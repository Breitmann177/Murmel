"""macOS: aktive App, Leerlauf, Bildschirm aus, Standby verhindern, Autostart, Overlay-Fenster."""
import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("murmel.mac")
HERE = Path(__file__).resolve().parent
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "de.murmel.app.plist"
APP_BUNDLE = Path.home() / "Applications" / "Murmel.app"     # legt install-mac.sh an


def init(app):
    """Murmel ist eine Menüleisten-App: kein Dock-Symbol, kein Eintrag im Cmd+Tab-Umschalter."""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception as e:  # noqa: BLE001
        log.warning("Aktivierungsmodus: %s", e)


def overlay(widget):
    """Pille auf allen Schreibtischen (Spaces) und auch über Vollbild-Apps zeigen."""
    try:
        import objc
        view = objc.objc_object(c_void_p=int(widget.winId()))
        win = view.window()
        win.setCollectionBehavior_((1 << 0) | (1 << 8))   # CanJoinAllSpaces | FullScreenAuxiliary
        win.setLevel_(25)                                  # NSStatusWindowLevel: über normalen Fenstern
        win.setHidesOnDeactivate_(False)
    except Exception as e:  # noqa: BLE001
        log.warning("Overlay: %s", e)


def foreground():
    try:
        from AppKit import NSWorkspace
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def process_name(target) -> str:
    try:
        return str(target.localizedName() or "") if target is not None else ""
    except Exception:
        return ""


def window_title(target) -> str:
    # Fenstertitel anderer Apps gibt macOS nur mit "Bildschirmaufnahme"-Erlaubnis heraus.
    # Bewusst nicht angefragt -> Browser bekommen den Stil "Standard".
    return ""


def idle_seconds() -> float:
    try:
        import Quartz as Q
        return float(Q.CGEventSourceSecondsSinceLastEventType(
            Q.kCGEventSourceStateCombinedSessionState, Q.kCGAnyInputEventType))
    except Exception:
        return 0.0


def monitor_off() -> None:
    subprocess.Popen(["pmset", "displaysleepnow"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def monitor_on() -> None:
    subprocess.Popen(["caffeinate", "-u", "-t", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_caffeinate = None


def prevent_sleep(on: bool) -> None:
    """Während einer Aufnahme kein Ruhezustand (Bildschirm darf trotzdem ausgehen)."""
    global _caffeinate
    try:
        if on and _caffeinate is None:
            _caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif not on and _caffeinate is not None:
            _caffeinate.terminate()
            _caffeinate = None
    except Exception as e:  # noqa: BLE001
        log.warning("caffeinate: %s", e)


def set_autostart(on: bool) -> bool:
    """LaunchAgent: startet Murmel beim Anmelden. Über die App (wegen der Erlaubnisse)."""
    try:
        if not on:
            LAUNCH_AGENT.unlink(missing_ok=True)
            return True
        if APP_BUNDLE.exists():
            args = ["/usr/bin/open", "-a", str(APP_BUNDLE)]
        else:
            args = [sys.executable, str(HERE / "main.pyw")]
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as fh:
            plistlib.dump({"Label": "de.murmel.app", "ProgramArguments": args, "RunAtLoad": True}, fh)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Autostart: %s", e)
        return False
