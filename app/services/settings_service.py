import json
from pathlib import Path
from typing import Dict

def _settings_path() -> str:
    """
    Ermittelt den Pfad zur settings.json.
    Struktur:
      app/
        services/
          settings_service.py  <-- Wir sind hier (__file__)
        data/
          settings.json        <-- Wir wollen hier hin
    """
    # 1. Parent = app/services
    # 2. Parent = app
    base_dir = Path(__file__).resolve().parent.parent
    
    # Ordner "data" innerhalb von "app"
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    return str(data_dir / "settings.json")

def read_settings() -> Dict:
    path = _settings_path()
    if not Path(path).exists():
        default = {"token": "", "projects": {}}
        write_settings(default)
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {"token": "", "projects": {}}
    except (json.JSONDecodeError, OSError):
        return {"token": "", "projects": {}}

def write_settings(settings: Dict) -> None:
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)