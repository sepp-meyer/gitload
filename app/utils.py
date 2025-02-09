# app/utils.py
import requests
import zipfile
import io

def get_zip_full_output(repo_url, token, selected_paths=None):
    """
    Lädt die ZIP-Datei vom Repository herunter und erstellt:
      - structure_str: Den vollständigen Strukturbaum (alle Dateien/Ordner)
      - content_str: Für die **ausgewählten** Dateien (falls selected_paths angegeben sind)
                     den Dateinamen und den (ausgelesenen) Inhalt.
    
    Falls selected_paths None ist, werden **alle** Dateien in den Inhaltsbereich übernommen.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code != 200:
        return None, None
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        
        # Zunächst wird die vollständige verschachtelte Struktur (ohne Inhalt) aufgebaut
        full_tree = {}
        # Gleichzeitig werden wir alle Dateien (nicht-Verzeichnisse) für den Inhaltsbereich sammeln
        # In selected_tree wird nur das aufgenommen, was der Benutzer ausgewählt hat.
        selected_tree = {}
        
        # Wenn keine Filterung erfolgt, gilt: Alle Dateien sind ausgewählt.
        if selected_paths is None:
            filter_all = True
        else:
            filter_all = False

        # Für jeden Eintrag im ZIP-Archiv:
        for file_info in zip_file.infolist():
            # Überspringe leere Pfade
            if file_info.filename in ["", "/"]:
                continue
            # Zerlege den Pfad in Komponenten und filtere leere Teile (z. B. am Ende)
            parts = [p for p in file_info.filename.split('/') if p]
            if not parts:
                continue
            # Aufbau des vollständigen Strukturbaums (full_tree)
            cur_full = full_tree
            for part in parts[:-1]:
                if part not in cur_full:
                    cur_full[part] = {}
                cur_full = cur_full[part]
            # Falls es sich um eine Datei handelt, lese den Inhalt ein
            if not file_info.is_dir():
                try:
                    with zip_file.open(file_info) as f:
                        content = f.read(50000).decode('utf-8', errors='ignore')
                except Exception as e:
                    content = f"Error reading file: {e}"
                cur_full[parts[-1]] = content

                # Normalisiere den Dateinamen (ohne abschließenden Schrägstrich)
                normalized_filename = file_info.filename.rstrip('/')
                # Entscheide, ob diese Datei in den Inhaltsbereich aufgenommen werden soll
                if filter_all or (normalized_filename in selected_paths):
                    # Baue für die Datei in einem separaten Baum (selected_tree) die gleiche Hierarchie auf
                    cur_sel = selected_tree
                    for part in parts[:-1]:
                        if part not in cur_sel:
                            cur_sel[part] = {}
                        cur_sel = cur_sel[part]
                    cur_sel[parts[-1]] = content
            else:
                # Bei Verzeichnissen: falls noch nicht vorhanden, anlegen
                if parts[-1] not in cur_full:
                    cur_full[parts[-1]] = {}
                # Für den Inhaltsbereich: Bei Verzeichnissen legen wir erst nichts an
                # (Später erfolgt die Formatierung nur für Dateien)
        
        # Rekursive Funktionen zur Formatierung in einen Text
        def format_tree(tree, indent_level=0):
            text = ""
            indent = "  " * indent_level
            for key, value in tree.items():
                if isinstance(value, dict):
                    text += f"{indent}/{key}\n"
                    text += format_tree(value, indent_level + 1)
                else:
                    text += f"{indent}- {key}\n"
            return text

        def format_tree_with_content(tree, indent_level=0):
            text = ""
            indent = "  " * indent_level
            for key, value in tree.items():
                if isinstance(value, dict):
                    text += f"{indent}/{key}\n"
                    text += format_tree_with_content(value, indent_level + 1)
                else:
                    text += f"{indent}- {key}: \n{indent}  {value}\n"
            return text

        structure_str = format_tree(full_tree)
        content_str = format_tree_with_content(selected_tree)
        return structure_str, content_str

    except zipfile.BadZipFile:
        return None, None
