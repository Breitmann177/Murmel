"""Die schwebende Pille unten mittig.

Technik-Entscheidungen:
- Echtes transparentes Fenster (WA_TranslucentBackground): Qt zeichnet mit Alpha-Kanal und
  Kantenglättung. Komplett transparente Pixel sind für Windows "nicht da" -> Klicks gehen durch.
- Tool + WindowDoesNotAcceptFocus + WS_EX_NOACTIVATE: die Pille wird NIE das aktive Fenster.
  Sonst würde der diktierte Text in der Pille statt in deiner App landen.
- Nicht verschiebbar (gewünscht): feste Position über der Taskleiste.
- Animations-Timer läuft nur, solange sich etwas bewegt -> im Leerlauf 0 % CPU.
"""
import ctypes
import math
import random
import time

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer,
                            Property, QParallelAnimationGroup, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import QWidget

WIN_W, WIN_H = 520, 196         # festes (unsichtbares) Fenster: Pille unten, Text-Blase darüber
BOTTOM_GAP = 12                 # Abstand der Pille zur Taskleiste
BARS = 12

SIZES = {                        # (Breite, Höhe) der Pille je Zustand
    "loading": (96, 10),
    "idle": (40, 8),
    "hover": (172, 46),          # aufgeklappt: Aufnahme + Quellen-Pfeil · Logo · Einstellungen
    "recording": (164, 40),
    "handsfree": (232, 40),
    "mini": (44, 20),            # Freihand nach 3 s ohne Maus: klein, nur Mini-Pegel
    "command": (184, 40),        # Command Mode: andere Farbe + ✨
    "processing": (164, 40),
    "done": (164, 40),
    "error": (240, 40),
}


# Knöpfe im aufgeklappten Zustand: Abstand von der Mitte (wie bei NoTime)
SLOTS = {"src": -40, "record": -58, "logo": 0, "settings": 56}   # "src" = dünner Pfeil: Tonquelle
SLOT_R = {"src": 6}                                                # Trefferradius (Standard 17)
SOURCES = (("mic", "Mikrofon"), ("system", "Laptop-Ton"), ("both", "Beides"))
GLYPHS = {"settings": "\uE713", "record": "\uE7C8"}


