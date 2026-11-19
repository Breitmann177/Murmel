"""Mac-Tastenlogik ohne Mac: handle() bekommt Tastencodes wie vom Quartz-Event-Tap."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mac_hotkeys as mk  # noqa: E402

CTRL, CMD, OPT, SPACE = 59, 55, 58, 49


class MacHook(unittest.TestCase):
    def setUp(self):
        mk.DOWN.clear()
        self.ev = []
        self.h = mk.PushToTalkHook(["ctrl", "win"], self.ev.append, command=["ctrl", "win", "alt"])

    def keys(self, *seq):
        for code, v in seq:
            self.h.handle(code, v)

    def test_diktat_ctrl_cmd(self):
        self.keys((CTRL, 1), (CMD, 1), (CMD, 0), (CTRL, 0))
        self.assertEqual(self.ev, ["press", "release"])

    def test_auto_repeat_ignoriert(self):
        self.keys((CTRL, 1), (CMD, 1), (CMD, 2), (CMD, 2), (CMD, 0), (CTRL, 0))
        self.assertEqual(self.ev, ["press", "release"])

    def test_befehl_mit_option(self):
        self.keys((CTRL, 1), (CMD, 1), (OPT, 1), (OPT, 0), (CMD, 0), (CTRL, 0))
        self.assertEqual(self.ev, ["press", "upgrade", "release"])

    def test_emoji_kuerzel_bricht_ab(self):
        self.keys((CTRL, 1), (CMD, 1), (SPACE, 1), (SPACE, 0), (CMD, 0), (CTRL, 0))
        self.assertEqual(self.ev, ["press", "other", "release"])

    def test_esc_wird_geschluckt(self):
        self.h.swallow_esc = True
        self.keys((CTRL, 1), (CMD, 1))
        self.assertTrue(self.h.handle(mk.K_ESC, 1))
        self.assertIn("esc", self.ev)


class MacStile(unittest.TestCase):
    def test_mac_app_namen(self):
        import styles
        self.assertEqual(styles.style_for("Microsoft Outlook", "", {}), "formal")
        self.assertEqual(styles.style_for("Nachrichten", "", {}), "casual")
        self.assertEqual(styles.style_for("Terminal", "", {}), "code")
        self.assertEqual(styles.style_for("Safari", "", {}), "standard")


if __name__ == "__main__":
    unittest.main()
