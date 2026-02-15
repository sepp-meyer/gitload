# app/routes.py
from __future__ import annotations
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, request
)
from app.forms import ProjectForm

# Import Services & Utils
from app import utils
from app.services import settings_service, repo_service, uml_service

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    settings = settings_service.read_settings()
    return redirect(
        url_for("main.project" if settings.get("token")
                else "main.settings_page")
    )

@bp.route("/project", methods=["GET", "POST"])
def project():
    settings = settings_service.read_settings()
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

@bp.route("/select_files")
def select_files():
    settings    = settings_service.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url  = settings["projects"].get(project_key)
    
    # Aufruf an Service
    file_list = repo_service.get_flat_file_list(repo_url, token)

    flat_list = [
        {"filename": p, "indent": p.count("/") - 1}
        for p in file_list
    ]
    return render_template("select_files.html",
                           flat_list=flat_list, project=project_key)

@bp.route("/full_output", methods=["POST"])
def full_output():
    settings    = settings_service.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    selected_paths = request.form.getlist("selected_paths")
    repo_url       = settings["projects"].get(project_key)

    try:
        # Service Aufruf
        (structure_str, content_str, analysis_rows, code_tree, 
         alias_warnings, import_conflicts) = repo_service.get_zip_full_output(
            repo_url, token, selected_paths, analyse=True
        )
    except Exception as exc:
        print("[gitload] Analyse-Fehler:", exc)
        return render_template("full_output.html", error=f"Analyse-Fehler: {exc}")

    if structure_str is None:
        return render_template("full_output.html", error="Fehler beim Laden.")

    # ── Daten für View aufbereiten
    
    # Imports
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

    # Funktionen Markdown
    if analysis_rows:
        known     = ["file", "func", "route", "class", "lineno"]
        col_order = [c for c in known if c in analysis_rows[0]] or list(analysis_rows[0].keys())
        md_head = "| " + " | ".join(col_order) + " |"
        md_sep  = "| " + " | ".join(["---"] * len(col_order)) + " |"
        md_body = ["| " + " | ".join(str(r.get(c, "")) for c in col_order) + " |" for r in analysis_rows]
        analysis_markdown = "\n".join([md_head, md_sep, *md_body])
    else:
        col_order, analysis_markdown = [], ""

    # Visualisierung (jetzt in utils)
    code_tree_str = utils.format_directory_tree(code_tree)
    
    # UML (jetzt im service)
    uml_code = uml_service.build_package_uml(code_tree)

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
        alias_warnings    = alias_warnings,
        import_conflicts  = import_conflicts,
    )

@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    settings = settings_service.read_settings()
    if request.method == "POST":
        new_token = request.form.get("token", "").strip()
        names     = request.form.getlist("project_name[]")
        urls      = request.form.getlist("project_url[]")

        projects = {n.strip(): u.strip()
                    for n, u in zip(names, urls) if n.strip() and u.strip()}

        settings_service.write_settings({"token": new_token, "projects": projects})
        session["token"] = new_token
        return redirect(url_for("main.project"))

    return render_template(
        "settings.html",
        token=settings.get("token", ""),
        projects=settings.get("projects", {})
    )