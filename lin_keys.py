"""Linux: Tasten senden über ein virtuelles Tastatur-Gerät (uinput). Geht unter Wayland und X11.

Braucht Schreibrechte auf /dev/uinput (udev-Regel aus install.sh). Ohne die Rechte fügt Murmel
nicht selbst ein, sondern lässt den Text in der Zwischenablage (Strg+V drückst du dann selbst).
"""
import threading
import time

DEVICE_NAME = "Murmel virtual keyboard"
_ui = None
_lock = threading.Lock()
_failed = False


def _device():
    global _ui, _failed
    if _ui is not None or _failed:
        return _ui
    try:
        from evdev import UInput, ecodes as E
        keys = [E.KEY_LEFTCTRL, E.KEY_LEFTSHIFT, E.KEY_V, E.KEY_C, E.KEY_F24]
        _ui = UInput({E.EV_KEY: keys}, name=DEVICE_NAME)
        time.sleep(0.3)            # der Compositor muss das neue Gerät erst kennenlernen
    except Exception:
        _failed = True
        _ui = None
    return _ui


def available() -> bool:
    return _device() is not None


def init():
    """Früh anlegen (beim Start), damit das erste Einfügen nicht verloren geht."""
    threading.Thread(target=_device, daemon=True).start()


def send(*events):
    """events: (keycode, down: bool) – alles in einem Rutsch."""
    with _lock:
        ui = _device()
        if ui is None:
            return False
        from evdev import ecodes as E
        for code, down in events:
            ui.write(E.EV_KEY, code, 1 if down else 0)
            ui.syn()
            time.sleep(0.004)
        return True


def chord(*names):
    """chord("KEY_LEFTCTRL", "KEY_V"): drücken in Reihenfolge, loslassen rückwärts."""
    from evdev import ecodes as E
    codes = [getattr(E, n) for n in names]
    return send(*[(c, True) for c in codes], *[(c, False) for c in reversed(codes)])


def tap_mask():
    """Unbelegte Taste antippen, solange Super/Alt gehalten werden (siehe lin_hotkeys)."""
    threading.Thread(target=lambda: chord("KEY_F24"), daemon=True).start()
