# app/routes.py
from flask import Blueprint, render_template, redirect, url_for, session, request
from app.forms import ProjectForm
from app import utils
import json

bp = Blueprint('main', __name__)

# Startseite: Falls ein Token hinterlegt ist, direkt zu /project, sonst zu /settings
@bp.route('/')
def index():
    settings = utils.read_settings()
    if settings.get("token"):
        return redirect(url_for('main.project'))
    else:
        return redirect(url_for('main.settings_page'))

@bp.route('/project', methods=['GET', 'POST'])
def project():
    settings = utils.read_settings()
    token = settings.get("token", "")
    if not token:
        return redirect(url_for('main.settings_page'))
    form = ProjectForm()
    projects_dict = settings.get("projects", {})
    form.project.choices = [(key, key) for key in sorted(projects_dict.keys())]
    if form.validate_on_submit():
        session["project"] = form.project.data
        return redirect(url_for('main.select_files'))
    return render_template("project.html", form=form)

@bp.route('/select_files', methods=['GET'])
def select_files():
    settings = utils.read_settings()
    token = settings.get("token", "")
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('main.project'))
    repo_url = settings.get("projects", {}).get(project_key)
    if not repo_url:
        return redirect(url_for('main.project'))
    
    # Erhalte die Liste der Dateien (normalisierte Dateipfade)
    file_list = utils.get_flat_file_list(repo_url, token)
    flat_list = []
    for f in file_list:
        # Berechne den Einrückungslevel (Anzahl der "/" minus 1, da im ZIP meist ein Top-Level-Verzeichnis existiert)
        indent = f.count('/') - 1  
        flat_list.append({"filename": f, "indent": indent})
    
    return render_template('select_files.html', flat_list=flat_list, project=project_key)

@bp.route('/full_output', methods=['GET', 'POST'])
def full_output():
    settings   = utils.read_settings()
    token      = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url = settings.get("projects", {}).get(project_key)

    # ---------- Benutzer‑Optionen ----------------------------------
    if request.method == "POST":
        selected_paths = request.form.getlist("selected_paths")
        analyse        = ("with_analysis" in request.form)
    else:
        selected_paths = None       # alle Dateien
        analyse        = False

    # ---------- ZIP verarbeiten -----------------------------------
    structure_str, content_str, analysis_rows = utils.get_zip_full_output(
        repo_url, token, selected_paths, analyse=analyse
    )
    if structure_str is None:
        return render_template("full_output.html", error="Fehler beim Laden.")

    combined_text = (
        f"Struktur der ZIP-Datei:\n{structure_str}\n\n"
        f"Einsicht in die Dateien:\n{content_str}"
    )

    # ---------- Markdown‑Tabelle für Copy‑Button -------------------
    if analysis_rows:
        md_lines = ["| Datei | Funktion |", "|------|-----------|"]
        md_lines += [f"| {r['file']} | {r['element']} |" for r in analysis_rows]
        analysis_markdown = "\n".join(md_lines)
    else:
        analysis_markdown = ""

    # ---------- Render‑Template -----------------------------------
    return render_template(
        "full_output.html",
        combined_text     = combined_text,
        analysis_rows     = analysis_rows,
        analysis_markdown = analysis_markdown,   # für Copy‑Button im Tab
        analyse_flag      = analyse              # Checkbox‑Status
    )



@bp.route('/settings', methods=['GET', 'POST'])
def settings_page():
    settings = utils.read_settings()
    if request.method == 'POST':
        new_token = request.form.get("token", "").strip()
        project_names = request.form.getlist("project_name[]")
        project_urls = request.form.getlist("project_url[]")
        projects = {}
        for name, url in zip(project_names, project_urls):
            if name.strip() != "" and url.strip() != "":
                projects[name.strip()] = url.strip()
        new_settings = {"token": new_token, "projects": projects}
        utils.write_settings(new_settings)
        session["token"] = new_token  # Token in der Session aktualisieren
        return redirect(url_for("main.project"))
    return render_template("settings.html", token=settings.get("token", ""), projects=settings.get("projects", {}))
