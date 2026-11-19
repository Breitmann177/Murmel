"""Spracherkennung in einem EIGENEN Prozess – damit ein GPU-Wechsel Murmel nicht mitreißt.

Warum? Wird die Grafikkarte weggeschaltet (z. B. Armoury Crate: Standard -> Eco), während das
Modell auf ihr liegt, beendet der NVIDIA-Treiber den Prozess hart (Windows-Fehler 0xc0000409).
Das kann Python nicht abfangen. Läuft das Modell hier in einem Kind-Prozess, stirbt nur dieser –
Murmel selbst (Pille, Hotkey, die Aufnahme im Speicher) läuft weiter, startet den Worker neu
(dann auf der CPU) und schickt dieselbe Aufnahme noch einmal.

Hauptprozess  <-- multiprocessing.Pipe -->  Worker
  STTProxy.transcribe()  ──("transcribe", id, audio, hotwords, welches)──▶  Modell
                         ◀──────────("ok", id, (text, lang, sek))──────────
"""
import logging
import multiprocessing as mp
import threading
import time

log = logging.getLogger("murmel.stt")


class WorkerDied(Exception):
    pass


# ======================================================================= Kind-Prozess
def run(conn, cfg, log_path):
    """Läuft im Worker-Prozess. Hier (und nur hier) wird CUDA angefasst."""
    logging.basicConfig(filename=log_path, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s[worker]: %(message)s")
    import stt
    try:
        main = stt.STT(cfg)
        main.load()
        preview = None
        if main.device == "cuda":          # kleines Zweitmodell nur für die Live-Blase
            try:
                p = stt.STT({**cfg, "model_gpu": "small"})
                p.load()
                preview = p if p.device == "cuda" else None
            except Exception as e:  # noqa: BLE001
                logging.getLogger("murmel.stt").warning("Vorschau-Modell: %s", e)
        conn.send(("ready", main.device, main.model_name, preview is not None))
    except Exception as e:  # noqa: BLE001
        conn.send(("error", str(e)))
        return

    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break                           # Hauptprozess ist weg
        kind = msg[0]
        if kind == "transcribe":
            _, rid, audio, hot, which = msg
            model = preview if (which == "preview" and preview) else main
            try:
                conn.send(("ok", rid, model.transcribe(audio, hot)))
            except Exception as e:  # noqa: BLE001
                conn.send(("err", rid, str(e)))
        elif kind == "cfg":
            main.cfg.update(msg[1])
            if preview:
                preview.cfg.update(msg[1])
        elif kind == "probe":
            import ctranslate2
            conn.send(("probe", ctranslate2.get_cuda_device_count()))
        elif kind == "quit":
            break


# ===================================================================== Hauptprozess
class STTProxy:
    """Gleiche Schnittstelle wie stt.STT, aber das Modell lebt im Worker-Prozess."""

    def __init__(self, cfg, log_path, on_change=None):
        self.cfg = cfg
        self.log_path = str(log_path)
        self.on_change = on_change          # wird nach (Neu-)Start mit (device, name) gerufen
        self.device = "?"
        self.model_name = "?"
        self.has_preview = False
        self._lock = threading.Lock()       # ein Auftrag nach dem anderen
        self._proc = None
        self._conn = None
        self._rid = 0

    # ------------------------------------------------------------ Start/Stopp
    def load(self):
        """Startet den Worker und wartet, bis das Modell geladen ist (blockiert)."""
        with self._lock:
            self._start()

    def _start(self):
        ctx = mp.get_context("spawn")
        a, b = ctx.Pipe()
        self._proc = ctx.Process(target=run, args=(b, dict(self.cfg), self.log_path),
                                 daemon=True, name="murmel-stt")
        self._proc.start()
        b.close()
        self._conn = a
        msg = self._recv(timeout=900)       # erster Start kann einen Modell-Download enthalten
        if msg[0] != "ready":
            raise RuntimeError(msg[1] if len(msg) > 1 else "Worker-Start fehlgeschlagen")
        _, self.device, self.model_name, self.has_preview = msg
        log.info("Worker bereit: %s auf %s (Vorschau: %s)", self.model_name, self.device, self.has_preview)
        if self.on_change:
            self.on_change(self.device, self.model_name)

    def _kill(self):
        try:
            if self._proc and self._proc.is_alive():
                self._proc.kill()
                self._proc.join(3)
        except Exception:
            pass
        self._proc = None

    def restart(self):
        with self._lock:
            self._kill()
            self._start()

    def stop(self):
        try:
            if self._conn:
                self._conn.send(("quit",))
        except Exception:
            pass
        if self._proc:
            self._proc.join(2)
        self._kill()

    def _recv(self, timeout):
        t_end = time.monotonic() + timeout
        while True:
            try:
                if self._conn.poll(0.2):
                    return self._conn.recv()
            except (EOFError, OSError):
                raise WorkerDied("Verbindung zum Worker verloren")
            if not self._proc or not self._proc.is_alive():
                code = self._proc.exitcode if self._proc else None
                raise WorkerDied(f"Worker beendet (Code {code})")
            if time.monotonic() > t_end:
                raise TimeoutError("Worker antwortet nicht")

    # ------------------------------------------------------------- Aufträge
    def transcribe(self, audio, hotwords=None, which="main"):
        with self._lock:
            for attempt in (1, 2):
                try:
                    if not self._proc or not self._proc.is_alive():
                        raise WorkerDied("Worker läuft nicht")
                    self._rid += 1
                    rid = self._rid
                    self._conn.send(("transcribe", rid, audio, hotwords, which))
                    while True:
                        msg = self._recv(timeout=600)
                        if msg[0] in ("ok", "err") and msg[1] == rid:
                            break
                    if msg[0] == "ok":
                        return msg[2]
                    raise RuntimeError(msg[2])
                except (WorkerDied, TimeoutError) as e:
                    # z. B. GPU wurde weggeschaltet: Worker neu (dann CPU) und gleiche Aufnahme nochmal
                    log.warning("Erkennung abgestürzt (%s) – starte neu, Versuch %d", e, attempt)
                    self._kill()
                    if attempt == 2:
                        raise
                    self._start()

    def update_cfg(self, changes: dict):
        self.cfg.update(changes)
        with self._lock:
            try:
                self._conn.send(("cfg", changes))
            except Exception:
                pass

    def cuda_available(self) -> bool:
        """Fragt den Worker (nicht den Hauptprozess!), ob gerade eine GPU da ist."""
        if not self._lock.acquire(timeout=0.5):
            return False
        try:
            self._conn.send(("probe",))
            msg = self._recv(timeout=10)
            return msg[0] == "probe" and msg[1] > 0
        except Exception:
            return False
        finally:
            self._lock.release()
