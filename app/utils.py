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
    
def get_zip_structure_and_content(repo_url, token):
    """
    Lädt die ZIP-Datei vom Repository herunter, analysiert die Verzeichnisstruktur
    und liest (bis zu 50.000 Bytes) den Inhalt aller Dateien aus.
    Es werden zwei Strings zurückgegeben:
      - structure_str: Nur der Strukturbaum (Namen und Hierarchie)
      - structure_with_content_str: Strukturbaum mit Datei-Inhalten
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)
    if response.status_code == 200:
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            directories = {}
            # Alle Einträge im ZIP-Archiv verarbeiten
            for file_info in zip_file.infolist():
                # Überspringe leere Pfade
                if file_info.filename in ["", "/"]:
                    continue
                parts = file_info.filename.split('/')
                # Filtere leere Teile (z. B. am Ende eines Pfades)
                parts = [p for p in parts if p]
                if not parts:
                    continue
                current_level = directories
                # Für alle bis auf das letzte Element (Ordner-Hierarchie)
                for part in parts[:-1]:
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
                # Wenn es sich um eine Datei handelt, lese deren Inhalt ein
                if not file_info.is_dir():
                    try:
                        with zip_file.open(file_info) as f:
                            content = f.read(50000).decode('utf-8', errors='ignore')
                    except Exception as e:
                        content = f"Error reading file: {e}"
                    current_level[parts[-1]] = content
                else:
                    # Falls es ein Verzeichnis ist, falls noch nicht vorhanden anlegen
                    if parts[-1] not in current_level:
                        current_level[parts[-1]] = {}
            
            # Rekursive Hilfsfunktionen zur Formatierung der Struktur
            def format_structure(current_level, indent_level=0):
                formatted = ""
                indent = "  " * indent_level
                for key, value in current_level.items():
                    if isinstance(value, dict):
                        formatted += f"{indent}/{key}\n"
                        formatted += format_structure(value, indent_level + 1)
                    else:
                        formatted += f"{indent}- {key}\n"
                return formatted

            def format_structure_with_content(current_level, indent_level=0):
                formatted = ""
                indent = "  " * indent_level
                for key, value in current_level.items():
                    if isinstance(value, dict):
                        formatted += f"{indent}/{key}\n"
                        formatted += format_structure_with_content(value, indent_level + 1)
                    else:
                        # Für Dateien: Zeige Dateinamen und den (ausgelesenen) Inhalt
                        formatted += f"{indent}- {key}: \n{indent}  {value}\n"
                return formatted

            structure_str = format_structure(directories)
            structure_with_content_str = format_structure_with_content(directories)
            return structure_str, structure_with_content_str

        except zipfile.BadZipFile:
            return None, None
    else:
        return None, None
