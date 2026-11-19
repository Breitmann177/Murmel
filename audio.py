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


class Loopback:
    """Laptop-Ton (alles, was aus den Lautsprechern kommt) über WASAPI-Loopback – für Online-
    Vorlesungen (Zoom, BBB, YouTube). Übernommen aus NoTime. Läuft nur während einer Aufnahme.
    Achtung: Windows liefert bei völliger Stille KEINE Daten – das fangen wir unten ab."""

    def __init__(self, on_audio):
        self.on_audio = on_audio
        self._pa = None
        self._stream = None

    def start(self):
        import pyaudiowpatch as pa
        self._pa = pa.PyAudio()
        dev = self._pa.get_default_wasapi_loopback()
        ch = int(dev["maxInputChannels"])
        rs = Resampler(int(dev["defaultSampleRate"]))

        def cb(in_data, frame_count, time_info, status):
            a = np.frombuffer(in_data, dtype=np.float32)
            if ch > 1:
                a = a.reshape(-1, ch).mean(axis=1)
            mono = rs(a.astype(np.float32))
            if len(mono):
                self.on_audio(mono)
            return (None, pa.paContinue)

        sr = int(dev["defaultSampleRate"])
        self._stream = self._pa.open(format=pa.paFloat32, channels=ch, rate=sr, input=True,
                                     input_device_index=dev["index"],
                                     frames_per_buffer=int(sr * 0.02), stream_callback=cb)
        self._stream.start_stream()

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = self._pa = None


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
    """Quellen: "mic" (Mikrofon), "system" (Laptop-Ton) oder "both" (beides gemischt).
    Taktgeber ist immer das Mikrofon (läuft dauerhaft, gleichmäßig). Beim Laptop-Ton holen wir uns
    pro Mikrofon-Block genau gleich viele Samples aus einem Puffer – fehlen welche (Stille, Windows
    liefert dann nichts), wird mit Null aufgefüllt. So bleibt die Zeitachse lückenlos."""

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
        self.source = "mic"
        self._loop = None
        self._lb = np.zeros(0, np.float32)   # Puffer Laptop-Ton
        self._lb_lock = threading.Lock()

    def _on_loopback(self, mono):
        with self._lb_lock:
            self._lb = np.concatenate([self._lb, mono])[-SR:]   # max. 1 s Vorrat (Takt-Drift)

    def _take_loopback(self, n):
        with self._lb_lock:
            take, self._lb = self._lb[:n], self._lb[n:]
        if len(take) < n:
            take = np.concatenate([take, np.zeros(n - len(take), np.float32)])
        return take

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
            src = self.source if (self._chunks is not None and self._loop) else "mic"
            if src == "system":
                out = self._take_loopback(len(mono))
            elif src == "both":
                out = np.clip(mono + self._take_loopback(len(mono)), -1.0, 1.0)
            else:
                out = mono
            rms = float(np.sqrt(np.mean(out * out)))
            self.level = rms if rms > self.level else self.level * 0.88 + rms * 0.12
            with self._lock:
                self._ring.append(mono)
                self._ring_len += len(mono)
                while self._ring_len - len(self._ring[0]) >= PRE_ROLL_S * SR:
                    self._ring_len -= len(self._ring.popleft())
                if self._chunks is not None and not self.paused:
                    self._chunks.append(out)

        self.last_cb = time.monotonic()
        self._stream = sd.InputStream(device=dev, channels=1, samplerate=sr,
                                      dtype="float32", blocksize=int(sr * 0.02), callback=cb)
        self._stream.start()

    def begin(self, source="mic") -> bool:
        """Aufnahme starten. Gibt False zurück, wenn der Laptop-Ton nicht ging (dann nur Mikro)."""
        self.paused = False
        ok = True
        self.source = source
        if source in ("system", "both"):
            with self._lb_lock:
                self._lb = np.zeros(0, np.float32)
            try:
                self._loop = Loopback(self._on_loopback)
                self._loop.start()
            except Exception:
                self._loop, self.source, ok = None, "mic", False
        with self._lock:
            # Pre-Roll (letzte 300 ms Mikro) nur, wenn das Mikro auch Teil der Aufnahme ist
            self._chunks = list(self._ring) if self.source != "system" else []
        return ok

    def _stop_loopback(self):
        if self._loop:
            self._loop.stop()
            self._loop = None
        self.source = "mic"

    def end(self) -> np.ndarray:
        with self._lock:
            chunks, self._chunks = self._chunks or [], None
        self._stop_loopback()
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def snapshot(self) -> np.ndarray:
        """Kopie der laufenden Aufnahme, ohne sie zu beenden (für die Live-Vorschau)."""
        with self._lock:
            chunks = list(self._chunks) if self._chunks is not None else []
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def cancel(self):
        with self._lock:
            self._chunks = None
        self._stop_loopback()

    @property
    def recording(self):
        return self._chunks is not None

    def healthy(self) -> bool:
        """Läuft der Stream noch und kommen Daten? Nach dem Abstecken bleibt der Callback stumm."""
        s = self._stream
        return bool(s is not None and s.active and time.monotonic() - self.last_cb < 2.0)

    def close(self):
        self._stop_loopback()
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
