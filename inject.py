"""Text an der Cursor-Position einfügen – über die Zwischenablage.

Warum nicht Buchstabe für Buchstabe tippen (SendInput mit Unicode)? Das ist bei langen Texten
langsam, und manche Apps (Spiele, Remote-Desktop, Editoren mit Autovervollständigung) verschlucken
oder verändern Zeichen. Strg+V ist überall schnell und exakt.

Ablauf: 1) ALLE Formate der Zwischenablage sichern (auch Bilder, Dateien, HTML)
        2) unseren Text hineinlegen (vom Windows-Clipboard-Verlauf ausgenommen)
        3) warten, bis Strg/Win/Alt/Shift physisch losgelassen sind
        4) Strg+V senden, kurz warten, alte Zwischenablage zurücklegen
"""
import ctypes
import logging
import time
from ctypes import wintypes

from winutil import VK_CONTROL, VK_LWIN, VK_MENU, VK_RWIN, VK_SHIFT, class_name, key_down, send_keys, user32, kernel32

log = logging.getLogger("murmel.inject")

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Formate, die keine Speicherblöcke sind (GDI-Handles) -> nicht kopierbar. Windows erzeugt
# CF_BITMAP automatisch wieder aus CF_DIB, Bilder gehen also trotzdem nicht verloren.
SKIP_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
NO_TEXT_FIELD = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

_EXCLUDE = None


def _open_clipboard():
    # Eine andere App kann die Zwischenablage gerade offen haben -> kurz erneut versuchen
    for _ in range(25):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.01)
    return False


def _alloc(data: bytes):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def save_clipboard():
    saved = []
    if not _open_clipboard():
        return None
    try:
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in SKIP_FORMATS:
                h = user32.GetClipboardData(fmt)
                if h:
                    size = kernel32.GlobalSize(h)
                    p = kernel32.GlobalLock(h)
                    if p and size:
                        saved.append((fmt, ctypes.string_at(p, size)))
                        kernel32.GlobalUnlock(h)
            fmt = user32.EnumClipboardFormats(fmt)
    finally:
        user32.CloseClipboard()
    return saved


def restore_clipboard(saved):
    if saved is None or not _open_clipboard():
        return
    try:
        user32.EmptyClipboard()
        for fmt, data in saved:
            user32.SetClipboardData(fmt, _alloc(data))   # Windows übernimmt den Speicher
    finally:
        user32.CloseClipboard()


def set_text(text: str, exclude_history=True):
    global _EXCLUDE
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, _alloc((text + "\0").encode("utf-16-le")))
        if exclude_history:
            # Diktate sollen nicht im Windows-Zwischenablageverlauf (Win+V) landen
            if _EXCLUDE is None:
                _EXCLUDE = (user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing"),
                            user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory"))
            user32.SetClipboardData(_EXCLUDE[0], _alloc(b"\0\0\0\0"))
            user32.SetClipboardData(_EXCLUDE[1], _alloc(b"\0\0\0\0"))
        return True
    finally:
        user32.CloseClipboard()


def _wait_modifiers_released(timeout=1.0):
    """Würden wir Strg+V senden, während Win noch gedrückt ist, käme Strg+Win+V an."""
    t_end = time.monotonic() + timeout
    mods = (VK_CONTROL, VK_LWIN, VK_RWIN, VK_MENU, VK_SHIFT)
    while time.monotonic() < t_end:
        if not any(key_down(vk) for vk in mods):
            return True
        time.sleep(0.01)
    return False


def paste(text: str, target_hwnd, restore_ms=220) -> str:
    """Gibt "pasted" oder "clipboard" (kein Textfeld -> Text bleibt in der Zwischenablage) zurück."""
    if not target_hwnd or class_name(target_hwnd) in NO_TEXT_FIELD:
        set_text(text, exclude_history=False)
        return "clipboard"

    # Text soll in der App landen, die beim DRÜCKEN aktiv war
    if user32.GetForegroundWindow() != target_hwnd:
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        if user32.GetForegroundWindow() != target_hwnd:
            set_text(text, exclude_history=False)
            return "clipboard"

    saved = save_clipboard()
    if not set_text(text):
        return "clipboard"
    _wait_modifiers_released()
    send_keys((VK_CONTROL, True), (0x56, True), (0x56, False), (VK_CONTROL, False))
    # Die Ziel-App liest die Zwischenablage asynchron -> kurz warten, dann zurücklegen
    time.sleep(restore_ms / 1000)
    restore_clipboard(saved)
    return "pasted"
