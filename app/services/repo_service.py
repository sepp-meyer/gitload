import io
import os
import re
import zipfile
import requests
from requests.exceptions import RequestException
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from pathlib import Path

# Import der Analyzer aus dem übergeordneten Modul
from app.analyzer import REGISTRY
# NEU: Importiere die Baum-Formatierung
from app.utils import format_directory_tree

def _iterate_files_with_content(tree: Dict, base: str = ""):
    for key, val in tree.items():
        new_path = f"{base}/{key}" if base else key
        if isinstance(val, dict):
            yield from _iterate_files_with_content(val, new_path)
        else:
            yield new_path, val

# ════════════════════════════════════════════════════════════════════
#  NEU: Hilfsfunktion zum Entfernen von Kommentaren
# ════════════════════════════════════════════════════════════════════
def _remove_comments(text: str, ext: str) -> str:
    """
    Entfernt Kommentare aus Quellcode basierend auf der Dateiendung.
    """
    if not text:
        return ""
    
    clean_text = text

    if ext == '.py':
        # 1. Docstrings
        clean_text = re.sub(r'(?s)("{3}|\'{3}).*?\1', '', clean_text)
        # 2. Zeilenkommentare
        clean_text = re.sub(r'#.*$', '', clean_text, flags=re.MULTILINE)

    elif ext in ['.js', '.css']:
        # 1. Block-Kommentare
        clean_text = re.sub(r'(?s)/\*.*?\*/', '', clean_text)
        # 2. Zeilen-Kommentare
        clean_text = re.sub(r'(?<!:)//.*$', '', clean_text, flags=re.MULTILINE)

    elif ext == '.html':
        # 1. HTML Kommentare
        clean_text = re.sub(r'<!\-\-.*?\-\->', '', clean_text)
        
        # 2. Zusätzlich JS/CSS Kommentare innerhalb von <script>/<style> entfernen
        clean_text = re.sub(r'(?s)/\*.*?\*/', '', clean_text)
        clean_text = re.sub(r'(?<!:)//.*$', '', clean_text, flags=re.MULTILINE)

    # 3. Aufräumen: Mehrfache Leerzeilen reduzieren
    clean_text = re.sub(r'\n\s*\n\s*\n', '\n\n', clean_text)
    
    return clean_text.strip()

# ════════════════════════════════════════════════════════════════════
#  VERBESSERT: Hilfs-Generator: Repo-to-Markdown (Projektübergabe)
# ════════════════════════════════════════════════════════════════════
def _generate_markdown_handover(tree: Dict, structure_str: str, clean_mode: bool = False) -> str:
    """
    Erzeugt einen Markdown-String für LLM-Übergabe.
    Header-Tiefe (#) passt sich der Ordner-Tiefe an.
    Wenn clean_mode=True, werden Kommentare entfernt.
    """
    lines = []
    
    # 1. Projektnamen (Root-Ordner) ermitteln
    project_name = "Projekt"
    if tree:
        project_name = list(tree.keys())[0]

    # Header schreiben
    suffix = " (No Comments)" if clean_mode else ""
    lines.append(f"# Projekt /{project_name}{suffix}")
    lines.append("")
    lines.append("## Projektaufbau")
    lines.append("```")
    lines.append(structure_str)
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Mapping nur für die wichtigsten Sprachen
    ext_map = {
        '.py': 'python', 
        '.js': 'javascript', 
        '.html': 'html', 
        '.css': 'css',
        '.json': 'json',
        '.md': 'markdown',
        '.sh': 'bash',
        '.yml': 'yaml',
        '.yaml': 'yaml'
    }

    # 3. Dateien durchgehen
    for rel_path, content in _iterate_files_with_content(tree):
        # Pfad bereinigen und analysieren
        parts = rel_path.strip("/").split("/")
        
        visible_parts = []
        clean_path = ""

        if len(parts) > 1:
            # Alles nach dem ersten Slash (Root-Folder entfernen)
            visible_parts = parts[1:]
            clean_path = "/" + "/".join(visible_parts)
        else:
            # Fallback
            visible_parts = parts
            clean_path = "/" + rel_path

        # ─── Header-Tiefe ───
        depth = len(visible_parts) + 1
        if depth > 6:
            depth = 6
        hashes = "#" * depth
        # ────────────────────

        # Sprache bestimmen
        ext = os.path.splitext(rel_path)[1].lower()
        lang = ext_map.get(ext, "") 
        if rel_path.endswith("Dockerfile"):
            lang = "dockerfile"
        
        # Inhalt vorbereiten (ggf. bereinigen)
        final_content = content
        if clean_mode and ext in ['.py', '.html', '.js', '.css']:
            final_content = _remove_comments(content, ext)

        lines.append(f"{hashes} {clean_path}")
        lines.append(f"```{lang}")
        lines.append(final_content)
        lines.append("```")
        lines.append("") # Leerzeile

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
#  Haupt-Funktionen
# ════════════════════════════════════════════════════════════════════

