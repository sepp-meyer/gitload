# app/routes.py
from flask import render_template, redirect, url_for, session, request
from app import app
from app.forms import TokenForm, ProjectForm
from app import utils
from app.projects import projects

@app.route('/', methods=['GET', 'POST'])
def token():
    """
    Route zur Eingabe des Git‑Tokens.
    """
    form = TokenForm()
    if form.validate_on_submit():
        session['token'] = form.token.data
        return redirect(url_for('project'))
    return render_template('token.html', form=form)

@app.route('/project', methods=['GET', 'POST'])
def project():
    """
    Route zur Projektauswahl.
    """
    token = session.get('token')
    if not token:
        return redirect(url_for('token'))
    form = ProjectForm()
    form.project.choices = [(key, key) for key in sorted(projects.keys())]
    if form.validate_on_submit():
        # Speichere das ausgewählte Projekt in der Session
        session['project'] = form.project.data
        return redirect(url_for('select_files'))
    return render_template('project.html', form=form)

@app.route('/select_files', methods=['GET'])
def select_files():
    """
    Zeigt die ZIP‑Struktur als Tabelle mit Auswahlkästchen.
    """
    token = session.get('token')
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('project'))
    repo_url = projects.get(project_key)
    flat_structure = utils.get_flat_zip_structure(repo_url, token)
    if flat_structure is None:
        error = "Fehler beim Laden der ZIP‑Struktur."
        return render_template('select_files.html', error=error)
    return render_template('select_files.html', flat_structure=flat_structure, project=project_key)

@app.route('/read_files', methods=['POST'])
def read_files():
    """
    Liest die Inhalte der vom Benutzer ausgewählten Dateien aus.
    """
    token = session.get('token')
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('project'))
    repo_url = projects.get(project_key)
    # Erhalte die Liste der ausgewählten Dateipfade aus dem Formular
    selected_paths = request.form.getlist('selected_paths')
    processed_files = utils.process_selected_files(repo_url, token, selected_paths)
    if processed_files is None:
        error = "Fehler beim Verarbeiten der ausgewählten Dateien."
        return render_template('read_files.html', error=error)
    return render_template('read_files.html', processed_files=processed_files)
