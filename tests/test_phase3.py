"""Stile, Snippets/Wörterbuch und Hook-Logik (ohne echte Tastatur)."""
import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import styles  # noqa: E402


class Stile(unittest.TestCase):
    def test_discord_kurz_ohne_punkt(self):
        st = styles.style_for("Discord.exe", "", {})
        self.assertEqual(st, "casual")
        self.assertEqual(styles.apply("Bin gleich da.", st), "Bin gleich da")

    def test_locker_frage_bleibt(self):
        self.assertEqual(styles.apply("Kommst du heute?", "casual"), "Kommst du heute?")

    def test_locker_mehrere_saetze_behalten_punkt(self):
        self.assertEqual(styles.apply("Bin da. Komm rein.", "casual"), "Bin da. Komm rein.")

    def test_outlook_formell(self):
        st = styles.style_for("OUTLOOK.EXE", "", {})
        self.assertEqual(st, "formal")
        self.assertEqual(styles.apply("Vielen Dank für Ihre Mail", st), "Vielen Dank für Ihre Mail.")

    def test_gmail_im_browser(self):
        self.assertEqual(styles.style_for("chrome.exe", "Posteingang - Gmail", {}), "formal")
        self.assertEqual(styles.style_for("chrome.exe", "WhatsApp", {}), "casual")

    def test_code_klein(self):
        self.assertEqual(styles.apply("Fix the login bug", "code"), "fix the login bug")

    def test_code_akronym_und_woerterbuch(self):
        self.assertEqual(styles.apply("API Key erneuern", "code"), "API Key erneuern")
        self.assertEqual(styles.apply("Murmel starten", "code", ["Murmel"]), "Murmel starten")

    def test_eigene_zuordnung(self):
        self.assertEqual(styles.style_for("notion.exe", "", {"notion": "formal"}), "formal")


class Speicher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import config
        cls.tmp = tempfile.mkdtemp()
        config.APP_DIR = Path(cls.tmp)
        import storage
        storage.DB_PATH = Path(cls.tmp) / "t.db"
        storage._local.con = None
        cls.s = storage

    def test_snippet_ganze_aufnahme(self):
        self.s.add_snippet("meine Signatur", "Viele Grüße\nMax")
        self.assertEqual(self.s.match_snippet("Meine Signatur."), "Viele Grüße\nMax")
        self.assertIsNone(self.s.match_snippet("Schick mir meine Signatur"))

    def test_woerterbuch(self):
        self.s.add_dictionary("GPT", "gepeteh")
        self.s.add_dictionary("Musterstadt")
        self.assertEqual(self.s.replacements()["gepeteh"], "GPT")
        self.assertIn("Musterstadt", self.s.hotwords())


class Hook(unittest.TestCase):
    def setUp(self):
        import hotkeys
        self.hk = hotkeys
        self.sent = []
        hotkeys.send_keys = lambda *ev: self.sent.append(ev)
        self.ev = []
        self.h = hotkeys.PushToTalkHook(["ctrl", "win"], self.ev.append, command=["ctrl", "win", "alt"])

    def key(self, vk, down):
        s = self.hk.KBDLLHOOKSTRUCT(vk, 0, 0, 0, 0)
        return self.h._hook(0, self.hk.WM_KEYDOWN if down else self.hk.WM_KEYUP, ctypes.addressof(s))

    def test_diktat(self):
        for vk, d in ((0xA2, 1), (0x5B, 1), (0x5B, 0), (0xA2, 0)):
            self.key(vk, d)
        self.assertEqual(self.ev, ["press", "release"])

    def test_upgrade_zu_befehl(self):
        for vk, d in ((0xA2, 1), (0x5B, 1), (0xA4, 1), (0xA4, 0), (0x5B, 0), (0xA2, 0)):
            self.key(vk, d)
        self.assertEqual(self.ev, ["press", "upgrade", "release"])
        self.assertEqual(len(self.sent), 2)      # Alt-Up und Win-Up maskiert

    def test_befehl_direkt(self):
        for vk, d in ((0xA4, 1), (0xA2, 1), (0x5B, 1), (0x5B, 0), (0xA2, 0), (0xA4, 0)):
            self.key(vk, d)
        self.assertEqual(self.ev, ["command_press", "release"])

    def test_windows_kuerzel_bricht_ab(self):
        for vk, d in ((0xA2, 1), (0x5B, 1), (0x44, 1), (0x44, 0), (0x5B, 0), (0xA2, 0)):
            self.key(vk, d)
        self.assertEqual(self.ev, ["press", "other", "release"])


if __name__ == "__main__":
    unittest.main()
