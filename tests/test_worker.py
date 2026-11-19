"""Absturz-Test: Worker-Prozess wird mitten in der Erkennung hart beendet (wie beim GPU-Wechsel).
Murmel muss den Worker neu starten und trotzdem ein Ergebnis liefern.

Langsam (lädt ein echtes Modell) – nur mit  MURMEL_SLOW_TESTS=1  aktiv."""
import os
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(os.environ.get("MURMEL_SLOW_TESTS"), "langsamer Test")
class WorkerAbsturz(unittest.TestCase):
    def test_worker_stirbt_mitten_drin(self):
        import config
        from stt_worker import STTProxy
        cfg = dict(config.DEFAULTS)
        cfg["model_gpu"] = cfg["model_cpu"] = "small"
        p = STTProxy(cfg, os.path.join(tempfile.mkdtemp(), "w.log"))
        p.load()
        audio = (np.random.randn(16000 * 6) * 0.01).astype(np.float32)

        # Fall 1: Worker stirbt direkt nachdem der Auftrag rausging (GPU weg mitten in der Erkennung)
        first_pid = p._proc.pid
        conn = p._conn
        orig_send = conn.send

        def send_then_kill(msg):
            orig_send(msg)
            if msg[0] == "transcribe":
                os.kill(first_pid, 9)
        conn.send = send_then_kill
        t0 = time.time()
        text, lang, dt = p.transcribe(audio)
        self.assertNotEqual(p._proc.pid, first_pid)     # neuer Worker hat geantwortet
        self.assertIn(lang, ("de", "en"))
        print(f"\nFall 1 erholt nach {time.time() - t0:.1f}s, Gerät jetzt: {p.device}")

        # Fall 2: Worker ist im Leerlauf gestorben, nächstes Diktat kommt
        second_pid = p._proc.pid
        os.kill(second_pid, 9)
        time.sleep(0.5)
        text, lang, dt = p.transcribe(audio)
        self.assertNotEqual(p._proc.pid, second_pid)
        print(f"Fall 2 erholt, Gerät jetzt: {p.device}")
        p.stop()


if __name__ == "__main__":
    unittest.main()
