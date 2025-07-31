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

bp = Blueprint("main", __name__)

# ───────────────────────────────────────────────────────────────────────
#  Plant-UML-Generator  (Files → verschachtelte Packages,
#                        Functions → Komponenten,
#                        Calls     → Funktions-Kanten)
# ───────────────────────────────────────────────────────────────────────
def build_package_uml(code_tree: Dict[str, dict]) -> str:
    from pathlib import Path
    from typing import Dict, List, Union

    # ---------- Helper -------------------------------------------------
    def esc(path: str) -> str:
        return path.replace(".", "_").replace("/", "__")

    def trim(rel: str) -> str:
        p = Path(rel).parts
        return "/".join(p[1:]) if len(p) > 1 else rel

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
    lines = [
        "@startuml",
        "left to right direction",
        'skinparam defaultFontName "Courier New"',
    ]

    def render(name: str, node: Union["Tree", list[str]],
               path: str = "", ind: str = "") -> None:
        alias = esc(path or name)
        lines.append(f'{ind}package "{name}" as {alias} {{')
        if isinstance(node, dict):
            for child, sub in sorted(node.items()):
                new = f"{path}/{child}" if path else child
                render(child, sub, new, ind + "  ")
        else:  # Funktions-Liste
            for fn in sorted(node):
                fn_alias = esc(f"{path}__{fn}")
                lines.append(f'{ind}  component "{fn}" as {fn_alias}')
        lines.append(f"{ind}}}")

    for top, sub in sorted(root.items()):
        render(top, sub, top)

    # ---------- 3) Funktions-Lookup (Name → Alias) ---------------------
    func2alias: Dict[str, str] = {}
    file_of_alias: Dict[str, str] = {}
    for rel, meta in code_tree.items():
        file_alias = esc(trim(rel))
        for fn in meta.get("functions", {}):
            a = esc(f"{trim(rel)}__{fn}")
            func2alias.setdefault(fn, a)           # bei Duplikaten gewinnt 1. Fund
            file_of_alias[a] = file_alias

    # ---------- 4) Call-Kanten erzeugen -------------------------------
    added: set[tuple[str, str]] = set()
    for rel, meta in code_tree.items():
        src_file_alias = esc(trim(rel))
        for fn, fn_meta in meta.get("functions", {}).items():
            src_alias = esc(f"{trim(rel)}__{fn}")
            for called in fn_meta.get("calls", []):
                dst_alias = func2alias.get(called)          # nur, wenn darin definiert
                if not dst_alias or dst_alias == src_alias:
                    continue
                # nur Datei-übergreifend
                if file_of_alias.get(dst_alias) == src_file_alias:
                    continue
                edge = (src_alias, dst_alias)
                if edge in added:
                    continue
                added.add(edge)
                lines.append(f"{src_alias} ..> {dst_alias} : {called}()")

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
@bp.route("/full_output", methods=["GET", "POST"])
def full_output():
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url = settings["projects"].get(project_key)

    # ── Benutzer-Optionen ──────────────────────────────────────────
    if request.method == "POST":
        selected_paths = request.form.getlist("selected_paths")
        analyse        = "with_analysis" in request.form
    else:
        selected_paths, analyse = None, False

    # ── ZIP analysieren ────────────────────────────────────────────
    structure_str, content_str, analysis_rows, code_tree = (
        utils.get_zip_full_output(repo_url, token,
                                  selected_paths, analyse=analyse)
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

    imports_copy = (
        "file\tlineno\ttype\tmodule\tname\talias\n" +
        "\n".join(
            "\t".join(str(r.get(c, "") or "") for c in
                      ("file", "lineno", "type", "module", "name", "alias"))
            for r in imports_rows
        )
    ) if imports_rows else ""

    # ── Funktions-Markdown (Tabellen-Ansicht) ─────────────────────
    if analysis_rows:
        known      = ["file", "func", "route", "class", "lineno"]
        col_order  = [c for c in known if c in analysis_rows[0]] \
                     or list(analysis_rows[0])

        md_head = "| " + " | ".join(col_order) + " |"
        md_sep  = "| " + " | ".join(["---"] * len(col_order)) + " |"
        md_body = [
            "| " + " | ".join(str(r.get(c, "")) for c in col_order) + " |"
            for r in analysis_rows
        ]
        analysis_markdown = "\n".join([md_head, md_sep, *md_body])
    else:
        col_order, analysis_markdown = [], ""

    # ── Text-Baum (tree-like) ─────────────────────────────────────
    def build_tree(flat: Dict[str, dict]) -> Dict:
        root: Dict = {}
        for rel_path, info in flat.items():
            parts, ptr = rel_path.strip().split("/"), root
            for part in parts[:-1]:
                ptr = ptr.setdefault(part, {})
            ptr[parts[-1]] = info
        return root

    def fmt_dir(node: Dict, pref: str = "") -> List[str]:
        out, keys = [], sorted(node)
        for i, name in enumerate(keys):
            last   = i == len(keys) - 1
            branch = "└── " if last else "├── "
            next_p = pref + ("    " if last else "│   ")

            if isinstance(node[name], dict) and "functions" not in node[name]:
                out += [pref + branch + name + "/",
                        *fmt_dir(node[name], next_p)]
            else:
                out.append(pref + branch + name)
                for j, fn in enumerate(node[name].get("functions", {})):
                    fn_last = j == len(node[name]["functions"]) - 1
                    fn_br   = "└── " if fn_last else "├── "
                    route   = node[name]["functions"][fn].get("route", "")
                    out.append(next_p + fn_br + f"{fn}()" +
                               (f"  route: {route}" if route else ""))
        return out

    code_tree_str = "\n".join(fmt_dir(build_tree(code_tree)))

    # ── UML-Script ────────────────────────────────────────────────
    uml_code = build_package_uml(code_tree)

    # ── Antwort rendern ───────────────────────────────────────────
    combined_text = (
        "Struktur der ZIP-Datei:\n" + structure_str + "\n\n" +
        "Einsicht in die Dateien:\n" + content_str
    )

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
        analyse_flag      = analyse,
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
