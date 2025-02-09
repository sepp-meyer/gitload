# app/utils.py
import requests
import zipfile
import io

def flatten_structure(structure, parent=""):
    """
    Rekursive Funktion, die eine verschachtelte Struktur in eine flache Liste umwandelt.
    """
    entries = []
    for key, value in structure.items():
        full_path = f"{parent}/{key}" if parent else key
        entries.append({
            "path": full_path,
            "name": key,
            "is_dir": bool(value),  # Verzeichnis, wenn value nicht leer ist
            "indent": full_path.count('/')
        })
        if value:
            entries.extend(flatten_structure(value, full_path))
    return entries

def get_flat_zip_structure(repo_url, token):
    """
    Lädt die ZIP‑Datei herunter und gibt eine flache Liste der Dateien/Ordner zurück.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code == 200:
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            # Erstelle die verschachtelte Struktur
            directories = {}
            for file_info in zip_file.infolist():
                parts = file_info.filename.split('/')
                current_level = directories
                for part in parts:
                    if part == "":
                        continue
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
            # Flache Struktur erzeugen
            flat_list = flatten_structure(directories)
            return flat_list
        except zipfile.BadZipFile:
            return None
    else:
        return None

def process_selected_files(repo_url, token, selected_paths):
    """
    Lädt die ZIP‑Datei herunter und liest den Inhalt der ausgewählten Dateien.
    Gibt ein Dictionary zurück: key = Pfad, value = Dateiinhalte.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code == 200:
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            processed_files = {}
            for file_info in zip_file.infolist():
                # Normalisiere den Dateinamen (entferne eventuell ein Schrägstrich am Ende)
                normalized_filename = file_info.filename.rstrip('/')
                if normalized_filename in selected_paths and not file_info.is_dir():
                    with zip_file.open(file_info) as f:
                        content = f.read().decode('utf-8', errors='replace')
                    processed_files[normalized_filename] = content
            return processed_files
        except zipfile.BadZipFile:
            return None
    else:
        return None
