"""macOS: Text einfügen über die Zwischenablage + Cmd+V (wie unter Windows, nur mit Mac-APIs).

Ablauf: alle Formate der Zwischenablage sichern -> Text hinein (als "vorübergehend" markiert,
damit Clipboard-Manager ihn nicht speichern) -> warten bis Ctrl/Cmd losgelassen -> Cmd+V senden
-> kurz warten -> alte Zwischenablage zurück. Cmd+V senden braucht die Bedienungshilfen-Erlaubnis.
"""
import logging
import time

import mac_hotkeys

log = logging.getLogger("murmel.inject")

STRING = "public.utf8-plain-text"
# Markierungen nach nspasteboard.org: Clipboard-Manager speichern so etwas nicht
TRANSIENT = "org.nspasteboard.TransientType"


def init():
    pass


def _pb():
    from AppKit import NSPasteboard
    return NSPasteboard.generalPasteboard()


def save_clipboard():
    saved = []
    try:
        for item in _pb().pasteboardItems() or []:
            d = {}
            for t in item.types():
                data = item.dataForType_(t)
                if data is not None:
                    d[str(t)] = data
            saved.append(d)
    except Exception as e:  # noqa: BLE001
        log.warning("Zwischenablage sichern: %s", e)
    return saved


def restore_clipboard(saved):
    try:
        from AppKit import NSPasteboardItem
        pb = _pb()
        pb.clearContents()
        items = []
        for d in saved or []:
            it = NSPasteboardItem.alloc().init()
            for t, data in d.items():
                it.setData_forType_(data, t)
            items.append(it)
        if items:
            pb.writeObjects_(items)
    except Exception as e:  # noqa: BLE001
        log.warning("Zwischenablage zurücklegen: %s", e)


def set_text(text: str, exclude_history=True):
    pb = _pb()
    pb.clearContents()
    types = [STRING, TRANSIENT] if exclude_history else [STRING]
    pb.declareTypes_owner_(types, None)
    pb.setString_forType_(text, STRING)
    if exclude_history:
        pb.setString_forType_("", TRANSIENT)
    return True


def get_text():
    try:
        return str(_pb().stringForType_(STRING) or "")
    except Exception:
        return ""


def _wait_modifiers_released(timeout=1.0):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if not mac_hotkeys.modifiers_down():
            return True
        time.sleep(0.01)
    return False


def _cmd(keycode):
    """Cmd + Taste senden; markiert, damit unser eigener Hook es ignoriert."""
    import Quartz as Q
    src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        ev = Q.CGEventCreateKeyboardEvent(src, keycode, down)
        Q.CGEventSetFlags(ev, Q.kCGEventFlagMaskCommand)
        Q.CGEventSetIntegerValueField(ev, Q.kCGEventSourceUserData, mac_hotkeys.MAGIC)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)


def _activate(target):
    """Die App, die beim DRÜCKEN vorne war, wieder nach vorne holen (falls inzwischen gewechselt)."""
    try:
        if target is not None and not target.isActive():
            from AppKit import NSApplicationActivateIgnoringOtherApps
            target.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            time.sleep(0.15)
    except Exception:
        pass


def paste(text: str, target, restore_ms=220) -> str:
    if target is None:
        set_text(text, exclude_history=False)
        return "clipboard"
    _activate(target)
    saved = save_clipboard()
    set_text(text)
    _wait_modifiers_released()
    _cmd(mac_hotkeys.K_V)
    time.sleep(restore_ms / 1000)            # Ziel-App liest die Zwischenablage asynchron
    restore_clipboard(saved)
    return "pasted"


def copy_selection(timeout=0.6) -> str:
    """Markierten Text holen (Command Mode): sichern, leeren, Cmd+C, warten, zurücklegen."""
    saved = save_clipboard()
    pb = _pb()
    pb.clearContents()
    before = pb.changeCount()
    _wait_modifiers_released()
    _cmd(mac_hotkeys.K_C)
    text, t_end = "", time.monotonic() + timeout
    while time.monotonic() < t_end:
        time.sleep(0.03)
        if pb.changeCount() != before:
            text = get_text()
            if text:
                break
    restore_clipboard(saved)
    return text
