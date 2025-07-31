# app/utils.py
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


import requests
from requests.exceptions import RequestException

# Analyzer-Registry für verschiedene Dateitypen
from app.analyzer import REGISTRY


# ════════════════════════════════════════════════════════════════════
#  Hilfs-Generator: verschachtelten Dict-Baum flach durchlaufen
# ════════════════════════════════════════════════════════════════════
def _iterate_files_with_content(tree: Dict, base: str = ""):
    for key, val in tree.items():
        new_path = f"{base}/{key}" if base else key
        if isinstance(val, dict):
            yield from _iterate_files_with_content(val, new_path)
        else:
            yield new_path, val


# ════════════════════════════════════════════════════════════════════
#  Haupt-Routine: ZIP laden → Struktur / Inhalt / Analyse
# ════════════════════════════════════════════════════════════════════


def get_zip_full_output(
    repo_url: str,
    token: str,
    selected_paths: Optional[List[str]] = None,
    analyse: bool = False,
) -> Tuple[
    str,               # Struktur-String
    str,               # Inhalt-String
    List[Dict],        # analysis_rows
    Dict,              # code_tree
    List[Dict],        # alias_warnings
    List[Dict],        # import_conflicts
]:
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get(repo_url, headers=headers, timeout=15)
        response.raise_for_status()
    except RequestException as exc:
        print(f"[gitload] Download-Fehler: {exc}")
        return None, None, [], {}, [], []

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        full_tree: Dict = {}
        selected_tree: Dict = {}
        filter_all = selected_paths is None  # True → „alle markiert“

        # ── ZIP entpacken → verschachteltes Dict
        for info in zip_file.infolist():
            if info.filename in ("", "/"):
                continue
            parts = [p for p in info.filename.split("/") if p]
            if not parts:
                continue

            cur = full_tree
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})

            if info.is_dir():
                cur.setdefault(parts[-1], {})
                continue

            with zip_file.open(info) as f:
                content = f.read(50_000).decode("utf-8", errors="ignore")
            cur[parts[-1]] = content

            # Auswahl-Baum
            norm = info.filename.rstrip("/")
            if filter_all or norm in (selected_paths or []):
                cur = selected_tree
                for part in parts[:-1]:
                    cur = cur.setdefault(part, {})
                cur[parts[-1]] = content

        tree_focus = selected_tree if not filter_all else full_tree

        # ── Strings für Tabs 1 & 2
        def _fmt(tree: Dict, lvl=0) -> List[str]:
            ind = "  " * lvl
            lines: List[str] = []
            for k, v in tree.items():
                if isinstance(v, dict):
                    lines.append(f"{ind}/{k}")
                    lines += _fmt(v, lvl + 1)
                else:
                    lines.append(f"{ind}- {k}")
            return lines

        def _fmt_content(tree: Dict, lvl=0) -> List[str]:
            ind = "  " * lvl
            lines: List[str] = []
            for k, v in tree.items():
                if isinstance(v, dict):
                    lines.append(f"{ind}/{k}")
                    lines += _fmt_content(v, lvl + 1)
                else:
                    lines.append(f'{ind}- {k}: ')
                    lines.append(f'{ind}  "{v}"')
            return lines

        structure_str = "\n".join(_fmt(tree_focus))
        content_str   = "\n".join(_fmt_content(tree_focus))

        # ── Analyse (Tabellen, Code-Baum)
        analysis_rows: List[Dict] = []
        code_tree: Dict = {}
        alias_warnings: List[Dict] = []

        if analyse:
            # 1) Standard-Analyse und Alias-Erkennung
            for rel_path, text in _iterate_files_with_content(tree_focus):
                suffix = Path(rel_path).suffix.lower()
                analyzer = REGISTRY[suffix]
                analysis_rows.extend(analyzer.analyse(rel_path, text))
                if hasattr(analyzer, "analyse_tree"):
                    code_tree[rel_path] = analyzer.analyse_tree(rel_path, text)
                if hasattr(analyzer, "analyse_aliases"):
                    alias_warnings.extend(analyzer.analyse_aliases(rel_path, text))

            analysis_rows.sort(key=lambda r: (r["file"], r.get("lineno", 0)))

            # 2) Funktions-Verknüpfungen (unverändert)
            def _alias_map(meta: Dict) -> Dict[str, str]:
                aliases = {}
                for imp in meta.get("imports", []):
                    if not imp.get("alias"):
                        continue
                    if imp["type"] == "import":
                        aliases[imp["alias"]] = imp["module"]
                    elif imp["type"] == "from":
                        full_mod = imp["module"].lstrip(".")
                        if imp.get("name"):
                            full_mod += f".{imp['name']}"
                        aliases[imp["alias"]] = full_mod
                return aliases

            def _mod_to_rel(mod: str) -> Optional[str]:
                return "/".join(mod.split(".")) + ".py" if mod.startswith("app.") else None

            for src_rel, meta in code_tree.items():
                aliases = _alias_map(meta)
                for fn_meta in meta.get("functions", {}).values():
                    for call in fn_meta.get("calls", []):
                        target_mod = aliases.get(call)
                        if not target_mod:
                            continue
                        dst_rel = _mod_to_rel(target_mod)
                        if not dst_rel:
                            continue
                        dst_meta = code_tree.get(dst_rel, {})
                        if call not in dst_meta.get("functions", {}):
                            continue
                        fn_meta.setdefault("out_calls", []).append((dst_rel, call))

        # ── Import-Konflikte erkennen
        imports_rows: List[Dict] = []
        for rel, info in code_tree.items():
            for imp in info.get("imports", []):
                row = {"file": rel, **imp}
                imports_rows.append(row)

        # Name → alle importierenden Module
        name2modules: Dict[str, set] = defaultdict(set)
        for imp in imports_rows:
            name = imp.get("alias") or imp.get("name")
            if not name:
                continue
            name2modules[name].add(imp.get("module", ""))

        import_conflicts: List[Dict] = []
        for imp in imports_rows:
            name = imp.get("alias") or imp.get("name")
            mods = name2modules.get(name, set())
            if name and len(mods) > 1:
                import_conflicts.append({
                    "file":   imp["file"],
                    "lineno": imp["lineno"],
                    "name":   name,
                    "modules": sorted(mods),
                })

        return structure_str, content_str, analysis_rows, code_tree, alias_warnings, import_conflicts

    except zipfile.BadZipFile:
        print("[gitload] ZIP-Datei fehlerhaft oder leer")
        return None, None, [], {}, [], []




# ════════════════════════════════════════════════════════════════════
#  Dateiliste (flach) für die Auswahl-UI
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


# ════════════════════════════════════════════════════════════════════
#  Settings-Handling  (Token & Projekt-URLs)
# ════════════════════════════════════════════════════════════════════
def _settings_path() -> str:
    data_dir = Path(__file__).with_suffix("").parent / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "settings.json")


def read_settings() -> Dict:
    path = _settings_path()
    if not Path(path).exists():
        default = {"token": "", "projects": {}}
        write_settings(default)
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {"token": "", "projects": {}}
    except (json.JSONDecodeError, OSError):
        return {"token": "", "projects": {}}


def write_settings(settings: Dict) -> None:
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
