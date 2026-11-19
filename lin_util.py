"""Linux-Gegenstücke zu winutil.py: aktive App, Leerlaufzeit, Bildschirm aus, kein Standby, Autostart.

Wayland verrät Apps nicht, welches Fenster vorne ist. Wir fragen deshalb die Barrierefreiheits-
Schnittstelle (AT-SPI) – die kennt das aktive Fenster von GTK-, Qt- und vielen Electron-Apps.
Klappt das nicht, gilt einfach der Stil "Standard".
"""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("murmel.linux")

try:
    from jeepney import DBusAddress, MessageType, Properties, new_method_call
    from jeepney.io.blocking import open_dbus_connection
except ImportError:
    open_dbus_connection = None

_conns = {}


def _bus(which):
    """which: "SESSION" | "SYSTEM" | "A11Y" (Barrierefreiheits-Bus)."""
    if open_dbus_connection is None:
        return None
    c = _conns.get(which)
    if c is not None:
        return c
    try:
        if which == "A11Y":
            s = _bus("SESSION")
            r = s.send_and_get_reply(new_method_call(
                DBusAddress("/org/a11y/bus", "org.a11y.Bus", "org.a11y.Bus"), "GetAddress"), timeout=1)
            c = open_dbus_connection(r.body[0])
        else:
            c = open_dbus_connection(which)
    except Exception as e:  # noqa: BLE001
        log.info("D-Bus %s nicht erreichbar: %s", which, e)
        return None
    _conns[which] = c
    return c


def _call(conn, dest, path, iface, method, sig=None, body=(), timeout=0.4):
    r = conn.send_and_get_reply(new_method_call(DBusAddress(path, dest, iface), method, sig, body), timeout=timeout)
    if r.header.message_type == MessageType.error:
        raise RuntimeError(r.body[0] if r.body else "D-Bus-Fehler")
    return r.body


def _prop(conn, dest, path, iface, name):
    r = conn.send_and_get_reply(Properties(DBusAddress(path, dest, iface)).get(name), timeout=0.4)
    if r.header.message_type == MessageType.error:
        raise RuntimeError("Property")
    return r.body[0][1]


# ------------------------------------------------------------------ aktive App
STATE_ACTIVE = 1 << 1
ACC = "org.a11y.atspi.Accessible"


def foreground():
    """→ {"app": "ptyxis", "title": "…"} oder {} (wird beim Drücken gemerkt, wie das HWND unter Windows)."""
    a = _bus("A11Y")
    if a is None:
        return {}
    try:
        apps = _call(a, "org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root", ACC, "GetChildren")[0]
        for bus, path in apps:
            try:
                wins = _call(a, bus, path, ACC, "GetChildren", timeout=0.2)[0]
                for wbus, wpath in wins[:20]:
                    if _call(a, wbus, wpath, ACC, "GetState", timeout=0.2)[0][0] & STATE_ACTIVE:
                        return {"app": _prop(a, bus, path, ACC, "Name"),
                                "title": _prop(a, wbus, wpath, ACC, "Name")}
            except Exception:
                continue
    except Exception as e:  # noqa: BLE001
        log.debug("AT-SPI: %s", e)
        _conns.pop("A11Y", None)
    return {}


def process_name(target) -> str:
    return (target or {}).get("app", "") if isinstance(target, dict) else ""


def window_title(target) -> str:
    return (target or {}).get("title", "") if isinstance(target, dict) else ""


# ------------------------------------------------------------------ Leerlauf / Bildschirm
def idle_seconds() -> float:
    s = _bus("SESSION")
    if s is not None:
        try:      # GNOME
            ms = _call(s, "org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core",
                       "org.gnome.Mutter.IdleMonitor", "GetIdletime")[0]
            return ms / 1000.0
        except Exception:
            pass
    return 0.0          # unbekannt -> Bildschirm wird nie automatisch ausgeschaltet


def _mutter_power(mode):
    s = _bus("SESSION")
    if s is None:
        return False
    try:
        addr = DBusAddress("/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig",
                           "org.gnome.Mutter.DisplayConfig")
        r = s.send_and_get_reply(Properties(addr).set("PowerSaveMode", "i", mode), timeout=1)
        return r.header.message_type != MessageType.error
    except Exception:
        return False


def monitor_off() -> None:
    """Nur den Bildschirm aus (OLED schonen), Aufnahme läuft weiter."""
    if _mutter_power(3):
        return
    if shutil.which("kscreen-doctor"):
        subprocess.Popen(["kscreen-doctor", "--dpms", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def monitor_on() -> None:
    """GNOME weckt den Bildschirm nicht selbst auf, wenn wir ihn ausgeschaltet haben."""
    if _mutter_power(0):
        return
    if shutil.which("kscreen-doctor"):
        subprocess.Popen(["kscreen-doctor", "--dpms", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ kein Standby
_inhibit = None


def prevent_sleep(on: bool) -> None:
    """Während einer Aufnahme kein Standby (systemd-inhibit hält die Sperre, solange es läuft)."""
    global _inhibit
    if on and _inhibit is None and shutil.which("systemd-inhibit"):
        try:
            _inhibit = subprocess.Popen(
                ["systemd-inhibit", "--what=sleep", "--who=Murmel", "--why=Aufnahme läuft",
                 "--mode=block", "sleep", "infinity"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            _inhibit = None
    elif not on and _inhibit is not None:
        _inhibit.terminate()
        _inhibit = None


# ------------------------------------------------------------------ Autostart
AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "murmel.desktop"


def set_autostart(on: bool) -> bool:
    try:
        if on:
            main = Path(__file__).resolve().parent / "main.pyw"
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text(
                "[Desktop Entry]\nType=Application\nName=Murmel\n"
                f"Exec=\"{sys.executable}\" \"{main}\"\n"
                f"Icon={Path(__file__).resolve().parent / 'assets' / 'murmel.png'}\n"
                "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=3\nTerminal=false\n",
                encoding="utf-8")
        elif AUTOSTART.exists():
            AUTOSTART.unlink()
        return True
    except OSError:
        return False
