"""Einstellungen als JSON (atomar gespeichert):
Windows: %APPDATA%\\Murmel\\settings.json   Linux: ~/.config/murmel/settings.json"""
import json
import os
import sys
from pathlib import Path

APP_NAME = "Murmel"
if sys.platform == "win32":
    APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
else:
    APP_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "murmel"
SETTINGS_PATH = APP_DIR / "settings.json"
LOG_PATH = APP_DIR / "murmel.log"

DEFAULTS = {
    "hotkey": ["ctrl", "win"],         # gedrückt halten = diktieren
    "language": "auto",                 # auto (nur DE/EN) | de | en
    "model_gpu": "large-v3-turbo",
    "model_cpu": "small",
    "beam_size": 1,                     # Diktat = kurze Clips -> Tempo vor Breitensuche
    "cleanup": "normal",                # off | normal | strong
    "mic_device": None,                 # None = System-Standard
    "min_press_s": 0.3,                 # kürzer = Versehen
    "double_tap_s": 0.45,               # zweimal tippen = Freihand
    "handsfree_limit_min": 240,         # Freihand: Sicherheitsgrenze (4 h), reicht für jede Vorlesung
    "paste_restore_ms": 220,            # so lange bleibt der Text in der Zwischenablage
    "name": "",                         # für "Guten Morgen, …"
    "sounds": True,
    "theme": "system",                  # light | dark | system
    "command_hotkey": ["ctrl", "win", "alt"],   # Command Mode (braucht Ollama)
    "ollama_model": None,               # None = automatisch wählen
    "app_styles": {},                   # eigene Zuordnung App -> Stil
    "onboarded": False,
    "live_preview": True,               # Text-Blase beim Sprechen (nur mit GPU)
    "autostart": False,
    "rec_source": "mic",                # Aufnahme über ● in der Pille: mic | system | both
    "rec_dir": "",                      # Speicherort für Aufnahmen ("" = Desktop\1. Semester)
    "screen_off_s": 60,                 # Freihand: Bildschirm nach 1 min ohne Eingabe aus (OLED), 0 = aus
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
