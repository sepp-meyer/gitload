# app/utils.py
import requests
import zipfile
import io
import os
import json

def get_zip_full_output(repo_url, token, selected_paths=None):
    """
    Lädt die ZIP-Datei vom Repository herunter und erstellt:
      - structure_str: Den vollständigen Strukturbaum (alle Dateien/Ordner)
      - content_str: Für die **ausgewählten** Dateien (oder alle, wenn selected_paths None ist)
                     den Dateinamen und den (ausgelesenen) Inhalt – wobei der Inhalt in doppelte
                     Anführungszeichen eingeschlossen wird.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code != 200:
        return None, None
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        
        full_tree = {}
        selected_tree = {}
        filter_all = (selected_paths is None)

        for file_info in zip_file.infolist():
            if file_info.filename in ["", "/"]:
                continue
            parts = [p for p in file_info.filename.split('/') if p]
            if not parts:
                continue
            cur_full = full_tree
            for part in parts[:-1]:
                if part not in cur_full:
                    cur_full[part] = {}
                cur_full = cur_full[part]
            if not file_info.is_dir():
                try:
                    with zip_file.open(file_info) as f:
                        content = f.read(50000).decode('utf-8', errors='ignore')
                except Exception as e:
                    content = f"Error reading file: {e}"
                cur_full[parts[-1]] = content

                normalized_filename = file_info.filename.rstrip('/')
                if filter_all or (normalized_filename in selected_paths):
                    cur_sel = selected_tree
                    for part in parts[:-1]:
                        if part not in cur_sel:
                            cur_sel[part] = {}
                        cur_sel = cur_sel[part]
                    cur_sel[parts[-1]] = content
            else:
                if parts[-1] not in cur_full:
                    cur_full[parts[-1]] = {}
        
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
                    # Inhalt in doppelte Anführungszeichen einklammern:
                    text += f'{indent}- {key}: \n{indent}  "{value}"\n'
            return text

        structure_str = format_tree(full_tree)
        content_str = format_tree_with_content(selected_tree)
        return structure_str, content_str

    except zipfile.BadZipFile:
        return None, None

def get_flat_file_list(repo_url, token):
    """
    Lädt die ZIP-Datei herunter und gibt eine Liste aller normalisierten Dateipfade (nur Dateien) zurück.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code != 200:
        return []
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        file_list = []
        for file_info in zip_file.infolist():
            if file_info.is_dir():
                continue
            normalized_filename = file_info.filename.rstrip('/')
            file_list.append(normalized_filename)
        return file_list
    except zipfile.BadZipFile:
        return []

### Funktionen zur Verwaltung der Einstellungen (Token und Projekte)

def get_settings_file_path():
    base_dir = os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return os.path.join(data_dir, "settings.json")

def read_settings():
    path = get_settings_file_path()
    if not os.path.exists(path):
        # Standard-Einstellungen, wenn die Datei noch nicht existiert
        default = {"token": "", "projects": {}}
        write_settings(default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Falls die Datei leer oder ungültig ist, setze data auf default
            if not isinstance(data, dict):
                raise ValueError("Settings file does not contain a dict.")
            return data
        except (json.JSONDecodeError, ValueError):
            default = {"token": "", "projects": {}}
            write_settings(default)
            return default


def write_settings(settings):
    path = get_settings_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
