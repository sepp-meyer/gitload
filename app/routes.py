# app/routes.py
from pathlib import Path
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, request
)
from typing import Dict, List
from collections import defaultdict
from app.forms import ProjectForm
from app import utils

bp = Blueprint("main", __name__)

# ──────────────────────────────────────────────────────────────────
# Hilfs-Funktion: PlantUML-Script (Ordner ▸ Datei ▸ Funktion)
#  - Dateien werden als „Packages“ angezeigt
#  - Funktions-Komponenten tragen NUR den Funktions-Namen
# ──────────────────────────────────────────────────────────────────
def build_package_uml(code_tree: Dict[str, dict],
                      imports_rows: List[dict]) -> str:
    """
    Erzeugt ein übersichtliches Diagramm:

        app
        ├─ routes.py
        │  ├─ index
        │  └─ save_data
        └─ utils.py
           ├─ read_settings
           └─ format_date
    """

    def esc(txt: str) -> str:
        """Alias-ID:  .  → _,   / → __   (PlantUML-kompatibel)."""
        return txt.replace(".", "_").replace("/", "__")

    def trim(rel: str) -> str:
        """Hash-Top-Folder (z. B. Git-ZIP-Ordner) entfernen."""
        parts = Path(rel).parts
        return "/".join(parts[1:]) if len(parts) > 1 else rel

    # ── Struktur sammeln  Folder ▸ Datei ▸ Funktionen ────────────
    folders: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rel_path, meta in code_tree.items():
        rel      = trim(rel_path)
        folder, file = rel.split("/", 1) if "/" in rel else ("<root>", rel)
        folders[folder][file].extend(meta.get("functions", {}).keys())

    uml = [
        "@startuml",
        "skinparam linetype ortho",
        'skinparam defaultFontName "Courier New"',
    ]

    # ── Packages + Komponenten ───────────────────────────────────
    for folder, files in sorted(folders.items()):
        uml.append(f'package "{folder}" {{')
        for file, fns in sorted(files.items()):
            file_alias = esc(file)
            uml.append(f'  package "{file}" as {file_alias} {{')
            for fn in sorted(fns):
                fn_alias = esc(f"{file}__{fn}")  # Alias enthält Datei + Fn
                uml.append(f'    component "{fn}" as {fn_alias}')
            uml.append("  }")
        uml.append("}")

    # ── Abhängigkeits-Kanten (projekt­interne Imports) ────────────
    for row in imports_rows:
        src_alias = esc(trim(row["file"]))
        if row["module"].startswith("app."):
            dst = row["module"].replace(".", "/") + ".py"
            dst_alias = esc(trim(dst))
            uml.append(f"{src_alias} ..> {dst_alias} : import")

    uml.append("@enduml")
    return "\n".join(uml)

# ──────────────────────────────────────────────────────────────────
# 1) Start- und Projekt­auswahl
# ──────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────
# 2) Dateiliste anzeigen
# ──────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────
# 3) Gesamtausgabe / Analyse / UML
# ──────────────────────────────────────────────────────────────────
@bp.route("/full_output", methods=["GET", "POST"])
def full_output():
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url = settings["projects"].get(project_key)

    # ── Benutzer-Optionen ─────────────────────────────────────────
    if request.method == "POST":
        selected_paths = request.form.getlist("selected_paths")
        analyse        = "with_analysis" in request.form
    else:
        selected_paths, analyse = None, False

    # ── ZIP analysieren ───────────────────────────────────────────
    structure_str, content_str, analysis_rows, code_tree = (
        utils.get_zip_full_output(repo_url, token,
                                  selected_paths, analyse=analyse)
    )
    if structure_str is None:
        return render_template("full_output.html",
                               error="Fehler beim Laden.")

    # ── Imports-Tabelle ───────────────────────────────────────────
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

    # ── Funktions-Markdown ────────────────────────────────────────
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

    # ── Code-Baum (Text) ──────────────────────────────────────────
    def build_tree(flat: Dict[str, dict]) -> Dict:
        root: Dict = {}
        for rel_path, info in flat.items():
            parts, ptr = rel_path.split("/"), root
            for part in parts[:-1]:
                ptr = ptr.setdefault(part, {})
            ptr[parts[-1]] = info
        return root

    def fmt_dir(node: Dict, pref: str = "") -> list[str]:
        out, keys = [], sorted(node)
        for i, name in enumerate(keys):
            last   = i == len(keys) - 1
            branch = "└── " if last else "├── "
            next_p = pref + ("    " if last else "│   ")

            if isinstance(node[name], dict) and \
               "functions" not in node[name]:
                out += [pref + branch + name + "/",
                        *fmt_dir(node[name], next_p)]
            else:
                out.append(pref + branch + name)
                funcs = list(node[name].get("functions", {}))
                for j, fn in enumerate(funcs):
                    fn_last = j == len(funcs) - 1
                    fn_br   = "└── " if fn_last else "├── "
                    route   = node[name]["functions"][fn].get("route", "")
                    out.append(next_p + fn_br + f"{fn}()" +
                               (f"  route: {route}" if route else ""))
        return out

    code_tree_str = "\n".join(fmt_dir(build_tree(code_tree)))

    # ── PlantUML-Script (angepasst) ───────────────────────────────
    uml_code = build_package_uml(code_tree, imports_rows)

    # ── Kombinierte Ausgabe ───────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────
# 4) Einstellungen (Token / Projekte)
# ──────────────────────────────────────────────────────────────────
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

    return render_template("settings.html",
                           token=settings.get("token", ""),
                           projects=settings.get("projects", {}))
