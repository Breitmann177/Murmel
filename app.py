"""Steuerung: verbindet Hotkey, Mikrofon, Whisper, Einfügen und Pille.

Threads (und warum):
- kbd-hook   : Low-Level-Hook braucht eigenen Message-Loop
- PortAudio  : Mikrofon-Callback (in audio.py)
- worker     : Modell laden + Erkennen + Einfügen (blockiert sonst das UI)
- Qt-Hauptthread: NUR hier wird das UI angefasst. Andere Threads melden sich über Qt-Signals;
  Qt stellt die Signale automatisch in die Warteschlange des Hauptthreads (QueuedConnection).
"""
import logging
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import cleanup
import config
import inject
from audio import SR, Mic
from hotkeys import PushToTalkHook
from stt import STT
from ui.widget import Pill
from winutil import process_name, user32

log = logging.getLogger("murmel")


class Bridge(QObject):
    hotkey = Signal(str)
    loaded = Signal(str)
    load_failed = Signal(str)
    result = Signal(dict)


def tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#14513F"))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawRoundedRect(4, 4, 56, 56, 18, 18)
    p.setBrush(QColor("#F8F6EE"))
    for i, h in enumerate((14, 26, 36, 26, 14)):
        p.drawRoundedRect(13 + i * 8, 32 - h / 2, 5, h, 2.5, 2.5)
    p.end()
    return QIcon(pm)


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = config.load()
        self.bridge = Bridge()
        self.mic = Mic(self.cfg.get("mic_device"))
        self.stt = STT(self.cfg)
        self.pill = Pill(level_source=lambda: self.mic.level)
        self.ready = False
        self.paused = False
        self.state = "idle"          # idle | recording | handsfree | processing
        self.target = None
        self.t_press = 0.0
        self.last_tap = 0.0
        self._busy = threading.Lock()

        b = self.bridge
        b.hotkey.connect(self.on_hotkey)
        b.loaded.connect(self.on_loaded)
        b.load_failed.connect(lambda m: self.pill.set_state("error", m, 6000))
        b.result.connect(self.on_result)
        self.pill.cancel_clicked.connect(self.cancel)
        self.pill.finish_clicked.connect(self.finish)

        self.hf_timer = QTimer(self, singleShot=True)
        self.hf_timer.timeout.connect(self.finish)

        self._build_tray()
        self.pill.show()
        self.pill.set_state("loading")

        try:
            self.mic.start()
        except Exception as e:  # noqa: BLE001
            log.error("Mikrofon: %s", e)
            self.pill.set_state("error", "Kein Mikrofon", 5000)

        self.hook = PushToTalkHook(self.cfg["hotkey"], b.hotkey.emit)
        self.hook.start()
        threading.Thread(target=self._load, daemon=True, name="loader").start()

    # ---------------------------------------------------------------- Tray
    def _build_tray(self):
        self.tray = QSystemTrayIcon(tray_icon(), self.app)
        self.tray.setToolTip("Murmel – lädt …")
        m = QMenu()
        self.act_pause = QAction("Pausieren", m, checkable=True)
        self.act_pause.toggled.connect(self.set_paused)
        m.addAction(self.act_pause)
        m.addSeparator()
        quit_act = QAction("Beenden", m)
        quit_act.triggered.connect(self.quit)
        m.addAction(quit_act)
        self.tray.setContextMenu(m)
        self._menu = m
        self.tray.show()

    def set_paused(self, on):
        self.paused = on
        self.hook.enabled = not on
        self.pill.setVisible(not on)

    # ---------------------------------------------------------------- Laden
    def _load(self):
        try:
            self.stt.load()
            self.bridge.loaded.emit(f"{self.stt.model_name} · {self.stt.device.upper()}")
        except Exception as e:  # noqa: BLE001
            log.exception("Modell")
            self.bridge.load_failed.emit("Modell nicht ladbar")

    def on_loaded(self, info):
        self.ready = True
        self.tray.setToolTip(f"Murmel – bereit ({info})")
        self.pill.set_state("idle")
        log.info("Bereit: %s", info)

    # -------------------------------------------------------------- Hotkey
    def on_hotkey(self, ev):
        now = time.monotonic()
        if ev == "hook_failed":
            self.pill.set_state("error", "Tastatur-Hook fehlgeschlagen", 5000)
        elif ev == "press":
            if self.state == "handsfree":
                self.finish()                     # im Freihand-Modus beendet erneutes Tippen
                return
            if self.state != "idle":
                return
            if not self.ready:
                self.pill.set_state("error", "Modell lädt noch …", 1500)
                return
            # Ziel-Fenster JETZT merken – beim Loslassen könnte schon ein anderes vorne sein
            self.target = user32.GetForegroundWindow()
            self.t_press = now
            self.mic.begin()
            self.hook.swallow_esc = True
            if now - self.last_tap < self.cfg["double_tap_s"]:
                self.state = "handsfree"          # Doppeltippen -> Freihand
                self.pill.set_state("handsfree")
                self.hf_timer.start(int(self.cfg["handsfree_max_s"] * 1000))
            else:
                self.state = "recording"
                self.pill.set_state("recording")
        elif ev == "release":
            if self.state != "recording":
                return
            if now - self.t_press < self.cfg["min_press_s"]:
                self.last_tap = now               # Versehen – oder erster Tipp eines Doppeltipps
                self._reset("idle")
                return
            self.finish()
        elif ev == "other":
            if self.state == "recording":         # z. B. Strg+Win+D (Windows-Kürzel)
                self._reset("idle")
        elif ev == "esc":
            if self.state in ("recording", "handsfree"):
                self.cancel()

    def _reset(self, pill_state):
        self.mic.cancel()
        self.hook.swallow_esc = False
        self.hf_timer.stop()
        self.state = "idle"
        self.pill.set_state(pill_state)

    def cancel(self):
        if self.state in ("recording", "handsfree"):
            self._reset("idle")

    def finish(self):
        if self.state not in ("recording", "handsfree"):
            return
        audio = self.mic.end()
        self.hook.swallow_esc = False
        self.hf_timer.stop()
        self.state = "processing"
        self.pill.set_state("processing")
        t_release = time.perf_counter()
        threading.Thread(target=self._process, args=(audio, self.target, t_release),
                         daemon=True, name="worker").start()

    # ------------------------------------------------------------ Verarbeiten
    def _process(self, audio, target, t_release):
        res = {"ok": False}
        try:
            if len(audio) < SR * 0.25:
                res["error"] = "Nichts verstanden"
                return
            raw, lang, t_stt = self.stt.transcribe(audio)
            text = cleanup.clean(raw, lang, self.cfg.get("cleanup", "normal"))
            if not text:
                res["error"] = "Nichts verstanden"
                return
            t_paste = time.perf_counter()
            mode = inject.paste(text + " ", target, self.cfg["paste_restore_ms"])
            total = time.perf_counter() - t_release
            log.info("Latenz %.2fs (Erkennung %.2fs, Einfügen %.2fs) | %.1fs Audio | %s | %s | %r",
                     total, t_stt, time.perf_counter() - t_paste - self.cfg["paste_restore_ms"] / 1000,
                     len(audio) / SR, lang, process_name(target), text)
            res.update(ok=True, mode=mode, text=text, latency=total)
        except Exception as e:  # noqa: BLE001
            log.exception("Verarbeitung")
            res["error"] = "Fehler beim Erkennen"
        finally:
            self.bridge.result.emit(res)

    def on_result(self, res):
        self.state = "idle"
        if not res.get("ok"):
            self.pill.set_state("error", res.get("error", "Fehler"), 3000)
        elif res.get("mode") == "clipboard":
            self.pill.set_state("error", "In der Zwischenablage", 2200)
        else:
            self.pill.set_state("done", hold_ms=600)

    # ---------------------------------------------------------------- Ende
    def quit(self):
        self.hook.stop()
        self.mic.close()
        self.tray.hide()
        self.app.quit()
