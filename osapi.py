"""Eine Schnittstelle, zwei Betriebssysteme: lädt die Windows- oder die Linux-Umsetzung.

Der Rest von Murmel (app.py, UI) benutzt nur diese Namen und weiß nicht, worauf er läuft.
"""
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import inject  # noqa: F401
    from hotkeys import PushToTalkHook  # noqa: F401
    from winutil import (idle_seconds, monitor_off, prevent_sleep, process_name,  # noqa: F401
                         set_autostart, user32, window_title)

    def foreground():
        return user32.GetForegroundWindow()

    def monitor_on():
        pass                      # Windows weckt den Bildschirm bei Eingabe selbst

    def init(app):
        pass

    WIN_KEY = "Win"
    SYSTEM_DEFAULT_MIC = "Windows-Standard"
    AUTOSTART_LABEL = "Mit Windows starten"
else:
    import lin_inject as inject  # noqa: F401
    from lin_hotkeys import PushToTalkHook  # noqa: F401
    from lin_util import (foreground, idle_seconds, monitor_off, monitor_on, prevent_sleep,  # noqa: F401
                          process_name, set_autostart, window_title)

    def init(app):
        inject.init()

    WIN_KEY = "Super"
    SYSTEM_DEFAULT_MIC = "Systemstandard"
    AUTOSTART_LABEL = "Beim Anmelden starten"

KEY_NAMES = {"ctrl": "Strg", "win": WIN_KEY, "alt": "Alt", "shift": "Shift", "rctrl": "Rechte Strg"}


def combo_text(keys):
    return " + ".join(KEY_NAMES[k] for k in keys)
