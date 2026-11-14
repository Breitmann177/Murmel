"""Einstellungen als JSON in %APPDATA%\\Murmel\\settings.json (atomar gespeichert)."""
import json
import os
from pathlib import Path

APP_NAME = "Murmel"
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_PATH = APP_DIR / "settings.json"
LOG_PATH = APP_DIR / "murmel.log"

DEFAULTS = {
    "hotkey": ["ctrl", "win"],         # gedrückt halten = diktieren
    "language": "auto",                 # auto (nur DE/EN) | de | en
    "model_gpu": "large-v3-turbo",
    "model_cpu": "small",
    "beam_size": 1,                     # Diktat = kurze Clips -> Tempo vor Breitensuche
    "cleanup": "normal",                # off | normal | strong
    "mic_device": None,                 # None = Windows-Standard
    "min_press_s": 0.3,                 # kürzer = Versehen
    "double_tap_s": 0.45,               # zweimal tippen = Freihand
    "handsfree_max_s": 360,
    "paste_restore_ms": 220,            # so lange bleibt der Text in der Zwischenablage
    "name": "",                         # für "Guten Morgen, …"
    "sounds": True,
    "theme": "system",                  # light | dark | system
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)   # atomar: nie eine halb geschriebene Datei
