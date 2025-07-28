# app/utils.py
import requests, zipfile, io, os, json
from pathlib import Path
from typing import Dict, Tuple, List

# ─────────────────────────────────────────────────────────────────────
# Hilfs‑Funktion: Baum rekursiv durchlaufen   (NEU)
def _iterate_files_with_content(tree: Dict, base: str = ""):
    for key, val in tree.items():
        new_path = f"{base}/{key}" if base else key
        if isinstance(val, dict):
            yield from _iterate_files_with_content(val, new_path)
        else:
            yield new_path, val
# ─────────────────────────────────────────────────────────────────────



def get_zip_full_output(
    repo_url: str,
    token: str,
    selected_paths: List[str] | None = None,
    analyse: bool = False                                  # ← NEU
) -> Tuple[str, str, List[Dict]]:
    """
    Rückgabe:
        structure_str, content_str, analysis_rows
    """
    headers = {"Authorization": f"token {token}"}
    response = requests.get(repo_url, headers=headers)
    if response.status_code != 200:
        return None, None, []

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        full_tree, selected_tree = {}, {}
        filter_all = (selected_paths is None)

        # -------- Dateien sammeln ------------------------------------
        for info in zip_file.infolist():
            if info.filename in ["", "/"]:
                continue
            parts = [p for p in info.filename.split("/") if p]
            if not parts:
                continue

            cur_full = full_tree
            for part in parts[:-1]:
                cur_full = cur_full.setdefault(part, {})

            if info.is_dir():
                cur_full.setdefault(parts[-1], {})
                continue

            with zip_file.open(info) as f:
                content = f.read(50_000).decode("utf-8", errors="ignore")
            cur_full[parts[-1]] = content

            norm = info.filename.rstrip("/")
            if filter_all or norm in selected_paths:
                cur_sel = selected_tree
                for part in parts[:-1]:
                    cur_sel = cur_sel.setdefault(part, {})
                cur_sel[parts[-1]] = content

        # -------- Formatierung ---------------------------------------
        def fmt(tree, lvl=0):
            out, ind = "", "  " * lvl
            for k, v in tree.items():
                if isinstance(v, dict):
                    out += f"{ind}/{k}\n" + fmt(v, lvl + 1)
                else:
                    out += f"{ind}- {k}\n"
            return out

        def fmt_with_content(tree, lvl=0):
            out, ind = "", "  " * lvl
            for k, v in tree.items():
                if isinstance(v, dict):
                    out += f"{ind}/{k}\n" + fmt_with_content(v, lvl + 1)
                else:
                    out += f'{ind}- {k}: \n{ind}  "{v}"\n'
            return out

        structure_str = fmt(full_tree)
        content_str   = fmt_with_content(selected_tree)

        # -------- Analyse‑Phase --------------------------------------   (NEU)
        analysis_rows: List[Dict] = []
        if analyse:
            from app.analyzer import REGISTRY
            for rel_path, text in _iterate_files_with_content(full_tree):
                suffix = Path(rel_path).suffix.lower()
                analysis_rows.extend(REGISTRY[suffix].analyse(rel_path, text))

        return structure_str, content_str, analysis_rows

    except zipfile.BadZipFile:
        return None, None, []


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