def get_flat_file_list(repo_url: str, token: str) -> List[str]:
    headers = {"Authorization": f"token {token}"}
    try:
        r = requests.get(repo_url, headers=headers, timeout=15)
        r.raise_for_status()
    except RequestException:
        return []

    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        return [i.filename.rstrip("/") for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        return []

def get_zip_full_output(
    repo_url: str,
    token: str,
    selected_paths: Optional[List[str]] = None,
    analyse: bool = False,
) -> Tuple[str, str, str, str, List[Dict], Dict, List[Dict], List[Dict]]:
    
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get(repo_url, headers=headers, timeout=15)
        response.raise_for_status()
    except RequestException as exc:
        print(f"[repo_service] Download-Fehler: {exc}")
        return None, None, None, None, [], {}, [], []

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        full_tree: Dict = {}
        selected_tree: Dict = {}
        filter_all = selected_paths is None

        # ── ZIP entpacken
        for info in zip_file.infolist():
            if info.filename in ("", "/"): continue
            parts = [p for p in info.filename.split("/") if p]
            if not parts: continue

            cur = full_tree
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})

            if info.is_dir():
                cur.setdefault(parts[-1], {})
                continue

            with zip_file.open(info) as f:
                content = f.read(50_000).decode("utf-8", errors="ignore")
            cur[parts[-1]] = content

            # Auswahl
            norm = info.filename.rstrip("/")
            if filter_all or norm in (selected_paths or []):
                cur = selected_tree
                for part in parts[:-1]:
                    cur = cur.setdefault(part, {})
                cur[parts[-1]] = content

        tree_focus = selected_tree if not filter_all else full_tree

        # ── Strings generieren (Inhalt)
        def _fmt_content(tree: Dict, lvl=0) -> List[str]:
            ind = "  " * lvl
            lines = []
            for k, v in tree.items():
                if isinstance(v, dict):
                    lines.append(f"{ind}/{k}")
                    lines += _fmt_content(v, lvl + 1)
                else:
                    lines.append(f'{ind}- {k}: ')
                    lines.append(f'{ind}  "{v}"')
            return lines

        content_str = "\n".join(_fmt_content(tree_focus))

        # ════════════════════════════════════════════════════════════════════
        # ANALYSE & STRUKTUR (Geänderte Reihenfolge!)
        # Wir führen die Analyse JETZT aus, damit wir den detaillierten Baum 
        # (mit Funktionen) schon für die Markdown-Generierung nutzen können.
        # ════════════════════════════════════════════════════════════════════
        
        analysis_rows = []
        code_tree = {}
        alias_warnings = []
        import_conflicts = []

        # Wir laufen über alle Dateien für die Analyse (auch wenn analyse=False, 
        # holen wir zumindest den Tree für die Optik, sofern Analyzer vorhanden)
        for rel_path, text in _iterate_files_with_content(tree_focus):
            suffix = Path(rel_path).suffix.lower()
            analyzer = REGISTRY[suffix]
            
            # Code Tree immer befüllen für die Visualisierung
            if hasattr(analyzer, "analyse_tree"):
                code_tree[rel_path] = analyzer.analyse_tree(rel_path, text)
            else:
                # Falls kein Analyzer für Dateityp da ist, leeren Eintrag, damit Datei existiert
                code_tree[rel_path] = {} 

            # Detaillierte Analyse nur wenn angefordert
            if analyse:
                analysis_rows.extend(analyzer.analyse(rel_path, text))
                if hasattr(analyzer, "analyse_aliases"):
                    alias_warnings.extend(analyzer.analyse_aliases(rel_path, text))

        # ── Struktur-String generieren (jetzt mit format_directory_tree)
        if code_tree:
            structure_str = format_directory_tree(code_tree)
        else:
            # Fallback (sollte kaum eintreten, wenn Dateien da sind)
            def _fmt_simple(tree: Dict, lvl=0) -> List[str]:
                ind = "  " * lvl
                lines = []
                for k, v in tree.items():
                    if isinstance(v, dict):
                        lines.append(f"{ind}/{k}")
                        lines += _fmt_simple(v, lvl + 1)
                    else:
                        lines.append(f"{ind}- {k}")
                return lines
            structure_str = "\n".join(_fmt_simple(tree_focus))

        # ── HANDOVER MARKDOWN (Nutzt jetzt den detaillierten structure_str)
        # 1. Normal (mit Kommentaren)
        handover_md = _generate_markdown_handover(tree_focus, structure_str, clean_mode=False)
        
        # 2. Clean (OHNE Kommentare)
        handover_clean_md = _generate_markdown_handover(tree_focus, structure_str, clean_mode=True)

        # ── Nacharbeiten Analyse (Sortierung, Konflikte)
        if analyse:
            analysis_rows.sort(key=lambda r: (r["file"], r.get("lineno", 0)))

            # Import Konflikte
            imports_rows = [
                {"file": rel, **imp} for rel, info in code_tree.items() 
                for imp in info.get("imports", [])
            ]
            name2modules = defaultdict(set)
            for imp in imports_rows:
                n = imp.get("alias") or imp.get("name")
                if n: name2modules[n].add(imp.get("module", ""))
            
            for imp in imports_rows:
                n = imp.get("alias") or imp.get("name")
                mods = name2modules.get(n, set())
                if n and len(mods) > 1:
                    import_conflicts.append({
                        "file": imp["file"], "lineno": imp["lineno"],
                        "name": n, "modules": sorted(mods)
                    })

            # Call Graph Verlinkung
            def _alias_map(meta):
                al = {}
                for imp in meta.get("imports", []):
                    if imp.get("alias"):
                        al[imp["alias"]] = imp["module"]
                    elif imp["type"] == "from":
                         n = imp.get("name")
                         al[imp.get("alias") or n] = f"{imp['module']}.{n}".lstrip(".")
                return al
            
            def _mod_to_rel(mod):
                 return "/".join(mod.split(".")) + ".py" if mod.startswith("app.") else None

            for src_rel, meta in code_tree.items():
                aliases = _alias_map(meta)
                for fn_meta in meta.get("functions", {}).values():
                    for call in fn_meta.get("calls", []):
                        tgt = aliases.get(call)
                        if not tgt: continue
                        dst = _mod_to_rel(tgt)
                        if not dst: continue
                        if call in code_tree.get(dst, {}).get("functions", {}):
                            fn_meta.setdefault("out_calls", []).append((dst, call))

        return structure_str, content_str, handover_md, handover_clean_md, analysis_rows, code_tree, alias_warnings, import_conflicts

    except zipfile.BadZipFile:
        return None, None, None, None, [], {}, [], []