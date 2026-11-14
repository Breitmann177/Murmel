"""Globaler Push-to-Talk über einen Low-Level-Keyboard-Hook (WH_KEYBOARD_LL).

Warum nicht RegisterHotKey wie in NoTime? RegisterHotKey meldet nur "gedrückt", nie
"losgelassen". Für Halten-zum-Sprechen brauchen wir beides, also hängen wir uns direkt in
den Tastatur-Datenstrom. Der Hook braucht einen eigenen Thread mit Message-Loop, und der
Callback muss schnell zurückkehren (Windows entfernt Hooks, die > ~300 ms brauchen).

Ereignisse an den Callback: "press", "release", "other" (andere Taste während des Haltens,
z. B. Strg+Win+D = Windows-Kürzel -> abbrechen), "esc".
"""
import ctypes
import threading
from ctypes import wintypes

from winutil import LRESULT, ULONG_PTR, VK_ESCAPE, VK_LWIN, VK_MASK, VK_RWIN, send_keys, user32, kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 0x100, 0x101, 0x104, 0x105, 0x12
LLKHF_INJECTED = 0x10

GROUPS = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "win": {VK_LWIN, VK_RWIN},
    "alt": {0x12, 0xA4, 0xA5},
    "shift": {0x10, 0xA0, 0xA1},
    "rctrl": {0xA3},
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class PushToTalkHook(threading.Thread):
    def __init__(self, combo, callback):
        super().__init__(daemon=True, name="kbd-hook")
        self.groups = [GROUPS[g] for g in combo]
        self.combo_vks = set().union(*self.groups)
        self.callback = callback
        self.enabled = True
        self.swallow_esc = False       # nur während der Aufnahme schlucken wir Esc
        self._down = set()
        self._active = False
        self._mask_win = False
        self._tid = None
        self._proc = HOOKPROC(self._hook)   # Referenz halten, sonst räumt Python sie weg!

    def _satisfied(self):
        return all(self._down & g for g in self.groups)

    def _emit(self, ev):
        try:
            self.callback(ev)
        except Exception:
            pass

    def _hook(self, n_code, w_param, l_param):
        if n_code == 0:
            k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            # Selbst erzeugte (injizierte) Tasten ignorieren – z. B. unser eigenes Strg+V
            if not (k.flags & LLKHF_INJECTED):
                vk = k.vkCode
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    repeat = vk in self._down          # gehaltene Taste = Auto-Repeat
                    self._down.add(vk)
                    if not repeat and self.enabled:
                        if vk == VK_ESCAPE and self.swallow_esc:
                            self._emit("esc")
                            return 1                     # Esc nicht an die App weitergeben
                        if not self._active and self._satisfied():
                            self._active = True
                            self._emit("press")
                        elif self._active and vk not in self.combo_vks:
                            self._emit("other")
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    self._down.discard(vk)
                    if self._active and vk in self.combo_vks:
                        self._active = False
                        self._mask_win = bool(self.combo_vks & {VK_LWIN, VK_RWIN})
                        self._emit("release")
                    if vk in (VK_LWIN, VK_RWIN) and self._mask_win:
                        # Win losgelassen öffnet sonst das Startmenü (egal ob Win zuerst oder
                        # zuletzt losgelassen wird). Trick wie bei AutoHotkey: echtes Win-Up
                        # schlucken, dann "Maskentaste" + Win-Up selbst senden.
                        self._mask_win = False
                        send_keys((VK_MASK, True), (VK_MASK, False), (vk, False))
                        return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                        kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self._emit("hook_failed")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
