"""Hauptfenster: Sidebar links, Inhalt rechts. Home · Verlauf · Einstellungen.

Design-Ideen: viel Weißraum, große Serif-Überschriften, Karten mit 1-px-Rand statt Schatten,
weiche Seitenwechsel (Einblenden) und hochzählende Statistik-Zahlen.
"""
import ctypes
import time
from datetime import datetime

from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QVariantAnimation,
                            Property, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

import storage
import theme

APP_NAMES = {"winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "outlook": "Outlook",
             "olk": "Outlook", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "code": "VS Code",
             "cursor": "Cursor", "discord": "Discord", "whatsapp": "WhatsApp", "telegram": "Telegram",
             "slack": "Slack", "notepad": "Editor", "windowsterminal": "Terminal", "obsidian": "Obsidian",
             "claude": "Claude", "opera": "Opera GX", "teams": "Teams", "ms-teams": "Teams"}


def pretty_app(exe: str) -> str:
    base = exe.lower().removesuffix(".exe")
    return APP_NAMES.get(base, base[:1].upper() + base[1:])


HOTKEYS = {"Strg + Win": ["ctrl", "win"], "Strg + Alt": ["ctrl", "alt"],
           "Strg + Shift": ["ctrl", "shift"], "Rechte Strg": ["rctrl"]}


