"""Murmel starten. Nur eine Instanz (zwei Hooks + zweimal das Modell im Speicher wären Murks)."""
import ctypes
import logging
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import config  # noqa: E402

config.APP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=config.LOG_PATH, level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Benannter Mutex: existiert er schon, läuft Murmel bereits
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MurmelSingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
    sys.exit(0)

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Murmel.Dictation")
except Exception:
    pass

try:
    from PySide6.QtWidgets import QApplication
    from app import Controller

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)    # läuft im Tray weiter
    ctl = Controller(app)
    sys.exit(app.exec())
except Exception:
    logging.exception("Absturz")
    ctypes.windll.user32.MessageBoxW(None, f"Murmel ist abgestürzt.\n{config.LOG_PATH}\n\n"
                                     f"{traceback.format_exc()[-600:]}", "Murmel", 0x10)
