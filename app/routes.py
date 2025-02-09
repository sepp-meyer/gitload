# app/routes.py
from flask import render_template, redirect, url_for, session, request
from app import app
from app.forms import TokenForm, ProjectForm
from app import utils
from app.projects import projects

@app.route('/', methods=['GET', 'POST'])
def token():
    """
    Route zur Eingabe des Git-Tokens.
    """
    form = TokenForm()
    if form.validate_on_submit():
        # Speichere das eingegebene Token in der Session
        session['token'] = form.token.data
        return redirect(url_for('project'))
    return render_template('token.html', form=form)

@app.route('/project', methods=['GET', 'POST'])
def project():
    """
    Route zur Auswahl eines Projekts und Darstellung der ZIP-Struktur.
    """
    # Stelle sicher, dass ein Token vorhanden ist
    token = session.get('token')
    if not token:
        return redirect(url_for('token'))

    form = ProjectForm()
    # Fülle die Dropdown-Liste mit den Projektnamen
    form.project.choices = [(key, key) for key in sorted(projects.keys())]

    structure = None  # Variable für die Ausgabe der ZIP-Struktur

    if form.validate_on_submit():
        selected_project = form.project.data
        repo_url = projects.get(selected_project)

        # Rufe die Funktion auf, um die ZIP-Struktur zu erhalten
        structure = utils.get_zip_structure(repo_url, token)

    return render_template('project.html', form=form, structure=structure)
