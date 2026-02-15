from pathlib import Path
from typing import Dict, List, Union, Set
from collections import defaultdict
import re

def build_package_uml(code_tree: Dict[str, dict]) -> str:
    # ── Hilfsfunktionen ──────────────────────────────────────────────
    def esc(s: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", s)

    def trim(rel: str) -> str:
        parts = Path(rel).parts
        return "/".join(parts[1:]) if len(parts) > 1 else rel

    # ── 0) Nested-Kinder global sammeln
    nested_children: Set[str] = {
        inner
        for meta in code_tree.values()
        for inners in meta.get("nested", {}).values()
        for inner in inners
    }

    # ── 1) Baum aufbauen
    root = {}
    for rel, meta in code_tree.items():
        parts = Path(trim(rel)).parts
        ptr = root
        for folder in parts[:-1]:
            ptr = ptr.setdefault(folder, {})
        
        top_funcs = [
            fn for fn in meta.get("functions", {})
            if fn not in nested_children
        ]
        ptr[parts[-1]] = top_funcs

    # ── 2) UML-Text
    lines: List[str] = [
        "@startuml",
        "left to right direction",
        'skinparam defaultFontName "Courier New"',
    ]
    trim2meta = {trim(rel): meta for rel, meta in code_tree.items()}

    # ── 3) Rendern
    def render(name: str, node: Union[dict, list], path_so_far: str, indent: str = "") -> None:
        alias = esc(path_so_far or name)
        lines.append(f'{indent}package "{name}" as {alias} {{')

        if isinstance(node, dict):
            for child, sub in sorted(node.items()):
                new_path = f"{path_so_far}/{child}" if path_so_far else child
                render(child, sub, new_path, indent + "  ")
        elif node: 
            nested_map = trim2meta.get(path_so_far, {}).get("nested", {})
            
            def render_fn(fn_name: str, alias_prefix: str, indent_fn: str) -> None:
                children = nested_map.get(fn_name, [])
                cur_prefix = f"{alias_prefix}__{fn_name}" if alias_prefix else f"{path_so_far}__{fn_name}"
                cur_alias = esc(cur_prefix)

                if children:
                    lines.append(f'{indent_fn}package "{fn_name}()" as {cur_alias} {{')
                    for child in sorted(children):
                        render_fn(child, cur_prefix, indent_fn + "  ")
                    lines.append(f'{indent_fn}}}')
                else:
                    lines.append(f'{indent_fn}component "{fn_name}()" as {cur_alias}')

            for fn in sorted(node):
                render_fn(fn, "", indent + "  ")
        else:
            placeholder = esc(f"{path_so_far}__file")
            lines.append(f'{indent}  component "{name}" as {placeholder}')

        lines.append(f"{indent}}}")

    for top, sub in sorted(root.items()):
        render(top, sub, top)

    # ── 4-8) Alias & Kanten
    func2alias = {}
    file_of_alias = {}
    
    for rel, meta in code_tree.items():
        rel_trim = trim(rel)
        mod_alias = esc(rel_trim)
        for fn in meta.get("functions", {}):
            alias = esc(f"{rel_trim}__{fn}")
            func2alias[fn] = alias
            file_of_alias[alias] = mod_alias
        for parent, inners in meta.get("nested", {}).items():
            for inner in inners:
                alias = esc(f"{rel_trim}__{parent}__{inner}")
                func2alias[inner] = alias
                file_of_alias[alias] = mod_alias

    def resolve_module(origin, raw):
        rel_trimmed = trim(origin)
        base = Path("/".join(rel_trimmed.split("/")[:-1]))
        level = len(raw) - len(raw.lstrip("."))
        name  = raw.lstrip(".")
        for _ in range(max(0, level - 1)):
             base = base.parent
        if name:
            for part in name.split("."):
                base = base / part
        return base.stem

    name2module = {}
    for origin, meta in code_tree.items():
        for imp in meta.get("imports", []):
            canon = resolve_module(origin, imp["module"])
            if imp["type"] == "from":
                n = imp.get("alias") or imp.get("name")
                if n: name2module[n] = canon
            else:
                alias = imp.get("alias") or imp["module"].split(".")[0]
                name2module[alias] = canon

    all_calls = {
        c for meta in code_tree.values() 
        for fn_meta in meta.get("functions", {}).values() 
        for c in fn_meta.get("calls", [])
    }
    external_fns = sorted(c for c in all_calls if c not in func2alias and c in name2module)
    for fn in external_fns:
        func2alias[fn] = esc(f"extern__{fn}")

    if external_fns:
        lines.append('\npackage "externe Funktionen" as externe {')
        modules = defaultdict(list)
        for fn in external_fns:
            modules[name2module[fn]].append(fn)
        for mod, fns in sorted(modules.items()):
            pkg_alias = esc(f"externale__{mod}")
            lines.append(f'  package "{mod}.py" as {pkg_alias} {{')
            for fn in sorted(fns):
                lines.append(f'    component "{fn}" as {func2alias[fn]}')
            lines.append("  }")
        lines.append("}\n")

    added = set()
    for rel, meta in code_tree.items():
        for fn, fn_meta in meta.get("functions", {}).items():
            src = func2alias[fn]
            for called in fn_meta.get("calls", []):
                dst = func2alias.get(called)
                if not dst or dst == src: continue
                if file_of_alias.get(dst) == file_of_alias.get(src): continue
                if (src, dst) in added: continue
                added.add((src, dst))
                lines.append(f"{src} ..> {dst} : {called}()")

    lines.append("@enduml")
    return "\n".join(lines)