# ====================================================================== Bausteine
class Toggle(QAbstractButton):
    """iOS-artiger Schalter mit weicher Animation (QSS kann so etwas nicht)."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._go)
        self.on_color, self.off_color, self.knob_color = "#1E5A47", "#D9D5CA", "#FFFFFF"

    def _go(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(self.off_color), QColor(self.on_color)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 0, 42, 24, 12, 12)
        p.setBrush(QColor(self.knob_color))
        p.drawEllipse(3 + int(18 * t), 3, 18, 18)


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options, current, disabled=(), tips=None):
        super().__init__()
        self.setObjectName("segbox")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        for key, label in options:
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == current)
            b.setEnabled(key not in disabled)
            if tips and key in tips:
                b.setToolTip(tips[key])
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)


def label(text, obj=None, wrap=False):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def card():
    c = QFrame()
    c.setObjectName("card")
    return c


class StatCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(4)
        lay.addWidget(label(title.upper(), "section"))
        self.num = label("0", "statnum")
        lay.addWidget(self.num)
        self.sub = label("", "muted")
        lay.addWidget(self.sub)
        self._anim = QVariantAnimation(self, duration=900, easingCurve=QEasingCurve.OutCubic)
        self._fmt = str
        self._anim.valueChanged.connect(lambda v: self.num.setText(self._fmt(v)))

    def count_to(self, value, fmt=lambda v: f"{int(round(v)):,}".replace(",", ".")):
        self._fmt = fmt
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(value))
        self._anim.start()


# ======================================================================= Fenster
class MainWindow(QWidget):
    setting_changed = Signal(str, object)     # (Schlüssel, Wert) -> Controller

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.setWindowTitle("Murmel")
        self.setObjectName("root")
        self.resize(1040, 700)
        self.setMinimumSize(860, 560)
        self.t = theme.tokens(self.cfg.get("theme", "system"))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.pages = {"home": self._home(), "history": self._history(), "settings": self._settings()}
        for w in self.pages.values():
            self.stack.addWidget(self._scroll(w))

        self._level_timer = QTimer(self, interval=66)
        self._level_timer.timeout.connect(self._tick_level)
        self.apply_theme()
        self.show_page("home")

    # ---------------------------------------------------------------- Theme
    def apply_theme(self):
        self.t = theme.tokens(self.cfg.get("theme", "system"))
        self.setStyleSheet(theme.qss(self.t))
        for key, btn in self.nav.items():
            btn.setIcon(theme.icon(btn.property("iconName"), self.t["text"], 18))
        self.brand_logo.setPixmap(self._logo_pm())
        for tg in self.findChildren(Toggle):
            tg.on_color, tg.off_color = self.t["accent"], self.t["line"]
            tg.knob_color = "#FFFFFF" if not theme.is_dark(self.cfg.get("theme")) else "#EDEDED"
            tg.update()
        self.search_icon.setPixmap(theme.icon_pixmap("search", self.t["faint"], 16))
        self._dark_titlebar()
        if self.isVisible():
            self.refresh()

    def _dark_titlebar(self):
        """Titelleiste an den Hintergrund angleichen (Win11: Caption-Farbe setzen)."""
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(1 if theme.is_dark(self.cfg.get("theme")) else 0)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            def colorref(hexc):
                h = hexc.lstrip("#")
                return ctypes.c_uint(int(h[4:6] + h[2:4] + h[0:2], 16))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref(self.t["sidebar"])), 4)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(colorref(self.t["text"])), 4)
        except Exception:
            pass

    def _logo_pm(self, size=30):
        import numpy as np
        import logo
        dpr = self.devicePixelRatioF() or 1.5
        px = int(size * dpr)
        arr = np.ascontiguousarray(logo.render_icon(px))
        pm = QPixmap.fromImage(QImage(arr.data, px, px, 4 * px, QImage.Format_RGBA8888).copy())
        pm.setDevicePixelRatio(dpr)
        return pm

    # -------------------------------------------------------------- Sidebar
    def _sidebar(self):
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(224)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(18, 22, 18, 18)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.brand_logo = QLabel()
        top.addWidget(self.brand_logo)
        top.addWidget(label("Murmel", "brand"))
        top.addStretch()
        lay.addLayout(top)
        lay.addSpacing(26)
        self.nav = {}
        for key, text, ic in (("home", "Home", "house"), ("history", "Verlauf", "history"),
                              ("settings", "Einstellungen", "settings")):
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("iconName", ic)
            b.setIconSize(QSize(18, 18))
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            lay.addWidget(b)
            self.nav[key] = b
        lay.addStretch()
        self.status = label("", "chip")
        self.status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status, 0, Qt.AlignLeft)
        lay.addSpacing(6)
        lay.addWidget(label("Strg + Win halten und sprechen", "muted", wrap=True))
        return sb

    def set_status(self, text):
        self.status.setText(text)

    def _scroll(self, w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(w)
        return sa

    def show_page(self, key):
        for k, b in self.nav.items():
            b.setChecked(k == key)
        idx = list(self.pages).index(key)
        page = self.stack.widget(idx)
        self.stack.setCurrentIndex(idx)
        # weiches Einblenden
        eff = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", page)
        a.setDuration(220)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: page.setGraphicsEffect(None))
        a.start()
        self._page_anim = a
        self.current = key
        if key == "settings":
            self._level_timer.start()
        else:
            self._level_timer.stop()
        self.refresh()

    def refresh(self):
        if self.current == "home":
            self._refresh_home()
        elif self.current == "history":
            self._refresh_history()

    # ------------------------------------------------------------------ Home
    def _page(self):
        w = QWidget()
        w.setObjectName("page")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(56, 48, 56, 48)
        lay.setSpacing(0)
        return w, lay

    def _home(self):
        w, lay = self._page()
        self.greet = label("", "h1")
        lay.addWidget(self.greet)
        lay.addSpacing(6)
        lay.addWidget(label("Halte Strg + Win, sprich, lass los – der Text landet dort, wo dein Cursor ist.", "sub"))
        lay.addSpacing(32)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.st_today = StatCard("Wörter heute")
        self.st_wpm = StatCard("Wörter pro Minute")
        self.st_saved = StatCard("Gesparte Zeit")
        for c in (self.st_today, self.st_wpm, self.st_saved):
            row.addWidget(c)
        lay.addLayout(row)
        lay.addSpacing(28)

        lay.addWidget(label("PROBIER'S AUS", "section"))
        lay.addSpacing(10)
        self.tryout = QPlainTextEdit()
        self.tryout.setPlaceholderText("Klick hier rein, halte Strg + Win und sag etwas …")
        self.tryout.setFixedHeight(96)
        lay.addWidget(self.tryout)
        lay.addSpacing(28)

        lay.addWidget(label("ZULETZT", "section"))
        lay.addSpacing(10)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        rc = card()
        rc.setLayout(self.recent_box)
        self.recent_box.setContentsMargins(20, 6, 20, 6)
        lay.addWidget(rc)
        lay.addStretch()
        return w

    def _refresh_home(self):
        h = datetime.now().hour
        part = "Guten Morgen" if h < 11 else "Hallo" if h < 17 else "Guten Abend"
        name = self.cfg.get("name") or ""
        self.greet.setText(f"{part}, {name}" if name else part)
        s = storage.stats()
        self.st_today.count_to(s["today"])
        self.st_today.sub.setText(f"{s['week']:,} diese Woche".replace(",", "."))
        self.st_wpm.count_to(s["wpm"])
        self.st_wpm.sub.setText("beim Sprechen")
        self.st_saved.count_to(s["saved_min"], lambda v: f"{int(v * 60)} s" if v < 1 else f"{int(v)} min" if v < 120 else f"{v / 60:.1f} h")
        self.st_saved.sub.setText(f"Streak: {s['streak']} {'Tag' if s['streak'] == 1 else 'Tage'}")
        self._fill_rows(self.recent_box, storage.history(limit=5), compact=True)

    def _fill_rows(self, box, rows, compact=False):
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not rows:
            e = label("Noch nichts diktiert. Halte Strg + Win und leg los.", "muted")
            e.setContentsMargins(0, 14, 0, 14)
            box.addWidget(e)
            return
        for i, r in enumerate(rows):
            box.addWidget(self._entry(r, compact, last=(i == len(rows) - 1)))

    def _entry(self, r, compact, last=False):
        f = QFrame()
        f.setObjectName("row" if compact and not last else ("histrow" if not compact else ""))
        lay = QHBoxLayout(f)
        lay.setContentsMargins(0 if compact else 18, 12, 0 if compact else 10, 12)
        lay.setSpacing(12)
        txt = QVBoxLayout()
        txt.setSpacing(3)
        when = datetime.fromtimestamp(r["ts"])
        app = pretty_app(r.get("app") or "")
        meta = when.strftime("%H:%M") if when.date() == datetime.now().date() else when.strftime("%d.%m. %H:%M")
        txt.addWidget(label(f"{meta}  ·  {app}" if app else meta, "faint"))
        body = label(r["clean"], None, wrap=True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("font-size: 14px;")
        txt.addWidget(body)
        if not compact:
            raw = label(f"Roh: {r['raw']}", "muted", wrap=True)
            raw.setVisible(False)
            txt.addWidget(raw)
        lay.addLayout(txt, 1)
        for ic, tip, fn in (("copy", "Kopieren", lambda: self._copy(r["clean"])),) + (
                (("search", "Rohtext zeigen", lambda: raw.setVisible(not raw.isVisible())),
                 ("trash-2", "Löschen", lambda: self._delete(r["id"]))) if not compact else ()):
            b = QToolButton()
            b.setObjectName("iconbtn")
            b.setIcon(theme.icon(ic, self.t["muted"], 16))
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            lay.addWidget(b, 0, Qt.AlignTop)
        return f

    def _copy(self, text):
        QGuiApplication.clipboard().setText(text)

    # ---------------------------------------------------------------- Verlauf
    def _history(self):
        w, lay = self._page()
        top = QHBoxLayout()
        top.addWidget(label("Verlauf", "h2"))
        top.addStretch()
        clear = QPushButton("Alles löschen")
        clear.setObjectName("danger")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_all)
        top.addWidget(clear)
        lay.addLayout(top)
        lay.addSpacing(18)
        sr = QFrame()
        srl = QHBoxLayout(sr)
        srl.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen …")
        self.search.setTextMargins(26, 0, 0, 0)
        self.search_icon = QLabel(self.search)
        self.search_icon.move(14, 13)
        srl.addWidget(self.search)
        lay.addWidget(sr)
        self._search_timer = QTimer(self, singleShot=True, interval=200)
        self._search_timer.timeout.connect(self._refresh_history)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        lay.addSpacing(16)
        self.hist_box = QVBoxLayout()
        self.hist_box.setSpacing(10)
        lay.addLayout(self.hist_box)
        lay.addStretch()
        return w

    def _refresh_history(self):
        self._fill_rows(self.hist_box, storage.history(self.search.text().strip(), limit=200))

    def _delete(self, entry_id):
        storage.delete_history(entry_id)
        self.refresh()

    def _clear_all(self):
        if QMessageBox.question(self, "Murmel", "Den ganzen Verlauf löschen? Das kann man nicht rückgängig machen.") \
                == QMessageBox.Yes:
            storage.delete_history()
            self.refresh()

    # ----------------------------------------------------------- Einstellungen
    def _setting_row(self, box, title, hint, widget, last=False):
        row = QFrame()
        row.setObjectName("" if last else "row")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 14, 0, 14)
        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.addWidget(label(title))
        if hint is not None:
            h = label(hint, "muted", wrap=True)
            txt.addWidget(h)
            self._hints = getattr(self, "_hints", {})
            self._hints[title] = h
        rl.addLayout(txt, 1)
        rl.addWidget(widget, 0, Qt.AlignRight | Qt.AlignVCenter)
        box.addWidget(row)

    def _group(self, lay, title):
        lay.addWidget(label(title.upper(), "section"))
        lay.addSpacing(10)
        c = card()
        cl = QVBoxLayout(c)
        cl.setContentsMargins(22, 4, 22, 4)
        cl.setSpacing(0)
        lay.addWidget(c)
        lay.addSpacing(26)
        return cl

    def _settings(self):
        w, lay = self._page()
        lay.addWidget(label("Einstellungen", "h2"))
        lay.addSpacing(26)
        c = self.cfg

        g = self._group(lay, "Mikrofon")
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Windows-Standard", None)
        for idx, name in self.ctl.list_mics():
            self.mic_combo.addItem(name, idx)
        cur = self.mic_combo.findData(c.get("mic_device"))
        self.mic_combo.setCurrentIndex(max(0, cur))
        self.mic_combo.currentIndexChanged.connect(
            lambda _: self.setting_changed.emit("mic_device", self.mic_combo.currentData()))
        self._setting_row(g, "Eingabegerät", None, self.mic_combo)
        self.level = QProgressBar()
        self.level.setObjectName("level")
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(220)
        self._setting_row(g, "Pegel", "Sprich etwas – der Balken sollte sich bewegen.", self.level, last=True)

        g = self._group(lay, "Diktieren")
        hk = QComboBox()
        hk.addItems(list(HOTKEYS))
        cur_name = next((k for k, v in HOTKEYS.items() if v == c.get("hotkey")), "Strg + Win")
        hk.setCurrentText(cur_name)
        hk.currentTextChanged.connect(lambda t: self.setting_changed.emit("hotkey", HOTKEYS[t]))
        self._setting_row(g, "Tastenkürzel", "Halten zum Sprechen, doppelt tippen für Freihand.", hk)
        lang = Segmented([("auto", "Auto (DE/EN)"), ("de", "Deutsch"), ("en", "Englisch")], c.get("language", "auto"))
        lang.changed.connect(lambda v: self.setting_changed.emit("language", v))
        self._setting_row(g, "Sprache", None, lang)
        edit = Segmented([("off", "Aus"), ("normal", "Normal"), ("strong", "Stark")], c.get("cleanup", "normal"),
                         disabled=("strong",), tips={"strong": "Braucht Ollama – kommt in Phase 3"})
        edit.changed.connect(lambda v: self.setting_changed.emit("cleanup", v))
        self._setting_row(g, "Auto-Edit", "Füllwörter, Selbstkorrekturen, „neue Zeile“, Listen.", edit)
        self.engine_label = label("", "chip")
        self._setting_row(g, "Erkennung", "", self.engine_label, last=True)

        g = self._group(lay, "Allgemein")
        name = QLineEdit(c.get("name", ""))
        name.setPlaceholderText("Dein Name")
        name.setFixedWidth(220)
        name.editingFinished.connect(lambda: self.setting_changed.emit("name", name.text().strip()))
        self._setting_row(g, "Name", "Für die Begrüßung auf Home.", name)
        snd = Toggle(bool(c.get("sounds", True)))
        snd.toggled.connect(lambda v: self.setting_changed.emit("sounds", v))
        self._setting_row(g, "Sounds", "Leiser Ton beim Start und Ende der Aufnahme.", snd)
        th = Segmented([("light", "Hell"), ("dark", "Dunkel"), ("system", "System")], c.get("theme", "system"))
        th.changed.connect(lambda v: self.setting_changed.emit("theme", v))
        self._setting_row(g, "Design", None, th, last=True)
        lay.addStretch()
        return w

    def set_engine(self, text, gpu: bool):
        self.engine_label.setText(text)
        h = getattr(self, "_hints", {}).get("Erkennung")
        if h:
            h.setText("Läuft auf der Grafikkarte – schnell." if gpu else
                      "Läuft auf dem Prozessor. Für < 1,5 s die GPU in Armoury Crate auf „Standard“ stellen.")

    def _tick_level(self):
        import math
        lv = self.ctl.mic.level
        db = 20 * math.log10(max(lv, 1e-5))
        self.level.setValue(int(max(0, min(100, (db + 55) / 40 * 100))))

    # ------------------------------------------------------------------ Fenster
    def open(self, page="home"):
        self.show_page(page)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        e.ignore()          # Schließen = in den Tray
        self._level_timer.stop()
        self.hide()
