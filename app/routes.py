# app/routes.py
from flask import render_template, redirect, url_for, session, request
from app import app
from app.forms import TokenForm, ProjectForm
from app import utils
from app.projects import projects

@app.route('/', methods=['GET', 'POST'])
def token():
    """
    Token-Eingabe
    """
    form = TokenForm()
    if form.validate_on_submit():
        session['token'] = form.token.data
        return redirect(url_for('project'))
    return render_template('token.html', form=form)

@app.route('/project', methods=['GET', 'POST'])
def project():
    """
    Projektauswahl
    """
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
    Zeigt die ZIP-Struktur als Tabelle mit Auswahl-Checkboxen.
    Hierbei ist jede Checkbox standardmäßig aktiviert (checked),
    sodass per Default alle Dateien ausgewählt sind.
    """
    token = session.get('token')
    project_key = session.get('project')
    if not token or not project_key:
        return redirect(url_for('project'))
    repo_url = projects.get(project_key)
    # Nutze die Funktion, um eine flache Struktur zu erhalten (für die Anzeige)
    flat_structure = utils.get_zip_full_output(repo_url, token)[0]  # Nur der Strukturbaum wird hier benötigt
    # Für die Darstellung der Checkboxen bauen wir eine flache Liste aus dem Strukturbaum
    # (Hierzu können wir wieder eine einfache Funktion verwenden.)
    def flatten_tree(tree, parent=""):
        items = []
        for key, value in tree.items():
            full_path = f"{parent}/{key}" if parent else key
            # Falls value ein dict ist, handelt es sich um einen Ordner
            items.append({
                "path": full_path,
                "name": key,
                "is_dir": isinstance(value, dict),
                "indent": full_path.count('/')
            })
            if isinstance(value, dict):
                items.extend(flatten_tree(value, full_path))
        return items

    # Baue die verschachtelte Struktur erneut auf, um sie flach anzuzeigen
    # (Hierzu nutzen wir den gleichen Ansatz wie in der Utility-Funktion, aber nur für die Anzeige)
    # Wir laden die komplette Struktur erneut:
    structure_str, _ = utils.get_zip_full_output(repo_url, token)
    # Nun konstruieren wir einen einfachen Baum als Dictionary (mit Hierarchie) – 
    # alternativ könnte man eine eigene Funktion schreiben, hier nutzen wir eine vereinfachte Darstellung.
    # Damit wir die Checkboxen pro Zeile anzeigen können, bauen wir eine Liste auf:
    # Hinweis: Für eine exakte Hierarchie kannst du auch eine rekursive Funktion schreiben.
    # Hier ein vereinfachtes Beispiel, das der ursprünglichen Lösung ähnelt:
    import re
    pattern = re.compile(r'^( *)(/|- )(.+)$', re.MULTILINE)
    flat_list = []
    for line in structure_str.splitlines():
        m = pattern.match(line)
        if m:
            indent = len(m.group(1)) // 2
            name = m.group(3)
            # Erzeuge hier den "Pfad" anhand der Einrückung – in dieser einfachen Variante
            # speichern wir die Zeile als "Pfad", damit sie später zur Filterung genutzt werden kann.
            # In der finalen Ausgabe wird der Pfad dann wieder anhand des vollständigen Strukturbaums ermittelt.
            flat_list.append({"line": line.strip(), "indent": indent, "path": line.strip().replace("/","").replace("-","").strip()})
    # Falls keine sinnvolle flache Liste generiert wird, kann alternativ die ursprüngliche flat_structure genutzt werden.
    # Hier zeigen wir aber die komplette Struktur als Tabelle an.
    return render_template('select_files.html', flat_list=flat_list, project=project_key)

@app.route('/full_output', methods=['GET', 'POST'])
def full_output():
    """
    Erzeugt die kombinierte Textausgabe.
    Wird diese Route per POST (von der Auswahlseite) aufgerufen,
    werden die übermittelten (ausgewählten) Dateipfade genutzt.
    Bei GET werden alle Dateien angezeigt.
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
