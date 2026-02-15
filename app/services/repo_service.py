import io
import zipfile
import requests
from requests.exceptions import RequestException
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from pathlib import Path

# Import der Analyzer aus dem übergeordneten Modul
from app.analyzer import REGISTRY

def _iterate_files_with_content(tree: Dict, base: str = ""):
    for key, val in tree.items():
        new_path = f"{base}/{key}" if base else key
        if isinstance(val, dict):
            yield from _iterate_files_with_content(val, new_path)
        else:
            yield new_path, val

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
) -> Tuple[str, str, List[Dict], Dict, List[Dict], List[Dict]]:
    
    headers = {"Authorization": f"token {token}"}
    try:
        response = requests.get(repo_url, headers=headers, timeout=15)
        response.raise_for_status()
    except RequestException as exc:
        print(f"[repo_service] Download-Fehler: {exc}")
        return None, None, [], {}, [], []

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

        # ── Strings generieren (Helper Funktionen lokal)
        def _fmt(tree: Dict, lvl=0) -> List[str]:
            ind = "  " * lvl
            lines = []
            for k, v in tree.items():
                if isinstance(v, dict):
                    lines.append(f"{ind}/{k}")
                    lines += _fmt(v, lvl + 1)
                else:
                    lines.append(f"{ind}- {k}")
            return lines

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

        structure_str = "\n".join(_fmt(tree_focus))
        content_str   = "\n".join(_fmt_content(tree_focus))

        # ── Analyse
        analysis_rows = []
        code_tree = {}
        alias_warnings = []
        import_conflicts = []

        if analyse:
            for rel_path, text in _iterate_files_with_content(tree_focus):
                suffix = Path(rel_path).suffix.lower()
                analyzer = REGISTRY[suffix]
                analysis_rows.extend(analyzer.analyse(rel_path, text))
                if hasattr(analyzer, "analyse_tree"):
                    code_tree[rel_path] = analyzer.analyse_tree(rel_path, text)
                if hasattr(analyzer, "analyse_aliases"):
                    alias_warnings.extend(analyzer.analyse_aliases(rel_path, text))

            analysis_rows.sort(key=lambda r: (r["file"], r.get("lineno", 0)))

            # ── Import Konflikte & Calls (Logik 1:1 übernommen)
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

        return structure_str, content_str, analysis_rows, code_tree, alias_warnings, import_conflicts

    except zipfile.BadZipFile:
        return None, None, [], {}, [], []