"""Linux-Hook-Logik (evdev-Codes, ohne echte Tastatur)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import evdev  # noqa: F401
    HAVE_EVDEV = sys.platform != "win32"
except ImportError:
    HAVE_EVDEV = False


@unittest.skipUnless(HAVE_EVDEV, "nur Linux mit evdev")
class LinuxHook(unittest.TestCase):
    def setUp(self):
        import lin_hotkeys
        import lin_keys
        from evdev import ecodes as E
        self.E = E
        self.masks = []
        lin_keys.tap_mask = lambda: self.masks.append(1)
        lin_hotkeys.DOWN.clear()
        self.ev = []
        self.h = lin_hotkeys.PushToTalkHook(["ctrl", "win"], self.ev.append, command=["ctrl", "win", "alt"])

    def keys(self, *seq):
        for code, v in seq:
            self.h.handle(code, v)

    def test_diktat(self):
        E = self.E
        self.keys((E.KEY_LEFTCTRL, 1), (E.KEY_LEFTMETA, 1), (E.KEY_LEFTMETA, 2), (E.KEY_LEFTMETA, 0),
                  (E.KEY_LEFTCTRL, 0))
        self.assertEqual(self.ev, ["press", "release"])
        self.assertEqual(len(self.masks), 1)       # GNOME-Übersicht unterdrückt

    def test_upgrade_zu_befehl(self):
        E = self.E
        self.keys((E.KEY_LEFTCTRL, 1), (E.KEY_LEFTMETA, 1), (E.KEY_LEFTALT, 1), (E.KEY_LEFTALT, 0),
                  (E.KEY_LEFTMETA, 0), (E.KEY_LEFTCTRL, 0))
        self.assertEqual(self.ev, ["press", "upgrade", "release"])

    def test_befehl_direkt(self):
        E = self.E
        self.keys((E.KEY_LEFTALT, 1), (E.KEY_LEFTCTRL, 1), (E.KEY_LEFTMETA, 1), (E.KEY_LEFTMETA, 0),
                  (E.KEY_LEFTCTRL, 0), (E.KEY_LEFTALT, 0))
        self.assertEqual(self.ev, ["command_press", "release"])

    def test_andere_taste_bricht_ab(self):
        E = self.E
        self.keys((E.KEY_LEFTCTRL, 1), (E.KEY_LEFTMETA, 1), (E.KEY_D, 1), (E.KEY_D, 0),
                  (E.KEY_LEFTMETA, 0), (E.KEY_LEFTCTRL, 0))
        self.assertEqual(self.ev, ["press", "other", "release"])

    def test_esc_waehrend_aufnahme(self):
        E = self.E
        self.h.swallow_esc = True
        self.keys((E.KEY_ESC, 1), (E.KEY_ESC, 0))
        self.assertEqual(self.ev, ["esc"])

    def test_pausiert(self):
        E = self.E
        self.h.enabled = False
        self.keys((E.KEY_LEFTCTRL, 1), (E.KEY_LEFTMETA, 1), (E.KEY_LEFTMETA, 0), (E.KEY_LEFTCTRL, 0))
        self.assertEqual(self.ev, [])


if __name__ == "__main__":
    unittest.main()
