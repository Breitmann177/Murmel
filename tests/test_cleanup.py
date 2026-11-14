"""Tests für cleanup.py.   Ausführen:  .venv\\Scripts\\python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup import clean  # noqa: E402


class Akzeptanz(unittest.TestCase):
    def test_spec_beispiel(self):
        self.assertEqual(
            clean("Ähm, also ich wollte fragen, ob wir uns morgen um drei, nein, um vier treffen können."),
            "Ich wollte fragen, ob wir uns morgen um vier treffen können?")

    def test_denglisch_bleibt(self):
        self.assertEqual(clean("Ich muss noch den Pull Request reviewen, äh, before the deadline."),
                         "Ich muss noch den Pull Request reviewen, before the deadline.")


class Fuellwoerter(unittest.TestCase):
    def test_immer(self):
        self.assertEqual(clean("Das ist, ähm, ziemlich gut."), "Das ist, ziemlich gut.")

    def test_also_am_anfang(self):
        self.assertEqual(clean("Also das machen wir morgen."), "Das machen wir morgen.")

    def test_also_mitten_bleibt(self):
        self.assertEqual(clean("Wir treffen uns also morgen."), "Wir treffen uns also morgen.")

    def test_eingeschoben(self):
        self.assertEqual(clean("Das ist, sozusagen, der Plan."), "Das ist, der Plan.")

    def test_er_ist_im_deutschen_kein_fuellwort(self):
        self.assertEqual(clean("Er hat er gesagt."), "Er hat er gesagt.")

    def test_englisch(self):
        self.assertEqual(clean("Um, I think, uh, we should push it.", "en"), "I think, we should push it.")

    def test_englisch_so_am_anfang(self):
        self.assertEqual(clean("So we need to fix this.", "en"), "We need to fix this.")


class Korrekturen(unittest.TestCase):
    def test_einzelwort(self):
        self.assertEqual(clean("Ich komme am Montag, nein, Dienstag."), "Ich komme am Dienstag.")

    def test_anker(self):
        self.assertEqual(clean("Schick es an Max, ich meine, an Moritz."), "Schick es an Moritz.")

    def test_englisch(self):
        self.assertEqual(clean("Let's meet at five, actually, at six.", "en"), "Let's meet at six.")

    def test_echtes_nein_bleibt(self):
        self.assertEqual(clean("Er sagte, nein, das geht so nicht."), "Er sagte, nein, das geht so nicht.")

    def test_nein_am_anfang_bleibt(self):
        self.assertEqual(clean("Nein, das stimmt nicht."), "Nein, das stimmt nicht.")


class Wiederholungen(unittest.TestCase):
    def test_doppelt(self):
        self.assertEqual(clean("Ich ich wollte das sagen."), "Ich wollte das sagen.")

    def test_artikel_doppelt_erlaubt(self):
        self.assertEqual(clean("Das sind Leute, die die Regeln kennen."), "Das sind Leute, die die Regeln kennen.")


class Befehle(unittest.TestCase):
    def test_neue_zeile(self):
        self.assertEqual(clean("Hallo Max neue Zeile wie geht's"), "Hallo Max\nWie geht's")

    def test_neuer_absatz(self):
        self.assertEqual(clean("Erster Teil. Neuer Absatz. Zweiter Teil."), "Erster Teil.\n\nZweiter Teil.")

    def test_fragezeichen(self):
        self.assertEqual(clean("Kommst du morgen Fragezeichen"), "Kommst du morgen?")

    def test_punkt_am_ende(self):
        self.assertEqual(clean("Das war's Punkt"), "Das war's.")

    def test_treffpunkt_bleibt(self):
        self.assertEqual(clean("Der Treffpunkt ist am Bahnhof."), "Der Treffpunkt ist am Bahnhof.")

    def test_klammern(self):
        self.assertEqual(clean("Das Modell Klammer auf small Klammer zu ist schnell."),
                         "Das Modell (small) ist schnell.")


class Listen(unittest.TestCase):
    def test_erstens_zweitens(self):
        self.assertEqual(clean("Wir brauchen erstens Milch, zweitens Brot und drittens Käse."),
                         "Wir brauchen:\n1. Milch\n2. Brot\n3. Käse")

    def test_punkt_eins(self):
        self.assertEqual(clean("Punkt eins Folien fertig machen, Punkt zwei Mail an Prof schreiben."),
                         "1. Folien fertig machen\n2. Mail an Prof schreiben")

    def test_ein_erstens_ist_keine_liste(self):
        self.assertEqual(clean("Erstens kommt es anders."), "Erstens kommt es anders.")


class Woerterbuch(unittest.TestCase):
    def test_ersetzung(self):
        self.assertEqual(clean("Frag doch mal gepeteh.", replacements={"gepeteh": "GPT"}), "Frag doch mal GPT.")


class Fragen(unittest.TestCase):
    def test_w_frage(self):
        self.assertEqual(clean("wann kommst du nach Hause."), "Wann kommst du nach Hause?")

    def test_aussage_bleibt(self):
        self.assertEqual(clean("Ich komme um acht nach Hause."), "Ich komme um acht nach Hause.")

    def test_level_off(self):
        self.assertEqual(clean("ähm hallo", level="off"), "ähm hallo")


if __name__ == "__main__":
    unittest.main()
