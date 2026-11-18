"""Spracherkennung mit faster-whisper. Das Modell wird EINMAL beim Start geladen und bleibt
im Speicher (NoTime lädt pro Aufnahme neu – beim Diktieren wären das jedes Mal Sekunden).

GPU zuerst (CUDA, float16), sonst automatisch CPU (int8). float16 halbiert auf der GPU
Speicher und Rechenzeit fast ohne Qualitätsverlust; auf der CPU ist int8 der schnellste Typ.
"""
import logging
import os
import re
import time

import numpy as np

log = logging.getLogger("murmel.stt")


def _setup_cuda_dlls():
    """cuBLAS/cuDNN kommen als pip-Pakete (nvidia-*-cu12) mit. Windows findet deren DLLs nicht von
    selbst – also die bin-Ordner in den Suchpfad hängen, BEVOR ctranslate2 sie lädt.
    Linux: LD_LIBRARY_PATH wirkt nur beim Programmstart, deshalb die .so-Dateien vorab laden."""
    if os.name != "nt":
        _preload_cuda_libs()
        return
    try:
        import site
        for sp in site.getsitepackages():
            for sub in ("cublas", "cudnn", "cuda_nvrtc"):
                d = os.path.join(sp, "nvidia", sub, "bin")
                if os.path.isdir(d):
                    os.add_dll_directory(d)
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:  # noqa: BLE001
        log.warning("CUDA-Pfade: %s", e)



def _preload_cuda_libs():
    import ctypes
    import glob
    import site
    try:
        dirs = site.getsitepackages()
    except Exception:  # noqa: BLE001
        return
    for sp in dirs:
        for pattern in ("cublas/lib/libcublasLt.so.*", "cublas/lib/libcublas.so.*",
                        "cudnn/lib/libcudnn*.so.*"):
            for lib in sorted(glob.glob(os.path.join(sp, "nvidia", pattern))):
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


_setup_cuda_dlls()

# Typische Whisper-Halluzinationen bei Stille (aus NoTime übernommen).
# Eindeutige Phrasen: tauchen sie in einem kurzen Text auf, ist er erfunden.
HALLUCINATIONS = (
    "untertitel im auftrag", "untertitel der amara", "untertitelung", "amara.org",
    "vielen dank fürs zuschauen", "vielen dank für's zuschauen", "danke fürs zuschauen",
    "thanks for watching", "swr 20", "ard text", "zdf 20",
)
# Einzelwörter, die auch in echten Diktaten vorkommen ("Bitte abonnieren Sie den Newsletter").
# Nur verwerfen, wenn der ganze Text kaum mehr als dieses Wort ist.
HALLUCINATION_WORDS = ("untertitel", "copyright", "abonnieren", "subscribe")


def is_hallucination(text: str) -> bool:
    t = text.lower().strip()
    if not t or len(t) >= 90:
        return False
    if any(h in t for h in HALLUCINATIONS):
        return True
    words = re.findall(r"\w+", t)
    return len(words) <= 4 and any(w in t for w in HALLUCINATION_WORDS)


