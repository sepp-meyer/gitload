# app/utils.py
import requests
import zipfile
import io

def get_zip_structure(repo_url, token):
    """
    Lädt die ZIP-Datei aus dem Repository herunter, entpackt sie im Speicher
    und gibt die Verzeichnisstruktur als formatierten String zurück.
    """
    headers = {'Authorization': f'token {token}'}
    response = requests.get(repo_url, headers=headers)

    if response.status_code == 200:
        try:
            # Öffne die ZIP-Datei im Speicher
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))

            def get_structure(zip_ref):
                """
                Baut ein verschachteltes Dictionary aus den Pfadkomponenten der ZIP-Datei.
                """
                directories = {}
                for file_info in zip_ref.infolist():
                    parts = file_info.filename.split('/')
                    current_level = directories
                    for part in parts:
                        if part == "":  # Überspringe leere Teile (z.B. am Ende eines Pfades)
                            continue
                        if part not in current_level:
                            current_level[part] = {}
                        current_level = current_level[part]
                return directories

            def format_structure(structure, indent_level=0):
                """
                Formatiert das Dictionary rekursiv als String.
                """
                formatted = ""
                indent = "  " * indent_level
                for key, value in structure.items():
                    if value:  # Falls es sich um ein Verzeichnis handelt
                        formatted += f"{indent}/{key}\n"
                        formatted += format_structure(value, indent_level + 1)
                    else:  # Datei
                        formatted += f"{indent}- {key}\n"
                return formatted

            # Erstelle und formatiere die Struktur
            structure_dict = get_structure(zip_file)
            structure_str = format_structure(structure_dict)
            return structure_str

        except zipfile.BadZipFile:
            return "Die heruntergeladene Datei ist keine gültige ZIP-Datei."
    else:
        return f'Fehler beim Herunterladen der Datei. Statuscode: {response.status_code}'
