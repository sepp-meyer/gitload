# app/routes.py
from flask import Blueprint, render_template, redirect, url_for, session, request
from typing import Dict
from collections import defaultdict
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

# Gesamtausgabe / Analyse
@bp.route("/full_output", methods=["GET", "POST"])
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
        analyse        = "with_analysis" in request.form
    else:
        selected_paths = None        # alle Dateien
        analyse        = False

    # ---------- ZIP verarbeiten -----------------------------------
    structure_str, content_str, analysis_rows, code_tree = utils.get_zip_full_output(
        repo_url, token, selected_paths, analyse=analyse
    )
    if structure_str is None:
        return render_template("full_output.html", error="Fehler beim Laden.")

    # ---------- Markdown‑Tabelle ----------------------------------
    if analysis_rows:
        known      = ["file", "func", "route", "class", "lineno"]
        col_order  = [c for c in known if c in analysis_rows[0]] or list(analysis_rows[0])
        md_lines   = [
            "| " + " | ".join(col_order) + " |",
            "| " + " | ".join(["---"] * len(col_order)) + " |",
        ] + [
            "| " + " | ".join(str(r.get(c, "")) for c in col_order) + " |"
            for r in analysis_rows
        ]
        analysis_markdown = "\n".join(md_lines)
    else:
        col_order, analysis_markdown = [], ""
        
    # ---------- Code‑Baum (Ordner‑/Dateibaum) ----------------------
    from collections import defaultdict

    def build_dir_tree(flat: Dict) -> Dict:
        """wandelt {'app/routes.py': info, …} in verschachtelten Dict‑Baum um"""
        root: Dict = {}
        for rel_path, info in flat.items():
            parts = rel_path.split("/")
            ptr   = root
            for part in parts[:-1]:
                ptr = ptr.setdefault(part, {})      # legt Unterdict an
            ptr[parts[-1]] = info                   # Dateiknoten
        return root

    def fmt_dir(node: Dict, prefix: str = "") -> list[str]:
        lines, keys = [], sorted(node.keys())
        for idx, name in enumerate(keys):
            is_last  = idx == len(keys) - 1
            branch   = "└── " if is_last else "├── "
            new_pref = prefix + ("    " if is_last else "│   ")

            # Ordner?
            if isinstance(node[name], dict) and "functions" not in node[name]:
                lines.append(prefix + branch + name + "/")
                lines.extend(fmt_dir(node[name], new_pref))
            else:  # Datei
                lines.append(prefix + branch + name)
                funcs = node[name].get("functions", {})
                fn_keys = list(funcs)
                for jdx, func in enumerate(fn_keys):
                    is_last_fn = jdx == len(fn_keys) - 1
                    fn_branch  = "└── " if is_last_fn else "├── "
                    route      = funcs[func].get("route")
                    route_txt  = f"  route: {route}" if route else ""
                    lines.append(
                        new_pref + fn_branch + f"{func}(){route_txt}"
                    )
        return lines

    dir_tree      = build_dir_tree(code_tree)
    code_tree_str = "\n".join(fmt_dir(dir_tree))


    # ---------- Kombinierte Textausgabe ----------------------------
    combined_text = (
        f"Struktur der ZIP-Datei:\n{structure_str}\n\n"
        f"Einsicht in die Dateien:\n{content_str}"
    )

    # ---------- Render‑Template -----------------------------------
    return render_template(
        "full_output.html",
        combined_text     = combined_text,
        analysis_rows     = analysis_rows,
        analysis_markdown = analysis_markdown,
        col_order         = col_order,
        code_tree_str     = code_tree_str,
        analyse_flag      = analyse,
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
