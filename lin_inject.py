"""Linux: Text an der Cursor-Position einfügen – Zwischenablage + Strg+V über uinput.

Wie unter Windows: alte Zwischenablage sichern, Text hinein, warten bis Strg/Super losgelassen
sind, Strg+V senden, alte Zwischenablage zurücklegen. Terminals fügen mit Strg+Shift+V ein.

Die Zwischenablage gehört Qt und darf nur im Qt-Hauptthread angefasst werden. Der Worker-Thread
ruft deshalb über ein Signal mit BlockingQueuedConnection in den Hauptthread.
"""
import logging
import time

from PySide6.QtCore import QMimeData, QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

import lin_hotkeys
import lin_keys

log = logging.getLogger("murmel.inject")

# Diese Apps fügen mit Strg+Shift+V ein (Strg+V wäre dort ein Steuerzeichen)
TERMINALS = {"ptyxis", "gnome-terminal", "gnome-terminal-server", "kgx", "console", "konsole", "kitty",
             "alacritty", "wezterm", "wezterm-gui", "foot", "tilix", "terminator", "xterm", "yakuake",
             "blackbox", "terminal", "xfce4-terminal", "qterminal", "ghostty", "warp"}
# Klipper (KDE) und viele Clipboard-Manager speichern so markierte Inhalte nicht im Verlauf
SECRET_HINT = "x-kde-passwordManagerHint"


class _Clip(QObject):
    request = Signal(object)

    def __init__(self):
        super().__init__()
        self.request.connect(self._run, Qt.BlockingQueuedConnection)

    @Slot(object)
    def _run(self, job):
        fn, args, box = job
        try:
            box.append(fn(*args))
        except Exception as e:  # noqa: BLE001
            log.warning("Zwischenablage: %s", e)
            box.append(None)

    def call(self, fn, *args):
        if QThread.currentThread() is self.thread():
            return fn(*args)
        box = []
        self.request.emit((fn, args, box))
        return box[0] if box else None


_clip = None


def init():
    """Im Qt-Hauptthread aufrufen (Controller.__init__)."""
    global _clip
    _clip = _Clip()
    lin_keys.init()


def _cb():
    return QApplication.clipboard()


def _save():
    md = _cb().mimeData()
    if md is None:
        return None
    return {f: bytes(md.data(f)) for f in md.formats() if not f.startswith("application/x-qt")}


def _restore(saved):
    if saved is None:
        return
    md = QMimeData()
    for f, data in saved.items():
        md.setData(f, data)
    _cb().setMimeData(md)


def _set(text, exclude_history):
    md = QMimeData()
    md.setText(text)
    if exclude_history:
        md.setData(SECRET_HINT, b"secret")
    _cb().setMimeData(md)
    return True


def _get():
    return _cb().text()


def set_text(text: str, exclude_history=True):
    return bool(_clip.call(_set, text, exclude_history))


def get_text():
    return _clip.call(_get) or ""


def _wait_modifiers_released(timeout=1.0):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if not lin_hotkeys.modifiers_down():
            return True
        time.sleep(0.01)
    return False


def is_terminal(target) -> bool:
    app = (target or {}).get("app", "").lower() if isinstance(target, dict) else ""
    return app in TERMINALS or "terminal" in app


def paste(text: str, target, restore_ms=220) -> str:
    """Gibt "pasted" oder "clipboard" (Text bleibt zum selbst Einfügen in der Zwischenablage) zurück."""
    if not lin_keys.available():
        set_text(text, exclude_history=False)
        return "clipboard"
    saved = _clip.call(_save)
    if not set_text(text):
        return "clipboard"
    _wait_modifiers_released()
    time.sleep(0.03)
    keys = ("KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_V") if is_terminal(target) else ("KEY_LEFTCTRL", "KEY_V")
    lin_keys.chord(*keys)
    # Wayland-Apps holen den Inhalt erst auf Anfrage (über XWayland) -> etwas länger warten
    time.sleep(max(restore_ms, 450) / 1000)
    _clip.call(_restore, saved)
    return "pasted"


def copy_selection(timeout=0.6) -> str:
    """Markierten Text holen (Command Mode): Strg+C senden, auf den Text warten, zurücklegen."""
    if not lin_keys.available():
        return ""
    saved = _clip.call(_save)
    _clip.call(_set, "", False)
    _wait_modifiers_released()
    lin_keys.chord("KEY_LEFTCTRL", "KEY_C")
    text, t_end = "", time.monotonic() + timeout
    while time.monotonic() < t_end:
        time.sleep(0.04)
        text = get_text()
        if text:
            break
    _clip.call(_restore, saved)
    return text
