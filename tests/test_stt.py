import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stt import is_hallucination  # noqa: E402


class HallucinationTest(unittest.TestCase):
    def test_typische_phrasen(self):
        self.assertTrue(is_hallucination("Untertitel der Amara.org-Community"))
        self.assertTrue(is_hallucination("Vielen Dank fürs Zuschauen!"))
        self.assertTrue(is_hallucination("Thanks for watching."))
        self.assertTrue(is_hallucination("Untertitel"))
        self.assertTrue(is_hallucination("Abonnieren!"))

    def test_echte_saetze_bleiben(self):
        self.assertFalse(is_hallucination("Bitte abonnieren Sie unseren Newsletter."))
        self.assertFalse(is_hallucination("Kannst du die Untertitel im Video einschalten?"))
        self.assertFalse(is_hallucination("Das Copyright liegt beim Verlag, nicht bei uns."))
        self.assertFalse(is_hallucination("Wie kann ich mich bei dem Kanal subscriben?"))
        self.assertFalse(is_hallucination(""))


if __name__ == "__main__":
    unittest.main()
