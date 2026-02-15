# app/utils.py

def format_directory_tree(code_tree: dict) -> str:
    """
    Erzeugt den String für den Codebaum-Tab (Visualisierung).
    War früher inline in routes.py
    """
    # 1. Flaches Dict -> Baum
    def build_tree(flat: dict) -> dict:
        root = {}
        for rel, info in flat.items():
            parts = rel.strip().split("/")
            ptr = root
            for p in parts[:-1]:
                ptr = ptr.setdefault(p, {})
            ptr[parts[-1]] = info
        return root

    # 2. Baum -> String
    def fmt_dir(node: dict, pref: str = "") -> list[str]:
        out = []
        keys = sorted(node)
        for i, name in enumerate(keys):
            last = i == len(keys) - 1
            branch = "└── " if last else "├── "
            next_pref = pref + ("    " if last else "│   ")
            sub = node[name]

            if isinstance(sub, dict) and "functions" not in sub:
                out.append(f"{pref}{branch}{name}/")
                out.extend(fmt_dir(sub, next_pref))
                continue

            out.append(f"{pref}{branch}{name}")
            
            # Funktionen
            nested_map = sub.get("nested", {})
            nested_children = {c for lst in nested_map.values() for c in lst}
            top_funcs = [
                fn for fn in sorted(sub.get("functions", {})) 
                if fn not in nested_children
            ]

            def print_fn(fn_name, prefix, is_last):
                route = sub["functions"][fn_name].get("route", "")
                fn_br = "└── " if is_last else "├── "
                out.append(f"{prefix}{fn_br}{fn_name}(){'  route: '+route if route else ''}")
                
                kids = sorted(nested_map.get(fn_name, []))
                if not kids: return
                kid_pref_base = prefix + ("    " if is_last else "│   ")
                for k, kid in enumerate(kids):
                    print_fn(kid, kid_pref_base, k == len(kids) - 1)

            for j, fn in enumerate(top_funcs):
                print_fn(fn, next_pref, j == len(top_funcs) - 1)
        return out

    return "\n".join(fmt_dir(build_tree(code_tree)))