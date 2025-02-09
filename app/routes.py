# app/routes.py
from flask import render_template, redirect, url_for, session, request
from app import app
from app.forms import TokenForm, ProjectForm
from app import utils
from app.projects import projects

@app.route('/', methods=['GET', 'POST'])
def token():
    """Token-Eingabe"""
    form = TokenForm()
    if form.validate_on_submit():
        session['token'] = form.token.data
        return redirect(url_for('project'))
    return render_template('token.html', form=form)

@app.route('/project', methods=['GET', 'POST'])
def project():
    """Projektauswahl"""
    token = session.get('token')
    if not token:
        return redirect(url_for('token'))
    form = ProjectForm()
    form.project.choices = [(key, key) for key in sorted(projects.keys())]
    if form.validate_on_submit():
        session['project'] = form.project.data
        return redirect(url_for('select_files'))
    return render_template('project.html', form=form)

@app.route('/select_files', methods=['GET'])
def select_files():
    """
    Zeigt die ZIP-Struktur (als vollständigen Baum) und eine Liste der Dateien als Checkboxen.
    Standardmäßig sind alle Dateien ausgewählt.
    """
    token = session.get('token')
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('project'))
    repo_url = projects.get(project_key)
    
    # Zur Anzeige des vollständigen Strukturbaums (ohne Inhalte)
    structure_str, _ = utils.get_zip_full_output(repo_url, token)
    
    # Erhalte die Liste der Dateien (normalisierte Dateipfade)
    file_list = utils.get_flat_file_list(repo_url, token)
    flat_list = []
    for f in file_list:
        # Zur besseren Darstellung: Berechne den Einrückungslevel (Anzahl der "/" minus 1, da im ZIP meist ein Top-Level-Verzeichnis existiert)
        indent = f.count('/') - 1  
        flat_list.append({"filename": f, "indent": indent})
    
    return render_template('select_files.html', flat_list=flat_list, structure_str=structure_str, project=project_key)

@app.route('/full_output', methods=['GET', 'POST'])
def full_output():
    """
    Erzeugt die kombinierte Textausgabe.
    Bei einem POST-Request werden die ausgewählten Dateipfade zur Filterung verwendet.
    Bei GET-Requests werden alle Dateien ausgegeben.
    """
    token = session.get('token')
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('project'))
    repo_url = projects.get(project_key)
    
    if request.method == 'POST':
        selected_paths = request.form.getlist('selected_paths')
    else:
        selected_paths = None  # Alle Dateien anzeigen
    
    structure_str, content_str = utils.get_zip_full_output(repo_url, token, selected_paths)
    if structure_str is None:
        error = "Fehler beim Laden oder Verarbeiten der ZIP-Datei."
        return render_template('full_output.html', error=error)
    
    combined_text = (
        f"Struktur der ZIP-Datei:\n{structure_str}\n\n"
        f"Einsicht in die Dateien:\n{content_str}"
    )
    return render_template('full_output.html', combined_text=combined_text)