class STT:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None
        self.device = "?"
        self.model_name = "?"

    # ------------------------------------------------------------- Laden
    def load(self):
        from faster_whisper import WhisperModel
        import ctranslate2

        attempts = []
        if ctranslate2.get_cuda_device_count() > 0:
            attempts.append((self.cfg["model_gpu"], "cuda", "float16"))
        attempts.append((self.cfg["model_cpu"], "cpu", "int8"))

        last_err = None
        for name, device, ctype in attempts:
            for local_only in (True, False):   # erst offline (schnell), sonst Download
                try:
                    t0 = time.perf_counter()
                    kw = {"cpu_threads": min(8, os.cpu_count() or 4)} if device == "cpu" else {}
                    self.model = WhisperModel(name, device=device, compute_type=ctype,
                                              local_files_only=local_only, **kw)
                    self.device, self.model_name = device, name
                    log.info("Modell %s auf %s (%s) geladen in %.1fs", name, device, ctype,
                             time.perf_counter() - t0)
                    self._warmup()
                    return
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    log.warning("Laden fehlgeschlagen (%s/%s, offline=%s): %s",
                                name, device, local_only, e)
        raise RuntimeError(f"Kein Modell ladbar: {last_err}")

    def _warmup(self):
        # Erster Aufruf ist langsam (Kernels, Speicher). 1 s Stille "wärmt" alles vor.
        t0 = time.perf_counter()
        list(self.model.transcribe(np.zeros(16000, np.float32), language="de", beam_size=1,
                                   vad_filter=False)[0])
        log.info("Warm-up %.2fs", time.perf_counter() - t0)

    # ----------------------------------------------------------- Erkennen
    def pick_language(self, audio):
        mode = self.cfg.get("language", "auto")
        if mode in ("de", "en"):
            return mode
        # Whisper kennt ~100 Sprachen. Wir fragen nach allen Wahrscheinlichkeiten und
        # entscheiden NUR zwischen Deutsch und Englisch – so wird Denglisch nie zu Niederländisch.
        try:
            _, _, probs = self.model.detect_language(audio=audio)
            p = dict(probs)
            return "de" if p.get("de", 0) >= p.get("en", 0) else "en"
        except Exception:
            return "de"

    def transcribe(self, audio: np.ndarray, hotwords: str | None = None):
        """Kurze Diktate (≤ 28 s): schneller Ein-Pass-Weg. Länger (Freihand): normaler Weg."""
        if len(audio) <= 28 * 16000:
            try:
                return self._transcribe_single_pass(audio, hotwords)
            except Exception as e:  # noqa: BLE001
                log.warning("Ein-Pass-Weg fehlgeschlagen, nehme Standardweg: %s", e)
        return self._transcribe_standard(audio, hotwords)

    def _transcribe_single_pass(self, audio, hotwords):
        """Whisper rechnet den Encoder immer über ein 30-s-Fenster – das ist der teure Teil.
        model.transcribe() würde ihn für die Spracherkennung UND fürs Dekodieren je einmal
        rechnen. Hier: einmal encodieren, Ergebnis für beides nutzen (spart ~45 % auf der CPU)."""
        from faster_whisper.audio import pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        t0 = time.perf_counter()
        m = self.model
        # 1) Stille vorne/hinten abschneiden (Silero-VAD, sehr schnell)
        ts = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=400, speech_pad_ms=250))
        if not ts:
            return "", "de", time.perf_counter() - t0
        audio = audio[ts[0]["start"]: ts[-1]["end"]]

        # 2) EIN Encoder-Durchlauf
        feats = pad_or_trim(m.feature_extractor(audio))
        enc = m.encode(feats)

        # 3) Sprache aus demselben Encoder-Ergebnis – nur DE oder EN zulassen
        mode = self.cfg.get("language", "auto")
        if mode in ("de", "en"):
            lang = mode
        else:
            probs = dict(m.model.detect_language(enc)[0])
            lang = "de" if probs.get("<|de|>", 0) >= probs.get("<|en|>", 0) else "en"

        # 4) Dekodieren
        tok = Tokenizer(m.hf_tokenizer, m.model.is_multilingual, task="transcribe", language=lang)
        prompt = m.get_prompt(tok, [], without_timestamps=True, hotwords=hotwords or None)
        res = m.model.generate(enc, [prompt], beam_size=int(self.cfg.get("beam_size", 1)),
                               max_length=448, return_scores=True, return_no_speech_prob=True,
                               suppress_blank=True, suppress_tokens=[-1])[0]
        text = tok.decode(res.sequences_ids[0]).strip()
        if res.no_speech_prob > 0.6 and res.scores[0] < -0.8:
            text = ""
        if is_hallucination(text):
            text = ""
        return text, lang, time.perf_counter() - t0

    def _transcribe_standard(self, audio, hotwords):
        t0 = time.perf_counter()
        lang = self.pick_language(audio)
        segments, _info = self.model.transcribe(
            audio, language=lang, beam_size=int(self.cfg.get("beam_size", 1)),
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 250},
            condition_on_previous_text=False, without_timestamps=True,
            hotwords=hotwords or None, no_speech_threshold=0.6, temperature=0.0)
        parts = []
        for s in segments:
            txt = s.text.strip()
            if not txt:
                continue
            if is_hallucination(txt):
                continue
            if s.no_speech_prob > 0.6 and s.avg_logprob < -0.8:
                continue
            parts.append(txt)
        return " ".join(parts).strip(), lang, time.perf_counter() - t0
