"""Linux: globaler Push-to-Talk über evdev (liest die Tastatur direkt, geht unter Wayland und X11).

Warum evdev? Wayland erlaubt Apps keine globalen Tasten-Hooks, und Portale melden kein Loslassen
zuverlässig. evdev liest /dev/input/event* – dafür braucht der Nutzer Leserechte (Gruppe "input"
oder die udev-Regel aus install.sh). Gelesen wird nur, ob die eingestellte Kombination gedrückt
ist; es wird nichts gespeichert und die Tastatur wird NICHT exklusiv gegriffen.

Unterschiede zu Windows:
- Esc kann nicht "geschluckt" werden (die App bekommt es auch).
- Win/Super loslassen öffnet unter GNOME die Übersicht. Dagegen tippen wir beim Start der Aufnahme
  über uinput kurz eine unbelegte Taste (F24) – dann gilt Super als "Teil einer Kombination".

Ereignisse an den Callback wie unter Windows: "press", "release", "command_press", "upgrade",
"other", "esc", "hook_failed".
"""
import select
import threading
import time

import lin_keys

try:
    import evdev
    from evdev import ecodes as E
except ImportError:      # ohne evdev kein Hotkey (install.sh installiert es)
    evdev = None
    E = None


def _groups():
    if E is None:
        return {}
    return {
        "ctrl": {E.KEY_LEFTCTRL, E.KEY_RIGHTCTRL},
        "win": {E.KEY_LEFTMETA, E.KEY_RIGHTMETA},
        "alt": {E.KEY_LEFTALT, E.KEY_RIGHTALT},
        "shift": {E.KEY_LEFTSHIFT, E.KEY_RIGHTSHIFT},
        "rctrl": {E.KEY_RIGHTCTRL},
    }


GROUPS = _groups()
DOWN = set()          # aktuell gedrückte Tasten (für "warten bis Strg/Super losgelassen")


def modifiers_down():
    if E is None:
        return False
    mods = set().union(*(GROUPS[g] for g in ("ctrl", "win", "alt", "shift")))
    return bool(DOWN & mods)


class PushToTalkHook(threading.Thread):
    def __init__(self, combo, callback, command=None):
        super().__init__(daemon=True, name="kbd-hook")
        self.combos = {"dictate": [GROUPS[g] for g in combo]} if GROUPS else {}
        if command and GROUPS:
            self.combos["command"] = [GROUPS[g] for g in command]
        self.vks = {n: set().union(*gs) for n, gs in self.combos.items()}
        self.uses_win = any(GROUPS.get("win", set()) & v for v in self.vks.values())
        self.callback = callback
        self.enabled = True
        self.swallow_esc = False
        self._active = None
        self._stop = threading.Event()
        self._devices = {}

    # ------------------------------------------------------------ Logik
    def _satisfied(self, name):
        return name in self.combos and all(DOWN & g for g in self.combos[name])

    def _emit(self, ev):
        try:
            self.callback(ev)
        except Exception:
            pass

    def _mask(self):
        # Super/Alt wurde Teil einer Kombination -> GNOME-Übersicht / Menüleiste bleiben zu
        if self.uses_win or (E and DOWN & GROUPS["alt"]):
            lin_keys.tap_mask()

    def handle(self, code, value):
        """value: 1 = gedrückt, 0 = losgelassen, 2 = Auto-Repeat (ignoriert)."""
        if value == 2:
            return
        if value == 1:
            DOWN.add(code)
            if not self.enabled:
                return
            if code == E.KEY_ESC and self.swallow_esc:
                self._emit("esc")
                return
            if self._active is None:
                if self._satisfied("command"):
                    self._active = "command"
                    self._mask()
                    self._emit("command_press")
                elif self._satisfied("dictate"):
                    self._active = "dictate"
                    self._mask()
                    self._emit("press")
            elif self._active == "dictate" and self._satisfied("command"):
                self._active = "command"
                self._mask()
                self._emit("upgrade")
            elif code not in self.vks[self._active]:
                self._emit("other")
        elif value == 0:
            DOWN.discard(code)
            if self._active and code in self.vks[self._active]:
                self._active = None
                self._emit("release")

    # ------------------------------------------------------------ Geräte
    def _scan(self):
        """Alle echten Tastaturen öffnen (nicht unser eigenes uinput-Gerät)."""
        found = {}
        for path in evdev.list_devices():
            if path in self._devices:
                found[path] = self._devices[path]
                continue
            try:
                d = evdev.InputDevice(path)
            except OSError:
                continue
            keys = d.capabilities().get(E.EV_KEY, [])
            if d.name == lin_keys.DEVICE_NAME or E.KEY_A not in keys or E.KEY_LEFTCTRL not in keys:
                d.close()
                continue
            found[path] = d
        for path, d in self._devices.items():
            if path not in found:
                try:
                    d.close()
                except Exception:
                    pass
        self._devices = found

    def run(self):
        if evdev is None or not self.combos:
            self._emit("hook_failed")
            return
        self._scan()
        if not self._devices:
            self._emit("hook_failed")      # keine Leserechte auf /dev/input
        last_scan = time.monotonic()
        while not self._stop.is_set():
            if time.monotonic() - last_scan > 3:       # USB-Tastatur an-/abgesteckt?
                self._scan()
                last_scan = time.monotonic()
            fds = {d.fd: d for d in self._devices.values()}
            if not fds:
                time.sleep(1)
                continue
            try:
                ready, _, _ = select.select(list(fds), [], [], 1.0)
            except (OSError, ValueError):
                self._scan()
                continue
            for fd in ready:
                d = fds[fd]
                try:
                    for ev in d.read():
                        if ev.type == E.EV_KEY:
                            self.handle(ev.code, ev.value)
                except OSError:              # Gerät abgesteckt
                    self._scan()
                    break
        for d in self._devices.values():
            try:
                d.close()
            except Exception:
                pass

    def stop(self):
        self._stop.set()
