# ────────────────────────────────────────────────────────────────────────
# app/routes.py
from __future__ import annotations
from pathlib import Path
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, request, flash
)
from typing import Dict, List, Union
from collections import defaultdict
from app.forms import ProjectForm
from app import utils
import re

bp = Blueprint("main", __name__)

# ───────────────────────────────────────────────────────────────────────
#  Plant-UML-Generator  (Files → verschachtelte Packages,
#                        Functions → Komponenten,
#                        Calls     → Funktions-Kanten)
# ───────────────────────────────────────────────────────────────────────
def build_package_uml(code_tree: Dict[str, dict]) -> str:
    import re
    from pathlib import Path
    from typing import Dict, List, Union

    # ---------- Helper -------------------------------------------------
    def esc(path: str) -> str:
        return re.sub(r'[^A-Za-z0-9_]', '_', path)

    def trim(rel: str) -> str:
        parts = Path(rel).parts
        return "/".join(parts[1:]) if len(parts) > 1 else rel

    # ---------- 1) Baum der Ordner / Dateien / Funktionen --------------
    Tree = dict[str, "Tree | list[str]"]
    root: Tree = {}
    for rel, meta in code_tree.items():
        parts = Path(trim(rel)).parts
        ptr: Tree = root
        for folder in parts[:-1]:
            ptr = ptr.setdefault(folder, {})
        ptr[parts[-1]] = list(meta.get("functions", {}))

    # ---------- 2) Komponenten rendern --------------------------------
    lines: List[str] = [
        "@startuml",
        "left to right direction",
        'skinparam defaultFontName "Courier New"',
    ]

    def render(name: str, node: Union["Tree", list[str]], path_so_far: str, indent: str = "") -> None:
        alias = esc(path_so_far or name)
        lines.append(f'{indent}package "{name}" as {alias} {{')
        if isinstance(node, dict):
            for child, sub in sorted(node.items()):
                new = f"{path_so_far}/{child}" if path_so_far else child
                render(child, sub, new, indent + "  ")
        elif node:
            for fn in sorted(node):
                fn_alias = esc(f"{path_so_far}__{fn}")
                lines.append(f'{indent}  component "{fn}" as {fn_alias}')
        else:
            placeholder = esc(f"{path_so_far}__file")
            lines.append(f'{indent}  component "{name}" as {placeholder}')
        lines.append(f"{indent}}}")

    for top, sub in sorted(root.items()):
        render(top, sub, top)

    # ---------- 3) Internes Function→Alias-Mapping ---------------------
    func2alias: Dict[str, str] = {}
    file_of_alias: Dict[str, str] = {}
    for rel, meta in code_tree.items():
        mod_alias = esc(trim(rel))
        for fn in meta.get("functions", {}):
            alias = esc(f"{trim(rel)}__{fn}")
            func2alias[fn] = alias
            file_of_alias[alias] = mod_alias

    # ---------- 4) Import-Map (Name→Modul) ----------------------------
    name2module: Dict[str, str] = {}
    for meta in code_tree.values():
        for imp in meta.get("imports", []):
            if imp["type"] == "from":
                module = imp["module"].lstrip(".")
                name = imp.get("alias") or imp.get("name")
                if name:
                    name2module[name] = module
            else:  # import
                full = imp["module"]
                asname = imp.get("alias") or full.split(".")[0]
                name2module[asname] = full

    # ---------- 5) Externe Funktionen erkennen/filtern ---------------
    all_calls = {
        call
        for meta in code_tree.values()
        for fn_meta in meta.get("functions", {}).values()
        for call in fn_meta.get("calls", [])
    }
    external_fns = sorted(call for call in all_calls if call not in func2alias and call in name2module)

    # Alias für jede externe Funktion anlegen
    for fn in external_fns:
        func2alias[fn] = esc(f"extern__{fn}")

    # ---------- 6) Package “externe Funktionen” mit Unterordnern ------
    if external_fns:
        lines.append("")
        lines.append('package "externe Funktionen" as externe {')
        # group by module
        modules: Dict[str, List[str]] = {}
        for fn in external_fns:
            mod = name2module.get(fn, "")
            modules.setdefault(mod, []).append(fn)
        for mod, fns in sorted(modules.items()):
            pkg_alias = esc(f"externale__{mod}")
            lines.append(f'  package "{mod}.py" as {pkg_alias} {{')
            for fn in sorted(fns):
                alias = func2alias[fn]
                lines.append(f'    component "{fn}" as {alias}')
            lines.append("  }")
        lines.append("}")
        lines.append("")

    # ---------- 7) Call-Kanten erzeugen ------------------------------
    added: set[tuple[str, str]] = set()
    for rel, meta in code_tree.items():
        for fn, fn_meta in meta.get("functions", {}).items():
            src = func2alias[fn]
            for called in fn_meta.get("calls", []):
                dst = func2alias.get(called)
                if not dst or dst == src:
                    continue
                # überspringe intra-file-Kanten
                if file_of_alias.get(dst) == file_of_alias.get(src):
                    continue
                edge = (src, dst)
                if edge in added:
                    continue
                added.add(edge)
                lines.append(f"{src} ..> {dst} : {called}()")

    lines.append("@enduml")
    return "\n".join(lines)






# ════════════════════════════════════════════════════════════════════════
# 1) Start- und Projekt­auswahl
# ════════════════════════════════════════════════════════════════════════
@bp.route("/")
def index():
    settings = utils.read_settings()
    return redirect(
        url_for("main.project" if settings.get("token")
                else "main.settings_page")
    )

