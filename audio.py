"""Mikrofon: Stream bleibt dauerhaft offen und füllt einen ~300-ms-Ringpuffer.

Warum dauerhaft offen? Ein Audiogerät zu öffnen dauert 50–200 ms. Würden wir erst beim
Drücken öffnen, wäre das erste Wort oft abgeschnitten. So kopieren wir beim Drücken die
letzten 300 ms aus dem Ringpuffer vor die eigentliche Aufnahme ("Pre-Roll").
"""
import threading
import time
from collections import deque

import numpy as np

SR = 16000
PRE_ROLL_S = 0.30


class Resampler:
    """Streaming-Resampler (lineare Interpolation + einfacher Tiefpass). Aus NoTime."""

    def __init__(self, src_sr: int, dst_sr: int = SR):
        self.step = src_sr / dst_sr
        self.pos = 0.0
        self.prev = np.zeros(0, np.float32)
        k = max(1, int(round(self.step)))
        self.kernel = np.ones(k, np.float32) / k if k > 1 else None
        self.tail = np.zeros(0, np.float32)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.step == 1.0:
            return x
        if self.kernel is not None:
            ext = np.concatenate([self.tail, x])
            y = np.convolve(ext, self.kernel, mode="valid")
            self.tail = ext[len(ext) - (len(self.kernel) - 1):]
            x = y.astype(np.float32)
        buf = np.concatenate([self.prev, x])
        n = len(buf)
        if n < 2:
            self.prev = buf
            return np.zeros(0, np.float32)
        idx = np.arange(self.pos, n - 1, self.step)
        out = np.interp(idx, np.arange(n), buf).astype(np.float32)
        next_pos = idx[-1] + self.step if len(idx) else self.pos
        keep = min(int(next_pos), n - 1)
        self.prev = buf[keep:]
        self.pos = next_pos - keep
        return out


def input_devices():
    """(Index, Name) aller Eingabegeräte über MME (Host-API 0), ohne Dubletten und "Mapper".
    Linux: leer – dort nimmt Murmel immer das Standard-Mikrofon von PipeWire/PulseAudio (in den
    Systemeinstellungen wählbar). Die rohen ALSA-Geräte würden PipeWire das Mikrofon wegnehmen."""
    import sys
    if sys.platform != "win32":
        return []
    import sounddevice as sd
    seen, out = set(), []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["hostapi"] == 0 and "mapper" not in d["name"].lower():
            if d["name"] not in seen:
                seen.add(d["name"])
                out.append((i, d["name"]))
    return out


def rescan_devices():
    """PortAudio kennt nur die Geräte vom Start. Neu initialisieren, damit an- oder abgesteckte
    Headsets auftauchen. Nur aufrufen, wenn kein Stream offen ist."""
    import sounddevice as sd
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


class Mic:
    def __init__(self, device=None):
        # device = Gerätename (str) oder None für den System-Standard. Nummern verschieben sich,
        # sobald ein USB-Headset an- oder abgesteckt wird, deshalb speichern wir den Namen.
        self.device = device
        self.level = 0.0               # 0..~0.3, schnell hoch / langsam runter
        self._lock = threading.Lock()
        self._ring = deque()
        self._ring_len = 0
        self._chunks = None             # Liste während der Aufnahme, sonst None
        self.paused = False             # Freihand-Pause: Ton wird verworfen, Aufnahme bleibt offen
        self._stream = None
        self.device_name = ""
        self.last_cb = 0.0

    def _resolve(self):
        """Name -> aktuelle Gerätenummer. Gerät gerade nicht da? Dann System-Standard."""
        if self.device is None or isinstance(self.device, int):
            return self.device
        for i, name in input_devices():
            if name == self.device:
                return i
        return None

    def start(self):
        import sounddevice as sd
        dev = self._resolve()
        info = sd.query_devices(dev, "input")
        sr = int(info["default_samplerate"])
        self.device_name = info["name"]
        rs = Resampler(sr)

        def cb(indata, frames, t, status):
            # läuft im Audio-Thread von PortAudio: kurz halten, nichts blockieren
            self.last_cb = time.monotonic()
            mono = rs(indata[:, 0].copy())
            if not len(mono):
                return
            rms = float(np.sqrt(np.mean(mono * mono)))
            self.level = rms if rms > self.level else self.level * 0.88 + rms * 0.12
            with self._lock:
                self._ring.append(mono)
                self._ring_len += len(mono)
                while self._ring_len - len(self._ring[0]) >= PRE_ROLL_S * SR:
                    self._ring_len -= len(self._ring.popleft())
                if self._chunks is not None and not self.paused:
                    self._chunks.append(mono)

        self.last_cb = time.monotonic()
        self._stream = sd.InputStream(device=dev, channels=1, samplerate=sr,
                                      dtype="float32", blocksize=int(sr * 0.02), callback=cb)
        self._stream.start()

    def begin(self):
        self.paused = False
        with self._lock:
            self._chunks = list(self._ring)   # Pre-Roll vorneweg

    def end(self) -> np.ndarray:
        with self._lock:
            chunks, self._chunks = self._chunks or [], None
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def snapshot(self) -> np.ndarray:
        """Kopie der laufenden Aufnahme, ohne sie zu beenden (für die Live-Vorschau)."""
        with self._lock:
            chunks = list(self._chunks) if self._chunks is not None else []
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def cancel(self):
        with self._lock:
            self._chunks = None

    @property
    def recording(self):
        return self._chunks is not None

    def healthy(self) -> bool:
        """Läuft der Stream noch und kommen Daten? Nach dem Abstecken bleibt der Callback stumm."""
        s = self._stream
        return bool(s is not None and s.active and time.monotonic() - self.last_cb < 2.0)

    def close(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
