"""macOS: globaler Push-to-Talk über einen Quartz-Event-Tap.

Standard-Kürzel auf dem Mac: Ctrl + Cmd halten (in der App heißt "win" = Cmd ⌘).
Der Event-Tap braucht die Erlaubnis unter Systemeinstellungen → Datenschutz & Sicherheit →
"Bedienungshilfen" (und je nach macOS-Version "Eingabeüberwachung") für Murmel.app.
Gelesen wird nur, ob die eingestellte Kombination gedrückt ist – es wird nichts gespeichert.

Ereignisse an den Callback wie unter Windows/Linux: "press", "release", "command_press",
"upgrade", "other", "esc", "hook_failed".

Die Logik (handle) kennt keine Mac-Bibliotheken – sie lässt sich daher auch unter Windows testen.
Quartz wird erst in run() geladen.
"""
import threading

# Mac-Tastencodes (kVK_*)
K_ESC = 53
K_V, K_C = 9, 8
# Modifier: Tastencode -> geräteabhängiges Flag-Bit (links/rechts getrennt, aus IOLLEvent.h)
DEVICE_MASK = {
    59: 0x00000001,   # Ctrl links
    62: 0x00002000,   # Ctrl rechts
    56: 0x00000002,   # Shift links
    60: 0x00000004,   # Shift rechts
    55: 0x00000008,   # Cmd links
    54: 0x00000010,   # Cmd rechts
    58: 0x00000020,   # Option links
    61: 0x00000040,   # Option rechts
}
GROUPS = {
    "ctrl": {59, 62},
    "win": {55, 54},          # auf dem Mac ist "win" die Cmd-Taste
    "alt": {58, 61},          # Option
    "shift": {56, 60},
    "rctrl": {62},
}
# Unsere eigenen Tastendrücke (Cmd+V) tragen diese Markierung und werden ignoriert
MAGIC = 0x4D524D4C            # "MRML"
FLAG_MASK_ALL_MODS = 0x00040000 | 0x00100000 | 0x00080000 | 0x00020000  # Ctrl|Cmd|Option|Shift
DOWN = set()


def modifiers_down():
    """Sind gerade Ctrl/Cmd/Option/Shift physisch gedrückt? (Vor Cmd+V warten wir darauf.)"""
    try:
        import Quartz
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
        return bool(flags & FLAG_MASK_ALL_MODS)
    except Exception:
        return bool(DOWN & set(DEVICE_MASK))


class PushToTalkHook(threading.Thread):
    def __init__(self, combo, callback, command=None):
        super().__init__(daemon=True, name="kbd-hook")
        self.combos = {"dictate": [GROUPS[g] for g in combo]}
        if command:
            self.combos["command"] = [GROUPS[g] for g in command]
        self.vks = {n: set().union(*gs) for n, gs in self.combos.items()}
        self.callback = callback
        self.enabled = True
        self.swallow_esc = False
        self._active = None
        self._tap = None
        self._loop = None

    # ------------------------------------------------------------ Logik
    def _satisfied(self, name):
        return name in self.combos and all(DOWN & g for g in self.combos[name])

    def _emit(self, ev):
        try:
            self.callback(ev)
        except Exception:
            pass

    def handle(self, code, value):
        """value: 1 = gedrückt, 0 = losgelassen, 2 = Auto-Repeat (ignoriert).
        Rückgabe True = Taste schlucken (nur Esc während der Aufnahme)."""
        if value == 2:
            return False
        if value == 1:
            DOWN.add(code)
            if not self.enabled:
                return False
            if code == K_ESC and self.swallow_esc:
                self._emit("esc")
                return True
            if self._active is None:
                if self._satisfied("command"):
                    self._active = "command"
                    self._emit("command_press")
                elif self._satisfied("dictate"):
                    self._active = "dictate"
                    self._emit("press")
            elif self._active == "dictate" and self._satisfied("command"):
                self._active = "command"
                self._emit("upgrade")
            elif code not in self.vks[self._active]:
                self._emit("other")      # z. B. Ctrl+Cmd+Leertaste = Emoji-Auswahl -> abbrechen
        elif value == 0:
            DOWN.discard(code)
            if self._active and code in self.vks[self._active]:
                self._active = None
                self._emit("release")
        return False

    # ------------------------------------------------------------ Quartz
    def run(self):
        try:
            import Quartz
        except ImportError:
            self._emit("hook_failed")
            return
        Q = Quartz

        def cb(proxy, etype, event, refcon):
            # macOS schaltet Taps ab, wenn sie zu langsam sind -> sofort wieder an
            if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                Q.CGEventTapEnable(self._tap, True)
                return event
            if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == MAGIC:
                return event                              # unser eigenes Cmd+V
            code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
            if etype == Q.kCGEventFlagsChanged:
                bit = DEVICE_MASK.get(code)
                if bit is None:
                    return event
                value = 1 if (Q.CGEventGetFlags(event) & bit) else 0
            elif etype == Q.kCGEventKeyDown:
                value = 2 if Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat) else 1
            else:
                value = 0
            return None if self.handle(code, value) else event

        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
                | Q.CGEventMaskBit(Q.kCGEventFlagsChanged))
        self._tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                       Q.kCGEventTapOptionDefault, mask, cb, None)
        if not self._tap:                 # keine Bedienungshilfen-Erlaubnis
            self._emit("hook_failed")
            return
        src = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, src, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        Q.CFRunLoopRun()

    def stop(self):
        try:
            import Quartz
            if self._loop is not None:
                Quartz.CFRunLoopStop(self._loop)
        except Exception:
            pass
