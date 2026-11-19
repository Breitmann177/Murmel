"""Eine Schnittstelle, drei Betriebssysteme: lädt die Windows-, Linux- oder macOS-Umsetzung.

Der Rest von Murmel (app.py, UI) benutzt nur diese Namen und weiß nicht, worauf er läuft.
"""
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

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

    KEY_NAMES = {"ctrl": "Strg", "win": "Win", "alt": "Alt", "shift": "Shift", "rctrl": "Rechte Strg"}
    SYSTEM_DEFAULT_MIC = "Windows-Standard"
    AUTOSTART_LABEL = "Mit Windows starten"
elif IS_MAC:
    import mac_inject as inject  # noqa: F401
    from mac_hotkeys import PushToTalkHook  # noqa: F401
    from mac_util import (foreground, idle_seconds, monitor_off, monitor_on, prevent_sleep,  # noqa: F401
                          process_name, set_autostart, window_title)

    def init(app):
        import mac_util
        mac_util.init(app)

    # Auf dem Mac ist "win" die Cmd-Taste: Standard-Kürzel = Ctrl + Cmd
    KEY_NAMES = {"ctrl": "Ctrl", "win": "Cmd", "alt": "Option", "shift": "Shift", "rctrl": "Rechte Ctrl"}
    SYSTEM_DEFAULT_MIC = "Systemstandard"
    AUTOSTART_LABEL = "Bei der Anmeldung starten"
else:
    import lin_inject as inject  # noqa: F401
    from lin_hotkeys import PushToTalkHook  # noqa: F401
    from lin_util import (foreground, idle_seconds, monitor_off, monitor_on, prevent_sleep,  # noqa: F401
                          process_name, set_autostart, window_title)

    def init(app):
        inject.init()

    KEY_NAMES = {"ctrl": "Strg", "win": "Super", "alt": "Alt", "shift": "Shift", "rctrl": "Rechte Strg"}
    SYSTEM_DEFAULT_MIC = "Systemstandard"
    AUTOSTART_LABEL = "Beim Anmelden starten"

WIN_KEY = KEY_NAMES["win"]
if IS_MAC:
    HOOK_FAILED = "Bedienungshilfen für Murmel erlauben"      # Systemeinstellungen → Datenschutz
elif IS_WINDOWS:
    HOOK_FAILED = "Tastatur-Hook fehlgeschlagen"
else:
    HOOK_FAILED = "Keine Tastaturrechte (install.sh)"


def combo_text(keys):
    return " + ".join(KEY_NAMES[k] for k in keys)