class Pill(QWidget):
    cancel_clicked = Signal()
    pause_clicked = Signal()
    finish_clicked = Signal()
    open_window = Signal(str)        # "home" | "settings"
    source_changed = Signal(str)     # "mic" | "system" | "both"
    start_handsfree = Signal()
    copy_last = Signal()

    def __init__(self, level_source=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFixedSize(WIN_W, WIN_H)
        self.level_source = level_source or (lambda: 0.0)

        self.state = "loading"
        self.message = ""
        self.hint = "Strg + Win halten"
        self._w, self._h = SIZES["loading"]
        self._hovered = False
        self._bars = [0.0] * BARS
        self._t0 = time.monotonic()
        self._rec_t0 = 0.0
        self._progress = 0.0

        self._anim = QParallelAnimationGroup(self)
        self._aw = QPropertyAnimation(self, b"pillW", self)
        self._ah = QPropertyAnimation(self, b"pillH", self)
        for a in (self._aw, self._ah):
            self._anim.addAnimation(a)
        self._anim.finished.connect(self._maybe_stop_timer)

        self._tick = QTimer(self)
        self._tick.setInterval(16)                 # ~60 fps, nur bei Bewegung aktiv
        self._tick.timeout.connect(self._on_tick)
        self._back = QTimer(self, singleShot=True)
        self._back.timeout.connect(lambda: self.set_state("idle"))
        # Zuklappen leicht verzögert, damit die Pille nicht flackert, wenn man kurz rausrutscht
        self._leave = QTimer(self, singleShot=True)
        self._leave.setInterval(380)
        self._leave.timeout.connect(self._collapse)

        # Freihand-Aufnahme schrumpft nach 3 s ohne Maus auf eine Mini-Pille
        self._mini = False
        self._mini_timer = QTimer(self, singleShot=True)
        self._mini_timer.setInterval(3000)
        self._mini_timer.timeout.connect(self._go_mini)

        self._hover_slot = None
        self.rec_source = "mic"
        self._picker = False              # Mini-Auswahl der Tonquelle offen?
        self._picker_rows = []
        self._picker_hover = None
        self._bubble_text = ""
        self._bubble_a = 0.0
        self._bubble_target = 0.0
        self._copied_until = 0.0
        self._logo = None
        self.colors = {"pill": "#121214", "pill_fg": "#F2F2F2", "line": "#2A2A2A", "hover": "#262626"}
        self.icon_family = "Segoe Fluent Icons"

        self.place()

    def set_theme(self, t: dict):
        """Aufgeklappte Pille folgt dem App-Theme (hell = weiß wie bei NoTime)."""
        self.colors = {k: t[k] for k in ("pill", "pill_fg", "line", "hover")}
        self._logo = None
        self.update()

    def _logo_pixmap(self):
        if self._logo is None:
            import numpy as np
            import logo
            dpr = self.devicePixelRatioF()
            px = int(28 * dpr)
            arr = np.ascontiguousarray(logo.render(px, self.colors["pill_fg"]))
            img = QImage(arr.data, px, px, 4 * px, QImage.Format_RGBA8888).copy()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(dpr)
            self._logo = pm
        return self._logo

    def mark_copied(self):
        self._copied_until = time.monotonic() + 1.4
        self.update()
        QTimer.singleShot(1450, self.update)

    # ------------------------------------------------------- Eigenschaften
    def _get_w(self):
        return self._w

    def _set_w(self, v):
        self._w = v
        self.update()

    def _get_h(self):
        return self._h

    def _set_h(self, v):
        self._h = v
        self.update()

    pillW = Property(float, _get_w, _set_w)
    pillH = Property(float, _get_h, _set_h)

    # ------------------------------------------------------------ Fenster
    def showEvent(self, e):
        super().showEvent(e)
        try:   # WS_EX_NOACTIVATE + TOOLWINDOW zusätzlich auf Win32-Ebene setzen
            hwnd = int(self.winId())
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x00000080)
        except Exception:
            pass

    def place(self, screen=None):
        scr = screen or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()                 # ohne Taskleiste
        self.move(g.x() + (g.width() - WIN_W) // 2, g.y() + g.height() - WIN_H)

    def pill_rect(self):
        x = (WIN_W - self._w) / 2
        y = WIN_H - BOTTOM_GAP - self._h
        return QRectF(x, y, self._w, self._h)

    # ------------------------------------------------------------ Zustände
    def set_state(self, state, message="", hold_ms=0):
        self.state = state
        self.message = message
        self._back.stop()
        if state in ("recording", "handsfree", "command"):
            self._rec_t0 = time.monotonic() if state == "recording" or not self._rec_t0 else self._rec_t0
        if state not in ("handsfree",):
            self.paused, self._paused_total = False, 0.0
        if state == "handsfree" and not self.paused:
            self._rec_t0, self._paused_total = time.monotonic(), 0.0
        if state == "handsfree":
            if not self._mini:
                self._mini_timer.start()
        else:
            self._mini = False
            self._mini_timer.stop()
        key = "hover" if state == "idle" and self._hovered else ("mini" if state == "handsfree" and self._mini else state)
        w, h = SIZES[key]
        if state == "error" and message:
            w = max(160, min(300, 56 + len(message) * 7))
        self._animate_to(w, h, bounce=state in ("recording", "handsfree", "command", "hover"))
        if hold_ms:
            self._back.start(hold_ms)
        self._ensure_timer()

    # ------------------------------------------------------------ Pause
    paused = False
    _paused_at = 0.0
    _paused_total = 0.0

    def set_paused(self, on: bool):
        if on and not self.paused:
            self._paused_at = time.monotonic()
        elif not on and self.paused:
            self._paused_total += time.monotonic() - self._paused_at
        self.paused = on
        self.update()

    def elapsed(self):
        end = self._paused_at if self.paused else time.monotonic()
        return max(0.0, end - self._rec_t0 - self._paused_total)

    def set_preview(self, text: str):
        """Live-Text über der Pille. Leerer Text = Blase weich ausblenden."""
        if text:
            self._bubble_text = text
        self._bubble_target = 1.0 if text else 0.0
        self._ensure_timer()

    def set_progress(self, p):
        self._progress = p
        self.update()

    def _animate_to(self, w, h, bounce=False):
        self._anim.stop()
        curve = QEasingCurve(QEasingCurve.OutBack if bounce else QEasingCurve.OutCubic)
        if bounce:
            curve.setOvershoot(1.3)
        for a, start, end in ((self._aw, self._w, w), (self._ah, self._h, h)):
            a.setStartValue(float(start))
            a.setEndValue(float(end))
            a.setDuration(320 if bounce else 240)
            a.setEasingCurve(curve)
        self._anim.start()

    def _ensure_timer(self):
        if not self._tick.isActive():
            self._tick.start()

    def _maybe_stop_timer(self):
        if self.state in ("idle", "error") and self._anim.state() != QPropertyAnimation.Running \
                and self._bubble_a == self._bubble_target:
            self._tick.stop()

    def _on_tick(self):
        if self._bubble_a != self._bubble_target:               # Blase ein-/ausblenden
            step = 0.12 if self._bubble_target > self._bubble_a else 0.2
            self._bubble_a = min(1.0, self._bubble_a + step) if self._bubble_target > self._bubble_a \
                else max(0.0, self._bubble_a - step)
        if self.state in ("recording", "handsfree", "command"):
            self._update_bars()
        self.update()
        self._maybe_stop_timer()

    def _update_bars(self):
        lvl = self.level_source()
        db = 20 * math.log10(max(lvl, 1e-5))
        v = min(1.0, max(0.0, (db + 55) / 40))
        t = time.monotonic()
        for i in range(BARS):
            # symmetrisch zur Mitte: mittlere Balken höher, leichtes Eigenleben
            center = 1 - abs(i - (BARS - 1) / 2) / (BARS / 2)
            target = v * (0.35 + 0.65 * center) * (0.75 + 0.25 * math.sin(t * 9 + i * 1.7))
            target += random.uniform(0, 0.06) * v
            cur = self._bars[i]
            self._bars[i] = cur + (target - cur) * (0.55 if target > cur else 0.18)

    # -------------------------------------------------------------- Maus
    def _go_mini(self):
        if self.state == "handsfree" and not self._hovered:
            self._mini = True
            self._animate_to(*SIZES["mini"])
            self._ensure_timer()

    def enterEvent(self, e):
        self._leave.stop()
        if self.state == "handsfree":
            self._mini_timer.stop()
            self._hovered = True
            if self._mini:                        # Maus drauf: wieder groß mit ✕ / Pause / ✓
                self._mini = False
                self._animate_to(*SIZES["handsfree"], bounce=True)
                self._ensure_timer()
            return
        if not self._hovered:
            self._hovered = True
            if self.state == "idle":
                self.set_state("idle")

    def leaveEvent(self, e):
        self._leave.start()

    def _collapse(self):
        self._hovered = False
        self._hover_slot = None
        self._picker = False
        if self.state == "handsfree":
            self._mini_timer.start()
        if self.state == "idle":
            self.set_state("idle")

    def _slot_at(self, x, y):
        r = self.pill_rect()
        if not (self.state == "idle" and self._hovered and r.width() > 150 and r.contains(x, y)):
            return None
        cx = r.center().x()
        for name, dx in SLOTS.items():
            if abs(x - (cx + dx)) <= SLOT_R.get(name, 17):
                return name
        return None

    def _picker_row_at(self, x, y):
        for rect, key in self._picker_rows:
            if rect.contains(x, y):
                return key
        return None

    def mouseMoveEvent(self, e):
        if self._picker:
            ph = self._picker_row_at(e.position().x(), e.position().y())
            if ph != self._picker_hover:
                self._picker_hover = ph
                self.setCursor(Qt.PointingHandCursor if ph else Qt.ArrowCursor)
                self.update()
            if ph:
                return
        s = self._slot_at(e.position().x(), e.position().y())
        if s != self._hover_slot:
            self._hover_slot = s
            self.setCursor(Qt.PointingHandCursor if s else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if self.state == "handsfree":
            r = self.pill_rect()
            if r.width() < 200:                    # Mini-Pille: erst aufklappen lassen, nichts auslösen
                return
            if x < r.left() + 36:
                self.cancel_clicked.emit()
            elif x > r.right() - 36:
                self.finish_clicked.emit()
            elif r.contains(x, y):
                self.pause_clicked.emit()          # Mitte antippen = Pause / weiter
            return
        if self._picker:
            key = self._picker_row_at(x, y)
            self._picker = False
            if key:
                self.rec_source = key
                self.source_changed.emit(key)
                self.update()
                return
        s = self._slot_at(x, y)
        if s == "src":
            self._picker = not self._picker
            self.update()
            return
        if s == "settings":
            self.open_window.emit("settings")
        elif s == "record":
            self.start_handsfree.emit()
        elif s == "logo":
            self.open_window.emit("home")

    # ------------------------------------------------------------ Zeichnen
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.pill_rect()
        rad = r.height() / 2
        idle = self.state == "idle" and not self._hovered
        loading = self.state == "loading"
        if self.state == "idle" and (self._hovered or r.width() > 60):
            self._paint_menu(p, r)
            if self._picker and r.width() > 150:
                self._paint_picker(p, r)
            p.end()
            return
        if idle:
            # fast unsichtbare Fläche um die Mini-Pille: fängt die Maus ab (Alpha 0 wäre "Luft")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 1))
            p.drawRoundedRect(r.adjusted(-24, -12, 24, 6), 10, 10)

        # weicher Schatten: mehrere transparente Lagen statt teurem Blur-Effekt
        if not idle and not loading:
            for i in range(6, 0, -1):
                sr = r.adjusted(-i, -i + 2, i, i + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 10))
                p.drawRoundedRect(sr, sr.height() / 2, sr.height() / 2)

        fill = QColor(18, 18, 20, 150 if idle else 245)
        if self.state == "error":
            fill = QColor(120, 28, 32, 245)
        p.setBrush(fill)
        p.setPen(QPen(QColor(255, 255, 255, 40 if idle else 28), 1))
        p.drawRoundedRect(r, rad, rad)

        white = QColor(255, 255, 255)
        if loading:
            self._paint_loading(p, r)
        elif self.state == "idle" and self._hovered and r.width() > 110:
            self._text(p, r, self.hint, 11, QColor(255, 255, 255, 210))
        elif self.state == "command":
            self._paint_bars(p, r, QColor("#D8CAF7"))
            f = QFont(self.icon_family, 11)
            f.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias))
            p.setFont(f)
            p.setPen(QColor("#D8CAF7"))
            p.drawText(QRectF(r.left() + 8, r.top(), 26, r.height()), Qt.AlignCenter, "\uE945")  # Sparkle
        elif self.state == "handsfree" and r.width() < 140:
            self._paint_mini(p, r)
        elif self.state in ("recording", "handsfree"):
            if self.paused:
                self._text(p, r.adjusted(24, 0, -24, 0), "Pausiert", 10, QColor(255, 255, 255, 170))
            else:
                self._paint_bars(p, r)
            if self.state == "handsfree" and r.width() > 200:
                self._paint_handsfree(p, r)
        elif self.state == "processing":
            self._paint_dots(p, r)
        elif self.state == "done":
            self._paint_check(p, r)
        elif self.state == "error" and r.width() > 120:
            self._text(p, r, self.message, 11, white)
        self._paint_bubble(p, r)
        p.end()

    def _paint_mini(self, p, r):
        """Dezente Aufnahme-Anzeige: nur 4 winzige Pegel-Balken in der Mitte."""
        cy, cx = r.center().y(), r.center().x()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 110 if self.paused else 220))
        gap, bw = 6, 2.6
        x0 = cx - (3 * gap + bw) / 2
        for i, v in enumerate(self._bars[4:8]):
            h = 2.5 if self.paused else max(2.5, v * (r.height() - 8))
            p.drawRoundedRect(QRectF(x0 + i * gap, cy - h / 2, bw, h), bw / 2, bw / 2)
    def _paint_bubble(self, p, r):
        """Live-Text: dunkle Blase über der Pille, zeigt die letzten 3 Zeilen."""
        a = self._bubble_a
        if a < 0.02 or not self._bubble_text:
            return
        if self.state == "handsfree" and r.width() < 140:      # Mini-Modus: dezent, keine Blase
            return
        f = QFont("Inter", 11)
        f.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias))
        fm = QFontMetricsF(f)
        padx, pady = 16, 10
        max_text_w = WIN_W - 40 - 2 * padx
        full = fm.boundingRect(QRectF(0, 0, max_text_w, 10000), Qt.TextWordWrap, self._bubble_text)
        tw = min(max_text_w, full.width() + 2)
        th = min(full.height(), fm.lineSpacing() * 3)
        rect = QRectF((WIN_W - tw - 2 * padx) / 2, r.top() - 10 - th - 2 * pady, tw + 2 * padx, th + 2 * pady)
        rect.translate(0, (1 - a) * 6)                       # beim Einblenden leicht nach oben gleiten
        p.setPen(Qt.NoPen)
        for i in range(5, 0, -1):
            p.setBrush(QColor(0, 0, 0, int(8 * a)))
            p.drawRoundedRect(rect.adjusted(-i, -i + 2, i, i + 2), 16 + i, 16 + i)
        p.setBrush(QColor(18, 18, 20, int(242 * a)))
        p.setPen(QPen(QColor(255, 255, 255, int(28 * a)), 1))
        p.drawRoundedRect(rect, 16, 16)
        inner = rect.adjusted(padx, pady, -padx, -pady)
        p.save()
        p.setClipRect(inner)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, int(235 * a)))
        # unten ausrichten: bei langem Text sieht man immer die neuesten Wörter
        p.drawText(QRectF(inner.left(), inner.bottom() - full.height(), inner.width(), full.height()),
                   Qt.TextWordWrap | Qt.AlignLeft, self._bubble_text)
        p.restore()

    def _paint_menu(self, p, r):
        """Aufgeklappte Pille wie bei NoTime: ⚙  ●  Logo  ⤢  ⧉"""
        c = self.colors
        for i in range(6, 0, -1):                      # weicher Schatten
            sr = r.adjusted(-i, -i + 2, i, i + 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(sr, sr.height() / 2, sr.height() / 2)
        p.setBrush(QColor(c["pill"]))
        p.setPen(QPen(QColor(c["line"]), 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if r.width() < 150:            # während der Animation nur die Form zeigen
            return
        cx, cy = r.center().x(), r.center().y()
        f = QFont(self.icon_family, 12)
        # Graustufen-Glättung: Subpixel (ClearType) erzeugt auf transparenten Fenstern Farbsäume
        f.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias))
        p.setFont(f)
        for name, dx in SLOTS.items():
            x = cx + dx
            if name == self._hover_slot and name != "src":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c["hover"]))
                p.drawEllipse(QPointF(x, cy), 17, 17)
            if name == "logo":
                pm = self._logo_pixmap()
                p.drawPixmap(QPointF(x - 14, cy - 14), pm)
                continue
            if name == "src":               # schmale, hochkante Kapsel mit Pfeil (Tonquelle)
                active = name == self._hover_slot or self._picker
                cap = QRectF(x - 6, cy - 12, 12, 24)
                bg = QColor(c["hover"])
                if not active:
                    bg.setAlpha(150)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(cap, 6, 6)
                col = QColor(c["pill_fg"])
                col.setAlpha(235 if active else 170)
                p.setPen(QPen(col, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                d = 1 if self._picker else -1
                p.drawPolyline([QPointF(x - 2.2, cy - 1.6 * d), QPointF(x, cy + 1.6 * d), QPointF(x + 2.2, cy - 1.6 * d)])
                p.setFont(f)
                continue
            glyph = GLYPHS[name]
            color = QColor(c["pill_fg"])
            if name == "record":
                color = QColor("#FF453A")
            if name == "copy" and time.monotonic() < self._copied_until:
                glyph = ""
            p.setPen(color)
            p.drawText(QRectF(x - 17, cy - 17, 34, 34), Qt.AlignCenter, glyph)

    def _paint_picker(self, p, r):
        """Mini-Auswahl über dem Aufnahme-Knopf: Mikrofon / Laptop-Ton / Beides."""
        c = self.colors
        row_h, pad, w = 30, 6, 136
        h = len(SOURCES) * row_h + 2 * pad
        x = max(4.0, r.center().x() + SLOTS["record"] - 22)
        box = QRectF(x, r.top() - 8 - h, w, h)
        p.setPen(Qt.NoPen)
        for i in range(5, 0, -1):
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(box.adjusted(-i, -i + 2, i, i + 2), 14 + i, 14 + i)
        p.setBrush(QColor(c["pill"]))
        p.setPen(QPen(QColor(c["line"]), 1))
        p.drawRoundedRect(box, 14, 14)
        f = QFont("Inter", 10)
        f.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias))
        p.setFont(f)
        self._picker_rows = []
        for i, (key, text) in enumerate(SOURCES):
            row = QRectF(box.left() + 4, box.top() + pad + i * row_h, w - 8, row_h)
            self._picker_rows.append((row, key))
            if key == self._picker_hover:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c["hover"]))
                p.drawRoundedRect(row, 10, 10)
            dot = QPointF(row.left() + 14, row.center().y())
            fg = QColor(c["pill_fg"])
            if key == self.rec_source:              # gewählte Quelle: gefüllter Punkt
                p.setPen(Qt.NoPen)
                p.setBrush(fg)
                p.drawEllipse(dot, 3.5, 3.5)
            else:
                fg.setAlpha(110)
                p.setPen(QPen(fg, 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(dot, 3.5, 3.5)
            tc = QColor(c["pill_fg"])
            tc.setAlpha(240 if key == self.rec_source else 170)
            p.setPen(tc)
            p.drawText(row.adjusted(28, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _text(self, p, r, s, size, color):
        f = QFont("Segoe UI", size)
        f.setWeight(QFont.Medium)
        p.setFont(f)
        p.setPen(color)
        p.drawText(r, Qt.AlignCenter, s)

    def _paint_bars(self, p, r, color=None):
        n = BARS
        hf = self.state in ("handsfree", "command")
        area_w = 96 if hf else min(r.width() - 36, 110)
        gap = area_w / n
        bw = max(2.0, gap * 0.45)
        cx, cy = r.center().x() + (12 if hf else 0), r.center().y()   # Platz für den Timer
        x0 = cx - area_w / 2 + gap / 2
        max_h = r.height() - 14
        p.setPen(Qt.NoPen)
        p.setBrush(color or QColor(255, 255, 255, 235))
        for i, v in enumerate(self._bars):
            h = max(3.0, v * max_h)
            p.drawRoundedRect(QRectF(x0 + i * gap - bw / 2, cy - h / 2, bw, h), bw / 2, bw / 2)

    def _paint_handsfree(self, p, r):
        cy = r.center().y()
        # links ✕ (abbrechen), rechts ✓ (fertig), dazu Laufzeit
        p.setBrush(QColor(255, 255, 255, 30))
        p.setPen(Qt.NoPen)
        for cx in (r.left() + 20, r.right() - 20):
            p.drawEllipse(QPointF(cx, cy), 12, 12)
        pen = QPen(QColor(255, 255, 255, 220), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        x = r.left() + 20
        p.drawLine(QPointF(x - 4, cy - 4), QPointF(x + 4, cy + 4))
        p.drawLine(QPointF(x - 4, cy + 4), QPointF(x + 4, cy - 4))
        x = r.right() - 20
        path = QPainterPath(QPointF(x - 5, cy))
        path.lineTo(x - 1.5, cy + 3.5)
        path.lineTo(x + 5, cy - 4)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        secs = int(self.elapsed())
        f = QFont("Segoe UI", 9)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(QRectF(r.left() + 36, r.top(), 40, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{secs // 60}:{secs % 60:02d}")

    def _paint_dots(self, p, r):
        t = time.monotonic()
        cx, cy = r.center().x(), r.center().y()
        p.setPen(Qt.NoPen)
        for i in range(5):
            phase = t * 6 - i * 0.7
            dy = math.sin(phase) * 4
            a = int(140 + 100 * (math.sin(phase) + 1) / 2)
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(cx + (i - 2) * 11, cy + dy), 2.6, 2.6)

    def _paint_check(self, p, r):
        cx, cy = r.center().x(), r.center().y()
        pen = QPen(QColor(255, 255, 255), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(cx - 8, cy))
        path.lineTo(cx - 2.5, cy + 5.5)
        path.lineTo(cx + 8.5, cy - 6)
        p.drawPath(path)

    def _paint_loading(self, p, r):
        # dünner Fortschrittsstrich (unbestimmt: wandernder Abschnitt)
        inner = r.adjusted(3, 3.5, -3, -3.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(inner, inner.height() / 2, inner.height() / 2)
        t = (time.monotonic() - self._t0) % 1.4 / 1.4
        seg_w = inner.width() * 0.35
        x = inner.left() - seg_w + (inner.width() + seg_w) * t
        seg = QRectF(max(inner.left(), x), inner.top(),
                     min(inner.right(), x + seg_w) - max(inner.left(), x), inner.height())
        if seg.width() > 0:
            p.setBrush(QColor(255, 255, 255, 220))
            p.drawRoundedRect(seg, seg.height() / 2, seg.height() / 2)