@bp.route("/project", methods=["GET", "POST"])
def project():
    settings = utils.read_settings()
    if not settings.get("token"):
        return redirect(url_for("main.settings_page"))

    form = ProjectForm()
    form.project.choices = [
        (k, k) for k in sorted(settings.get("projects", {}))
    ]
    if form.validate_on_submit():
        session["project"] = form.project.data
        return redirect(url_for("main.select_files"))
    return render_template("project.html", form=form)

# ════════════════════════════════════════════════════════════════════════
# 2) Dateiliste anzeigen
# ════════════════════════════════════════════════════════════════════════
@bp.route("/select_files")
def select_files():
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url  = settings["projects"].get(project_key)
    file_list = utils.get_flat_file_list(repo_url, token)

    flat_list = [
        {"filename": p, "indent": p.count("/") - 1}
        for p in file_list
    ]
    return render_template("select_files.html",
                           flat_list=flat_list, project=project_key)

# ════════════════════════════════════════════════════════════════════════
# 3) Gesamtausgabe / Analyse / UML
# ════════════════════════════════════════════════════════════════════════

@bp.route("/full_output", methods=["POST"])
def full_output():
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    # Ausgewählte Dateien aus dem vorherigen Formular
    selected_paths = request.form.getlist("selected_paths")

    repo_url = settings["projects"].get(project_key)

    # ZIP immer mit Analyse laden (alle Tabs befüllen)
    # ⇩ Neu: alias_warnings zusätzlich
    structure_str, content_str, analysis_rows, code_tree, alias_warnings = (
        utils.get_zip_full_output(repo_url, token,
                                  selected_paths, analyse=True)
    )
    if structure_str is None:
        return render_template("full_output.html",
                               error="Fehler beim Laden.")

    # ── Imports sammeln ───────────────────────────────────────────
    imports_rows = [
        {"file": rel, **imp}
        for rel, info in code_tree.items()
        for imp in info.get("imports", [])
    ]
    imports_rows.sort(key=lambda r: (r["file"], r["lineno"]))
    imports_copy = ""
    if imports_rows:
        headers = ["file","lineno","type","module","name","alias"]
        lines = ["\t".join(headers)]
        for r in imports_rows:
            lines.append("\t".join(str(r.get(c, "")) for c in headers))
        imports_copy = "\n".join(lines)

    # ── Funktions-Markdown (Tabellen-Ansicht) ─────────────────────
    if analysis_rows:
        known     = ["file", "func", "route", "class", "lineno"]
        col_order = [c for c in known if c in analysis_rows[0]] \
                    or list(analysis_rows[0].keys())
        md_head = "| " + " | ".join(col_order) + " |"
        md_sep  = "| " + " | ".join(["---"] * len(col_order)) + " |"
        md_body = [
            "| " + " | ".join(str(r.get(c, "")) for c in col_order) + " |"
            for r in analysis_rows
        ]
        analysis_markdown = "\n".join([md_head, md_sep, *md_body])
    else:
        col_order, analysis_markdown = [], ""

    # ── Codebaum-String erzeugen ─────────────────────────────────
    def build_tree(flat: dict) -> dict:
        root = {}
        for rel, info in flat.items():
            parts = rel.strip().split("/")
            ptr = root
            for p in parts[:-1]:
                ptr = ptr.setdefault(p, {})
            ptr[parts[-1]] = info
        return root

    def fmt_dir(node: dict, pref: str = "") -> list[str]:
        out = []
        keys = sorted(node)
        for i, name in enumerate(keys):
            last = (i == len(keys) - 1)
            branch = "└── " if last else "├── "
            next_pref = pref + ("    " if last else "│   ")
            sub = node[name]
            if isinstance(sub, dict) and "functions" not in sub:
                out.append(f"{pref}{branch}{name}/")
                out.extend(fmt_dir(sub, next_pref))
            else:
                out.append(f"{pref}{branch}{name}")
                for j, fn in enumerate(sub.get("functions", {})):
                    fn_last = (j == len(sub["functions"]) - 1)
                    fn_branch = "└── " if fn_last else "├── "
                    route = sub["functions"][fn].get("route", "")
                    out.append(f"{next_pref}{fn_branch}{fn}(){('  route: '+route) if route else ''}")
        return out

    code_tree_str = "\n".join(fmt_dir(build_tree(code_tree)))

    # ── UML-Script ────────────────────────────────────────────────
    uml_code = build_package_uml(code_tree)

    # ── Kombinierten Text (Struktur + Inhalte) ─────────────────────
    combined_text = (
        "Struktur der ZIP-Datei:\n" + structure_str + "\n\n" +
        "Einsicht in die Dateien:\n" + content_str
    )

    # ── Ergebnis rendern ───────────────────────────────────────────
    return render_template(
        "full_output.html",
        combined_text     = combined_text,
        analysis_rows     = analysis_rows,
        analysis_markdown = analysis_markdown,
        col_order         = col_order,
        imports_rows      = imports_rows,
        imports_copy      = imports_copy,
        code_tree_str     = code_tree_str,
        uml_code          = uml_code,
        alias_warnings    = alias_warnings,
    )



# ════════════════════════════════════════════════════════════════════════
# 4) Einstellungen
# ════════════════════════════════════════════════════════════════════════
@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    settings = utils.read_settings()
    if request.method == "POST":
        new_token = request.form.get("token", "").strip()
        names     = request.form.getlist("project_name[]")
        urls      = request.form.getlist("project_url[]")

        projects = {n.strip(): u.strip()
                    for n, u in zip(names, urls) if n.strip() and u.strip()}

        utils.write_settings({"token": new_token, "projects": projects})
        session["token"] = new_token
        return redirect(url_for("main.project"))

    return render_template(
        "settings.html",
        token=settings.get("token", ""),
        projects=settings.get("projects", {})
    )
