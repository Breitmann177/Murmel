"""Steuerung: verbindet Hotkey, Mikrofon, Whisper, Einfügen, Pille, Hauptfenster und Tray.

Threads (und warum):
- kbd-hook   : Low-Level-Hook braucht eigenen Message-Loop
- PortAudio  : Mikrofon-Callback (in audio.py)
- worker     : Modell laden + Erkennen + Einfügen + Speichern (würde sonst das UI blockieren)
- Qt-Hauptthread: NUR hier wird das UI angefasst. Andere Threads melden sich über Qt-Signals;
  Qt stellt sie automatisch in die Warteschlange des Hauptthreads (QueuedConnection).
"""
import logging
import threading
import time

import numpy as np

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import cleanup
import config
import inject
import llm
import sounds
import storage
import styles
import theme
from audio import SR, Mic
from hotkeys import PushToTalkHook
from stt_worker import STTProxy
from ui.widget import Pill
from winutil import idle_seconds, monitor_off, prevent_sleep, process_name, user32, window_title

log = logging.getLogger("murmel")


class Bridge(QObject):
    hotkey = Signal(str)
    loaded = Signal(str, bool)
    load_failed = Signal(str)
    result = Signal(dict)
    partial = Signal(str)        # Live-Vorschau
    engine = Signal(str, str)    # Erkennung lief neu an (z. B. GPU -> CPU)


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = config.load()
        theme.load_fonts()
        self.bridge = Bridge()
        self.mic = Mic(self.cfg.get("mic_device"))
        # Modell läuft in eigenem Prozess (GPU-Wechsel reißt Murmel sonst mit, siehe stt_worker.py)
        self.stt = STTProxy(self.cfg, config.LOG_PATH,
                            on_change=lambda dev, name: self.bridge.engine.emit(dev, name))
        self.pill = Pill(level_source=lambda: self.mic.level)
        self.pill.set_theme(theme.tokens(self.cfg.get("theme", "system")))
        self.window = None
        self.engine_text, self.engine_gpu = "lädt …", False
        self.ready = False
        self.stt_lock = threading.Lock()     # Vorschau und finaler Durchlauf nie gleichzeitig
        self.preview_lock = threading.Lock()
        # Freihand: lange Aufnahmen werden schon während des Sprechens in Häppchen erkannt
        self._hf_lock = threading.Lock()
        self._hf_gen = 0
        self._hf_parts, self._hf_done, self._hf_lang = [], 0, "de"
        self._preview_gen = 0
        self.state = "idle"          # idle | recording | handsfree | processing
        self.target = None
        self.t_press = 0.0
        self.last_tap = 0.0

        b = self.bridge
        b.hotkey.connect(self.on_hotkey)
        b.loaded.connect(self.on_loaded)
        b.load_failed.connect(lambda m: self.pill.set_state("error", m, 6000))
        b.result.connect(self.on_result)
        b.engine.connect(self.on_engine)
        self._gpu_switching = False
        self.gpu_timer = QTimer(self, interval=30000)
        self.gpu_timer.timeout.connect(self._check_gpu)
        self.gpu_timer.start()
        b.partial.connect(lambda t: self.pill.set_preview(t) if self.state in ("recording", "handsfree") else None)
        self.pill.cancel_clicked.connect(self.cancel)
        self.pill.finish_clicked.connect(self.finish)
        self.pill.pause_clicked.connect(self.toggle_pause)
        self.pill.open_window.connect(self.open_window)
        self.pill.start_handsfree.connect(self.start_handsfree)
        self.pill.copy_last.connect(self.copy_last)
        # System-Theme gewechselt (bei "System")? -> neu einfärben
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self.apply_theme())

        self.hf_timer = QTimer(self, singleShot=True)
        self.hf_timer.timeout.connect(self.finish)
        # OLED: während einer Freihand-Aufnahme Bildschirm nach 1 min ohne Eingabe ausschalten
        self.screen_timer = QTimer(self, interval=5000)
        self.screen_timer.timeout.connect(self._check_screen)
        self._screen_off = False

        self._build_tray()
        self.pill.show()
        self.pill.set_state("loading")
        self._start_mic()
        self.hook = None
        self._start_hook()
        threading.Thread(target=self._load, daemon=True, name="loader").start()
        if not self.cfg.get("onboarded"):
            QTimer.singleShot(500, self.show_onboarding)

    # --------------------------------------------------------------- Setup
    def _start_mic(self):
        try:
            self.mic.start()
        except Exception as e:  # noqa: BLE001
            log.error("Mikrofon: %s", e)
            self.pill.set_state("error", "Kein Mikrofon", 5000)

    def _start_hook(self):
        if self.hook:
            self.hook.stop()
        # Command Mode nur, wenn Ollama installiert ist – sonst bleibt Strg+Win+Alt frei
        command = self.cfg.get("command_hotkey") if llm.installed() else None
        self.hook = PushToTalkHook(self.cfg["hotkey"], self.bridge.hotkey.emit, command=command)
        self.hook.start()
        names = {"ctrl": "Strg", "win": "Win", "alt": "Alt", "shift": "Shift", "rctrl": "Rechte Strg"}
        self.pill.hint = " + ".join(names[k] for k in self.cfg["hotkey"])

    def list_mics(self):
        try:
            import sounddevice as sd
            seen, out = set(), []
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and d["hostapi"] == 0 and "mapper" not in d["name"].lower():
                    if d["name"] not in seen:
                        seen.add(d["name"])
                        out.append((i, d["name"]))
            return out
        except Exception:
            return []

    # ---------------------------------------------------------------- Tray
    def _build_tray(self):
        import os
        self.tray = QSystemTrayIcon(QIcon(os.path.join(theme.ASSETS, "murmel.ico")), self.app)
        self.tray.setToolTip("Murmel – lädt …")
        self.tray.activated.connect(
            lambda reason: self.open_window() if reason == QSystemTrayIcon.Trigger else None)
        m = QMenu()
        m.addAction("Murmel öffnen", self.open_window)
        self.act_pause = QAction("Pausieren", m, checkable=True)
        self.act_pause.toggled.connect(self.set_paused)
        m.addAction(self.act_pause)
        lang_menu = m.addMenu("Sprache")
        grp = QActionGroup(lang_menu)
        self.lang_actions = {}
        for key, text in (("auto", "Auto (DE/EN)"), ("de", "Deutsch"), ("en", "Englisch")):
            a = QAction(text, lang_menu, checkable=True)
            a.setChecked(self.cfg.get("language") == key)
            a.triggered.connect(lambda _=False, k=key: self.change_setting("language", k))
            grp.addAction(a)
            lang_menu.addAction(a)
            self.lang_actions[key] = a
        m.addSeparator()
        m.addAction("Beenden", self.quit)
        self.tray.setContextMenu(m)
        self._menu = m
        self.tray.show()

    def set_paused(self, on):
        self.hook.enabled = not on
        self.pill.setVisible(not on)

    # ------------------------------------------------------------- Fenster
    def open_window(self, page="home"):
        if self.window is None:                      # erst bei Bedarf bauen: schnellerer Start
            from ui.main_window import MainWindow
            self.window = MainWindow(self)
            self.window.setWindowIcon(self.tray.icon())
            self.window.setting_changed.connect(self.change_setting)
            self.window.set_status(self.engine_text if self.ready else "Modell lädt …")
            self.window.set_engine(self.engine_text, self.engine_gpu)
        self.window.open(page)

    def apply_theme(self):
        t = theme.tokens(self.cfg.get("theme", "system"))
        self.pill.set_theme(t)
        if self.window:
            self.window.apply_theme()

    def show_onboarding(self):
        from ui.onboarding import Onboarding
        self.onboarding = Onboarding(self)
        self.onboarding.setWindowIcon(self.tray.icon())
        self.onboarding.finished.connect(lambda: self.change_setting("onboarded", True))
        self.onboarding.show()
        self.onboarding.raise_()
        self.onboarding.activateWindow()

    def change_setting(self, key, value):
        if key == "show_onboarding":
            self.show_onboarding()
            return
        if self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        config.save(self.cfg)
        log.info("Einstellung %s = %r", key, value)
        if key == "hotkey":
            self._start_hook()
        elif key == "mic_device":
            self.mic.close()
            self.mic = Mic(value)
            self.pill.level_source = lambda: self.mic.level
            self._start_mic()
        elif key == "theme":
            self.apply_theme()
        elif key == "language":
            for k, a in self.lang_actions.items():
                a.setChecked(k == value)
        if key in ("language", "beam_size"):
            self.stt.update_cfg({key: value})       # Worker-Prozess hat eine eigene Kopie
        if self.window and key == "name":
            self.window.refresh()

    # ---------------------------------------------------------------- Laden
    def _load(self):
        try:
            self.stt.load()
            gpu = self.stt.device == "cuda"
            self.bridge.loaded.emit(f"{self.stt.model_name} · {'GPU' if gpu else 'CPU'}", gpu)
        except Exception:  # noqa: BLE001
            log.exception("Modell")
            self.bridge.load_failed.emit("Modell nicht ladbar")

    def on_engine(self, device, name):
        """Worker (neu) gestartet – z. B. nach GPU-Wegfall auf CPU oder zurück auf GPU."""
        gpu = device == "cuda"
        info = f"{name} · {'GPU' if gpu else 'CPU'}"
        if not self.ready:
            return                              # erster Start: on_loaded übernimmt
        self.engine_text, self.engine_gpu = info, gpu
        self.tray.setToolTip(f"Murmel – bereit ({info})")
        if self.window:
            self.window.set_status(info)
            self.window.set_engine(info, gpu)
        log.info("Erkennung jetzt: %s", info)

    def _check_gpu(self):
        """Alle 30 s im Leerlauf: Läuft Murmel auf der CPU, ist die GPU aber wieder da? Dann wechseln."""
        if not self.ready or self.state != "idle" or self.stt.device != "cpu" or self._gpu_switching:
            return

        def work():
            self._gpu_switching = True
            try:
                if self.stt.cuda_available() and self.state == "idle":
                    log.info("GPU wieder da – wechsle")
                    self.stt.restart()
            except Exception as e:  # noqa: BLE001
                log.warning("GPU-Wechsel: %s", e)
            finally:
                self._gpu_switching = False
        threading.Thread(target=work, daemon=True, name="gpu-check").start()

    def on_loaded(self, info, gpu):
        self.ready = True
        self.engine_text, self.engine_gpu = info, gpu
        self.tray.setToolTip(f"Murmel – bereit ({info})")
        self.pill.set_state("idle")
        if self.window:
            self.window.set_status(info)
            self.window.set_engine(info, gpu)
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
            handsfree = now - self.last_tap < self.cfg["double_tap_s"]
            self._begin(user32.GetForegroundWindow(), handsfree)
        elif ev in ("command_press", "upgrade"):
            if ev == "command_press" and self.state == "idle" and self.ready:
                self._begin(user32.GetForegroundWindow(), False)
            if self.state == "recording":
                self.state = "command"            # gleiche Aufnahme, wird jetzt eine Anweisung
                self.pill.set_state("command")
        elif ev == "release":
            if self.state not in ("recording", "command"):
                return
            if now - self.t_press < self.cfg["min_press_s"]:
                self.last_tap = now               # Versehen – oder erster Tipp eines Doppeltipps
                self._reset("idle", sound=False)
                return
            self.finish()
        elif ev == "other":
            if self.state in ("recording", "command"):   # z. B. Strg+Win+D (Windows-Kürzel)
                self._reset("idle", sound=False)
        elif ev == "esc":
            if self.state in ("recording", "handsfree", "command"):
                self.cancel()

    def _begin(self, target, handsfree):
        # Ziel-Fenster JETZT merken – beim Loslassen könnte schon ein anderes vorne sein
        self.target = target
        self.t_press = time.monotonic()
        self.mic.begin()
        prevent_sleep(True)
        self.hook.swallow_esc = True
        sounds.play("start", self.cfg.get("sounds", True))
        if handsfree:
            self.state = "handsfree"
            self.pill.set_state("handsfree")
            self.hf_timer.start(int(self.cfg.get("handsfree_limit_min", 240) * 60 * 1000))
            self._start_chunker()
            self._screen_off = False
            self.screen_timer.start()
        else:
            self.state = "recording"
            self.pill.set_state("recording")
        self._start_preview()
        if self.cfg.get("cleanup") == "strong":
            threading.Thread(target=self._warm_ollama, daemon=True).start()

    # ------------------------------------------------------------ Live-Vorschau
    def _start_preview(self):
        """Während du sprichst, wird die bisherige Aufnahme ~2× pro Sekunde erkannt und in einer
        Blase über der Pille gezeigt. Das ist NUR eine Vorschau: Eingefügt wird am Ende der
        saubere Durchlauf über die komplette Aufnahme. Auf der CPU wäre das zu langsam (~2 s pro
        Durchlauf), deshalb nur mit GPU."""
        self._preview_gen += 1
        if self.cfg.get("live_preview", True) and self.stt.device == "cuda":
            threading.Thread(target=self._preview_loop, args=(self._preview_gen,),
                             daemon=True, name="preview").start()

    def _stop_preview(self):
        self._preview_gen += 1          # laufende Schleife merkt das und hört auf
        self.pill.set_preview("")

    def _preview_loop(self, gen):
        last_len = 0
        hot = storage.hotwords() or None
        which = "preview" if self.stt.has_preview else "main"
        while self._preview_gen == gen:
            time.sleep(0.25 if self.stt.has_preview else 0.4)
            audio = self.mic.snapshot()
            # erst ab 0,7 s und nur, wenn seit dem letzten Mal genug Neues dazukam
            if len(audio) < SR * 0.5 or len(audio) - last_len < SR * 0.2:
                continue
            last_len = len(audio)
            tail = audio[-25 * SR:]          # lange Freihand-Aufnahmen: nur das Ende zeigen
            with self.preview_lock:
                if self._preview_gen != gen or self.stt.device != "cuda":
                    break
                try:
                    text, lang, _ = self.stt.transcribe(tail, hot, which=which)
                except Exception:  # noqa: BLE001
                    continue
            if self._preview_gen == gen and text:
                self.bridge.partial.emit(cleanup.clean(text, lang, "normal"))

    def _warm_ollama(self):
        """Stark-Modus: Sprachmodell schon beim Drücken in den Grafikspeicher laden, damit die
        Glättung beim Loslassen sofort da ist (kalt dauert der erste Aufruf ~10 s)."""
        try:
            if llm.ensure_running(wait=5):
                model = llm.pick_model(self.cfg.get("ollama_model"))
                if model:
                    llm.warm(model)
        except Exception:  # noqa: BLE001
            pass

    def start_handsfree(self):
        """Klick auf ● in der Pille. Die Pille aktiviert sich nie, also ist das Vordergrund-
        fenster immer noch deine App – genau dorthin kommt der Text."""
        if self.state == "idle" and self.ready:
            self._begin(user32.GetForegroundWindow(), True)

    def copy_last(self):
        rows = storage.history(limit=1)
        if rows:
            inject.set_text(rows[0]["clean"], exclude_history=False)
            self.pill.mark_copied()

    def _reset(self, pill_state, sound=True):
        self.screen_timer.stop()
        self._stop_preview()
        self._hf_gen += 1                 # Häppchen-Erkennung einer abgebrochenen Aufnahme stoppen
        prevent_sleep(False)
        self.mic.cancel()
        self.hook.swallow_esc = False
        self.hf_timer.stop()
        self.state = "idle"
        self.pill.set_state(pill_state)

    def _check_screen(self):
        limit = int(self.cfg.get("screen_off_s", 60))
        if self.state != "handsfree" or limit <= 0:
            return
        idle = idle_seconds()
        if idle < 5:
            self._screen_off = False          # du hast die Maus bewegt -> Bildschirm ist wieder an
        elif idle >= limit and not self._screen_off:
            self._screen_off = True
            monitor_off()
            log.info("Bildschirm aus (OLED), Aufnahme läuft weiter")

    def toggle_pause(self):
        """Freihand-Aufnahme kurz anhalten (z. B. Zwischenfrage), Mitte der Pille antippen."""
        if self.state != "handsfree":
            return
        on = not self.mic.paused
        self.mic.paused = on
        self.pill.set_paused(on)
        if on:
            self.hf_timer.stop()          # die 6-Minuten-Grenze zählt in der Pause nicht
        else:
            left = self.cfg.get("handsfree_limit_min", 240) * 60 - self.pill.elapsed()
            self.hf_timer.start(int(max(1, left) * 1000))

    def cancel(self):
        if self.state in ("recording", "handsfree", "command"):
            self._reset("idle")

    def finish(self):
        if self.state not in ("recording", "handsfree", "command"):
            return
        mode = "command" if self.state == "command" else "dictate"
        self.screen_timer.stop()
        parts, done = None, 0
        if self.state == "handsfree":
            with self._hf_lock:          # ab jetzt nimmt die Häppchen-Schleife nichts mehr an
                self._hf_gen += 1
                parts, done = list(self._hf_parts), self._hf_done
        self._stop_preview()
        prevent_sleep(False)
        audio = self.mic.end()
        self.hook.swallow_esc = False
        self.hf_timer.stop()
        self.state = "processing"
        self.pill.set_state("processing")
        sounds.play("stop", self.cfg.get("sounds", True))
        t_release = time.perf_counter()
        if mode == "command":
            fn, args = self._process_command, (audio, self.target, t_release)
        else:
            fn, args = self._process, (audio, self.target, t_release, parts, done)
        threading.Thread(target=fn, args=args, daemon=True, name="worker").start()

    # ------------------------------------------------- Häppchen bei langer Aufnahme
    def _start_chunker(self):
        with self._hf_lock:
            self._hf_gen += 1
            self._hf_parts, self._hf_done, self._hf_lang = [], 0, "de"
            gen = self._hf_gen
        threading.Thread(target=self._chunk_loop, args=(gen,), daemon=True, name="chunker").start()

    def _chunk_loop(self, gen):
        """Alle ~25 s das fertige Stück erkennen (geschnitten an der leisesten Stelle, damit kein
        Wort zerteilt wird). So ist nach 90 Minuten Vorlesung beim Stoppen fast alles schon fertig."""
        hot = storage.hotwords() or None
        while self._hf_gen == gen:
            time.sleep(2)
            audio = self.mic.snapshot()
            start = self._hf_done
            if len(audio) - start < 28 * SR:
                continue
            cut = self._quiet_cut(audio, start + 18 * SR, start + 27 * SR)
            with self.stt_lock:
                if self._hf_gen != gen:
                    break
                try:
                    text, lang, _ = self.stt.transcribe(audio[start:cut], hot)
                except Exception as e:  # noqa: BLE001
                    log.warning("Häppchen: %s", e)
                    continue
            with self._hf_lock:
                if self._hf_gen != gen:
                    break
                if text:
                    self._hf_parts.append(text)
                    self._hf_lang = lang
                self._hf_done = cut

    @staticmethod
    def _quiet_cut(audio, a, b, frame=480):
        seg = audio[a:b]
        n = len(seg) // frame
        rms = np.sqrt((seg[:n * frame].reshape(n, frame) ** 2).mean(axis=1))
        return a + int(np.argmin(rms)) * frame + frame // 2

    # ------------------------------------------------------------ Verarbeiten
    def _shape_text(self, raw, lang, target):
        """Rohtext -> fertiger Text: Snippet? Regeln + Wörterbuch, optional Ollama, Stil der App."""
        snippet = storage.match_snippet(raw)
        if snippet:
            return snippet, "snippet"
        level = self.cfg.get("cleanup", "normal")
        text = cleanup.clean(raw, lang, "normal" if level == "strong" else level, storage.replacements())
        if level == "strong" and text and llm.ensure_running(wait=4):
            model = llm.pick_model(self.cfg.get("ollama_model"))
            if model:
                text = llm.polish(text, model) or text
        style = styles.style_for(process_name(target), window_title(target), self.cfg.get("app_styles", {}))
        words = [d["word"] for d in storage.dictionary()]
        return styles.apply(text, style, words), style

    def _process_command(self, audio, target, t_release):
        """Command Mode: Markierung holen -> Anweisung erkennen -> Ollama -> Markierung ersetzen."""
        res = {"ok": False}
        try:
            selection = inject.copy_selection()
            if not selection.strip():
                res["error"] = "Erst Text markieren"
                return
            with self.stt_lock:
                instruction, _lang, _ = self.stt.transcribe(audio)
            if not instruction:
                res["error"] = "Nichts verstanden"
                return
            if not llm.ensure_running():
                res["error"] = "Ollama startet nicht"
                return
            model = llm.pick_model(self.cfg.get("ollama_model"))
            if not model:
                res["error"] = "Kein Ollama-Modell"
                return
            out = llm.command(selection, instruction, model)
            if not out:
                res["error"] = "Keine Antwort"
                return
            mode = inject.paste(out, target, self.cfg["paste_restore_ms"])
            total = time.perf_counter() - t_release
            log.info("Befehl %.2fs | %r", total, instruction)
            storage.add_history(process_name(target), f"✨ {instruction}", out, _lang, len(audio) / SR, total)
            res.update(ok=True, mode=mode, text=out, latency=total)
        except Exception:  # noqa: BLE001
            log.exception("Befehl")
            res["error"] = "Befehl fehlgeschlagen"
        finally:
            self.bridge.result.emit(res)

    def _process(self, audio, target, t_release, parts=None, done=0):
        res = {"ok": False}
        try:
            if len(audio) < SR * 0.25:
                res["error"] = "Nichts verstanden"
                return
            if parts or done:           # lange Freihand-Aufnahme: nur noch der Rest fehlt
                rest = audio[done:]
                raw, lang, t_stt = "", self._hf_lang, 0.0
                if len(rest) >= SR * 0.3:
                    with self.stt_lock:
                        raw, lang, t_stt = self.stt.transcribe(rest, storage.hotwords() or None)
                raw = " ".join(p for p in parts + [raw] if p).strip()
            else:
                with self.stt_lock:      # wartet höchstens auf eine laufende Vorschau (~0,3 s)
                    raw, lang, t_stt = self.stt.transcribe(audio, storage.hotwords() or None)
            text, style = self._shape_text(raw, lang, target)
            if not text:
                res["error"] = "Nichts verstanden"
                return
            t_paste = time.perf_counter()
            # Leerzeichen hinten, damit das nächste Diktat nicht am Wort klebt (nicht nach Umbruch)
            mode = inject.paste(text if text.endswith("\n") else text + " ", target,
                                self.cfg["paste_restore_ms"])
            total = time.perf_counter() - t_release
            app = process_name(target)
            log.info("Latenz %.2fs (Erkennung %.2fs, Einfügen %.2fs) | %.1fs Audio | %s | %s | Stil %s",
                     total, t_stt, time.perf_counter() - t_paste - self.cfg["paste_restore_ms"] / 1000,
                     len(audio) / SR, lang, app, style)
            storage.add_history(app, raw, text, lang, len(audio) / SR, total)
            res.update(ok=True, mode=mode, text=text, latency=total)
        except Exception:  # noqa: BLE001
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
        if self.window and self.window.isVisible():
            self.window.refresh()

    # ---------------------------------------------------------------- Ende
    def quit(self):
        prevent_sleep(False)
        self.stt.stop()
        self.hook.stop()
        self.mic.close()
        self.tray.hide()
        self.app.quit()
