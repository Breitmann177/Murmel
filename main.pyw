"""Murmel starten. Nur eine Instanz (zwei Hooks + zweimal das Modell im Speicher wären Murks)."""
import logging
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import config  # noqa: E402

WINDOWS = sys.platform == "win32"

config.APP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=config.LOG_PATH, level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if WINDOWS:
    import ctypes
    # Benannter Mutex: existiert er schon, läuft Murmel bereits
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MurmelSingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        sys.exit(0)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Murmel.Dictation")
    except Exception:
        pass
else:
    import fcntl
    # Datei-Sperre statt Mutex: wird beim Beenden (auch bei Absturz) automatisch frei
    _lock = open(config.APP_DIR / "murmel.lock", "w")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)
    # Wayland lässt Fenster sich weder selbst platzieren noch "immer oben" bleiben, und die
    # Zwischenablage nur mit Fokus setzen. Über XWayland (xcb) geht beides – also dort laufen.
    if os.environ.get("DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def _crash_box(text):
    if WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Murmel", 0x10)
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        _app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Murmel", text)
    except Exception:
        print(text, file=sys.stderr)


try:
    from PySide6.QtWidgets import QApplication
    from app import Controller

    app = QApplication(sys.argv)
    app.setApplicationName("Murmel")
    app.setDesktopFileName("murmel")
    app.setQuitOnLastWindowClosed(False)    # läuft im Tray weiter
    ctl = Controller(app)
    sys.exit(app.exec())
except SystemExit:
    raise
except Exception:
    logging.exception("Absturz")
    _crash_box(f"Murmel ist abgestürzt.\n{config.LOG_PATH}\n\n{traceback.format_exc()[-600:]}")
