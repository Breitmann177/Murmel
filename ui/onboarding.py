"""Erster Start: 5 kurze Schritte. Willkommen → Mikrofon → Modell → Ausprobieren → Fertig."""
import math

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

import theme


def _label(text, obj=None, wrap=True, center=True):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    if center:
        lb.setAlignment(Qt.AlignHCenter)
    return lb


class Onboarding(QWidget):
    finished = Signal()

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("root")
        self.setWindowTitle("Willkommen bei Murmel")
        self.setFixedSize(620, 560)
        t = theme.tokens(ctl.cfg.get("theme", "system"))
        self.t = t
        self.setStyleSheet(theme.qss(t) + f"QLabel#h1 {{ font-size: 40px; }} QFrame#dot {{ border-radius: 4px; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 32)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.dots = []
        dots = QHBoxLayout()
        dots.setSpacing(8)
        for _ in range(5):
            d = QFrame()
            d.setObjectName("dot")
            d.setFixedSize(8, 8)
            dots.addWidget(d)
            self.dots.append(d)
        bottom.addLayout(dots)
        bottom.addStretch()
        self.back = QPushButton("Zurück")
        self.back.setObjectName("ghost")
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next = QPushButton("Weiter")
        self.next.setObjectName("primary")
        self.next.clicked.connect(self._next)
        for b in (self.back, self.next):
            b.setCursor(Qt.PointingHandCursor)
            bottom.addWidget(b)
        lay.addLayout(bottom)

        for build in (self._welcome, self._mic, self._model, self._try, self._done):
            self.stack.addWidget(build())
        self._timer = QTimer(self, interval=66)
        self._timer.timeout.connect(self._tick)
        self.go(0)

    # ------------------------------------------------------------- Seiten
    def _page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(12)
        l.addStretch()
        return w, l

    def _welcome(self):
        w, l = self._page()
        logo = QLabel()
        logo.setAlignment(Qt.AlignHCenter)
        logo.setPixmap(self._logo(72))
        l.addWidget(logo)
        l.addSpacing(8)
        l.addWidget(_label("Willkommen bei Murmel", "h1"))
        l.addWidget(_label("Diktieren in jeder App – Taste halten, sprechen, loslassen. "
                           "Alles läuft lokal auf deinem Laptop, nichts geht ins Internet.", "sub"))
        l.addStretch()
        return w

    def _mic(self):
        w, l = self._page()
        l.addWidget(_label("Mikrofon testen", "h1"))
        l.addWidget(_label("Sag etwas – der Balken sollte sich bewegen.", "sub"))
        l.addSpacing(16)
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Windows-Standard", None)
        for idx, name in self.ctl.list_mics():
            self.mic_combo.addItem(name, idx)
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(self.ctl.cfg.get("mic_device"))))
        self.mic_combo.currentIndexChanged.connect(
            lambda _: self.ctl.change_setting("mic_device", self.mic_combo.currentData()))
        l.addWidget(self.mic_combo, 0, Qt.AlignHCenter)
        l.addSpacing(10)
        self.level = QProgressBar()
        self.level.setObjectName("level")
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(320)
        l.addWidget(self.level, 0, Qt.AlignHCenter)
        l.addStretch()
        return w

    def _model(self):
        w, l = self._page()
        l.addWidget(_label("Sprachmodell", "h1"))
        self.model_text = _label("", "sub")
        l.addWidget(self.model_text)
        l.addSpacing(14)
        self.model_bar = QProgressBar()
        self.model_bar.setObjectName("level")
        self.model_bar.setTextVisible(False)
        self.model_bar.setFixedWidth(320)
        l.addWidget(self.model_bar, 0, Qt.AlignHCenter)
        self.model_hint = _label("", "muted")
        l.addWidget(self.model_hint)
        l.addStretch()
        return w

    def _try(self):
        w, l = self._page()
        l.addWidget(_label("Probier's aus", "h1"))
        l.addWidget(_label("Klick ins Feld, halte Strg + Win und sag zum Beispiel: "
                           "„Hallo Murmel, das ist mein erstes Diktat.“", "sub"))
        l.addSpacing(10)
        self.try_box = QPlainTextEdit()
        self.try_box.setFixedHeight(110)
        self.try_box.setPlaceholderText("Hier landet dein Text …")
        self.try_box.textChanged.connect(self._tried)
        l.addWidget(self.try_box)
        self.try_ok = _label("", "muted")
        l.addWidget(self.try_ok)
        l.addStretch()
        return w

    def _done(self):
        w, l = self._page()
        logo = QLabel()
        logo.setAlignment(Qt.AlignHCenter)
        logo.setPixmap(self._logo(56))
        l.addWidget(logo)
        l.addWidget(_label("Fertig!", "h1"))
        l.addWidget(_label("Die kleine Pille unten wartet auf dich. Fahr mit der Maus drüber für Optionen, "
                           "zweimal Strg + Win tippen startet den Freihand-Modus. Murmel läuft im Tray weiter.",
                           "sub"))
        l.addStretch()
        return w

    # ------------------------------------------------------------- Logik
    def _logo(self, size):
        import numpy as np
        import logo
        dpr = self.devicePixelRatioF() or 1.5
        px = int(size * dpr)
        arr = np.ascontiguousarray(logo.render_icon(px))
        pm = QPixmap.fromImage(QImage(arr.data, px, px, 4 * px, QImage.Format_RGBA8888).copy())
        pm.setDevicePixelRatio(dpr)
        return pm

    def _tried(self):
        if self.try_box.toPlainText().strip():
            self.try_ok.setText("✓ Perfekt – genau so funktioniert's überall.")

    def go(self, i):
        i = max(0, min(4, i))
        self.stack.setCurrentIndex(i)
        page = self.stack.currentWidget()
        eff = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", page)
        a.setDuration(240)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: page.setGraphicsEffect(None))
        a.start()
        self._anim = a
        self.back.setVisible(i > 0)
        self.next.setText("Los geht's" if i == 4 else "Weiter")
        for k, d in enumerate(self.dots):
            d.setStyleSheet(f"background: {self.t['accent'] if k == i else self.t['line']};")
        if i in (1, 2):
            self._timer.start()
        else:
            self._timer.stop()
        if i == 3:
            self.try_box.setFocus()
        self._tick()

    def _next(self):
        if self.stack.currentIndex() == 4:
            self.finished.emit()
            self.close()
        else:
            self.go(self.stack.currentIndex() + 1)

    def _tick(self):
        i = self.stack.currentIndex()
        if i == 1:
            lv = self.ctl.mic.level
            db = 20 * math.log10(max(lv, 1e-5))
            self.level.setValue(int(max(0, min(100, (db + 55) / 40 * 100))))
        elif i == 2:
            if self.ctl.ready:
                self.model_bar.setRange(0, 1)
                self.model_bar.setValue(1)
                self.model_text.setText(f"Bereit: {self.ctl.engine_text}")
                self.model_hint.setText("" if self.ctl.engine_gpu else
                                        "Läuft auf dem Prozessor (~2 s pro Diktat). Mit der Grafikkarte "
                                        "wird's deutlich schneller.")
            else:
                self.model_bar.setRange(0, 0)          # unbestimmter Fortschritt
                self.model_text.setText("Wird geladen … beim allerersten Mal auch heruntergeladen.")
                self.model_hint.setText("")
