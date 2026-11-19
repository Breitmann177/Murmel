"""Leise Start-/Stopp-Töne. Werden einmal als WAV erzeugt (keine Sounddateien nötig) und
asynchron abgespielt (Windows: winsound, Linux: pw-play/paplay/aplay) – blockiert nichts,
braucht kein Qt-Multimedia."""
import math
import shutil
import struct
import subprocess
import sys
import wave

import config

SR = 44100


def _tone(path, f0, f1, ms=90, vol=0.18):
    n = int(SR * ms / 1000)
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        phase += 2 * math.pi * f / SR
        env = math.sin(math.pi * t) ** 1.6              # weich ein- und ausblenden
        frames += struct.pack("<h", int(32767 * vol * env * math.sin(phase)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))


def _path(name):
    p = config.APP_DIR / f"{name}.wav"
    if not p.exists():
        config.APP_DIR.mkdir(parents=True, exist_ok=True)
        if name == "start":
            _tone(p, 660, 880)
        else:
            _tone(p, 760, 520)
    return p


def play(name, enabled=True):
    if not enabled:
        return
    try:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(_path(name)), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        if sys.platform == "darwin":                # macOS: eingebautes afplay
            subprocess.Popen(["afplay", str(_path(name))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        player = next((p for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)
        if player:
            args = [player, "-q", str(_path(name))] if player == "aplay" else [player, str(_path(name))]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
