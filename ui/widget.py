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
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

WIN_W, WIN_H = 320, 96          # festes (unsichtbares) Fenster, Pille wird darin gezeichnet
BOTTOM_GAP = 12                 # Abstand der Pille zur Taskleiste
BARS = 12

SIZES = {                        # (Breite, Höhe) der Pille je Zustand
    "loading": (96, 10),
    "idle": (40, 8),
    "hover": (138, 32),
    "recording": (164, 40),
    "handsfree": (232, 40),
    "processing": (164, 40),
    "done": (164, 40),
    "error": (240, 40),
}


class Pill(QWidget):
    cancel_clicked = Signal()
    finish_clicked = Signal()

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

        self.place()

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
        if state in ("recording", "handsfree"):
            self._rec_t0 = time.monotonic() if state == "recording" or not self._rec_t0 else self._rec_t0
        key = "hover" if state == "idle" and self._hovered else state
        w, h = SIZES[key]
        if state == "error" and message:
            w = max(160, min(300, 56 + len(message) * 7))
        self._animate_to(w, h, bounce=state in ("recording", "handsfree", "hover"))
        if hold_ms:
            self._back.start(hold_ms)
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
        if self.state in ("idle", "error") and self._anim.state() != QPropertyAnimation.Running:
            self._tick.stop()

    def _on_tick(self):
        if self.state in ("recording", "handsfree"):
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
    def enterEvent(self, e):
        self._hovered = True
        if self.state == "idle":
            self.set_state("idle")

    def leaveEvent(self, e):
        self._hovered = False
        if self.state == "idle":
            self.set_state("idle")

    def mousePressEvent(self, e):
        if self.state != "handsfree":
            return
        r = self.pill_rect()
        x = e.position().x()
        if x < r.left() + 36:
            self.cancel_clicked.emit()
        elif x > r.right() - 36:
            self.finish_clicked.emit()

    # ------------------------------------------------------------ Zeichnen
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.pill_rect()
        rad = r.height() / 2
        idle = self.state == "idle" and not self._hovered
        loading = self.state == "loading"

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
        elif self.state in ("recording", "handsfree"):
            self._paint_bars(p, r)
            if self.state == "handsfree" and r.width() > 200:
                self._paint_handsfree(p, r)
        elif self.state == "processing":
            self._paint_dots(p, r)
        elif self.state == "done":
            self._paint_check(p, r)
        elif self.state == "error" and r.width() > 120:
            self._text(p, r, self.message, 11, white)
        p.end()

    def _text(self, p, r, s, size, color):
        f = QFont("Segoe UI", size)
        f.setWeight(QFont.Medium)
        p.setFont(f)
        p.setPen(color)
        p.drawText(r, Qt.AlignCenter, s)

    def _paint_bars(self, p, r):
        n = BARS
        hf = self.state == "handsfree"
        area_w = 96 if hf else min(r.width() - 36, 110)
        gap = area_w / n
        bw = max(2.0, gap * 0.45)
        cx, cy = r.center().x() + (12 if hf else 0), r.center().y()   # Platz für den Timer
        x0 = cx - area_w / 2 + gap / 2
        max_h = r.height() - 14
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
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
        secs = int(time.monotonic() - self._rec_t0)
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
