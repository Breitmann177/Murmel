"""Hauptfenster: Sidebar links, Inhalt rechts. Home · Verlauf · Einstellungen.

Design-Ideen: viel Weißraum, große Serif-Überschriften, Karten mit 1-px-Rand statt Schatten,
weiche Seitenwechsel (Einblenden) und hochzählende Statistik-Zahlen.
"""
import ctypes
import time
from datetime import datetime

from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QVariantAnimation,
                            Property, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

import osapi
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


HOTKEYS = {osapi.combo_text(k): k for k in (["ctrl", "win"], ["ctrl", "alt"], ["ctrl", "shift"], ["rctrl"])}


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

        self.pages = {"home": self._home(), "history": self._history(), "dictionary": self._dictionary(),
                      "snippets": self._snippets(), "styles": self._styles(), "settings": self._settings()}
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
        self.search_action.setIcon(theme.icon("search", self.t["faint"], 16))
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
                              ("dictionary", "Wörterbuch", "book-a"), ("snippets", "Snippets", "scissors"),
                              ("styles", "Stile", "palette"), ("settings", "Einstellungen", "settings")):
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
        fn = {"home": self._refresh_home, "history": self._refresh_history,
              "dictionary": self._refresh_dictionary, "snippets": self._refresh_snippets,
              "styles": self._refresh_styles, "settings": self._refresh_settings}.get(self.current)
        if fn:
            fn()

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

    def _fill_rows(self, box, rows, compact=False, open_=False):
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not rows:
            e = label("Noch nichts diktiert.", "muted")
            e.setContentsMargins(0, 14, 0, 14)
            box.addWidget(e)
            return
        for i, r in enumerate(rows):
            box.addWidget(self._entry(r, compact, last=(i == len(rows) - 1), open_=open_))

    @staticmethod
    def _when(ts):
        when = datetime.fromtimestamp(ts)
        days = (datetime.now().date() - when.date()).days
        day = "Heute" if days == 0 else "Gestern" if days == 1 else when.strftime("%d.%m.%Y")
        return f"{day}, {when:%H:%M}"

    def _entry(self, r, compact, last=False, open_=False):
        """Eine Zeile: nur Datum, App und Länge – der Text klappt erst auf Wunsch auf
        (lange Vorlesungs-Diktate würden sonst die ganze Seite füllen)."""
        f = QFrame()
        f.setObjectName("row" if compact and not last else ("histrow" if not compact else ""))
        outer = QVBoxLayout(f)
        outer.setContentsMargins(0 if compact else 18, 12, 0 if compact else 10, 12)
        outer.setSpacing(8)
        lay = QHBoxLayout()
        lay.setSpacing(6)
        outer.addLayout(lay)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        title = label(self._when(r["ts"]))
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        txt.addWidget(title)
        app = pretty_app(r.get("app") or "")
        words = r.get("words") or len(r["clean"].split())
        txt.addWidget(label(" · ".join(x for x in (app, f"{words} Wörter") if x), "muted"))
        lay.addLayout(txt, 1)

        body = label(r["clean"], None, wrap=True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("font-size: 14px;")
        body.setVisible(open_)
        outer.addWidget(body)

        def toggle():
            body.setVisible(not body.isVisible())
            arrow.setIcon(theme.icon("chevron-up" if body.isVisible() else "chevron-down", self.t["muted"], 16))

        def copy():
            self._copy(r["clean"])
            cp.setIcon(theme.icon("clipboard-check", self.t["accent"], 16))
            QTimer.singleShot(1300, lambda: cp.setIcon(theme.icon("copy", self.t["muted"], 16)))

        def btn(ic, tip, fn):
            b = QToolButton()
            b.setObjectName("iconbtn")
            b.setIcon(theme.icon(ic, self.t["muted"], 16))
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            lay.addWidget(b, 0, Qt.AlignVCenter)
            return b

        cp = btn("copy", "Text kopieren", copy)
        arrow = btn("chevron-up" if open_ else "chevron-down", "Text anzeigen", toggle)
        if not compact:
            btn("trash-2", "Löschen", lambda: self._delete(r["id"]))
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
        self.search.setClearButtonEnabled(True)
        # Lupe als echtes Feld-Symbol (vorher ein drübergelegtes Bild, das verrutschen konnte)
        self.search_action = self.search.addAction(QIcon(), QLineEdit.LeadingPosition)
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
        q = self.search.text().strip()
        rows = storage.history(q, limit=200)
        self._fill_rows(self.hist_box, rows, open_=bool(q))     # bei Suche Treffer gleich aufgeklappt
        if q and not rows:
            self.hist_box.itemAt(0).widget().setText(f"Nichts gefunden für „{q}“.")

    def _delete(self, entry_id):
        storage.delete_history(entry_id)
        self.refresh()

    def _clear_all(self):
        if QMessageBox.question(self, "Murmel", "Den ganzen Verlauf löschen? Das kann man nicht rückgängig machen.") \
                == QMessageBox.Yes:
            storage.delete_history()
            self.refresh()

    # ---------------------------------------------------- Listen-Hilfsbausteine
    def _list_page(self, title, intro):
        w, lay = self._page()
        lay.addWidget(label(title, "h2"))
        lay.addSpacing(6)
        lay.addWidget(label(intro, "sub", wrap=True))
        lay.addSpacing(22)
        return w, lay

    def _form_card(self, lay, fields, button_text, on_add):
        c = card()
        cl = QHBoxLayout(c)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)
        for f in fields:
            cl.addWidget(f, f.property("stretch") or 1)
        b = QPushButton(button_text)
        b.setObjectName("primary")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(on_add)
        cl.addWidget(b)
        for f in fields:
            if isinstance(f, QLineEdit):
                f.returnPressed.connect(on_add)
        lay.addWidget(c)
        lay.addSpacing(18)

    def _simple_rows(self, box, rows, empty_text):
        """rows: Liste von (Titel, Untertitel, Lösch-Callback)."""
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not rows:
            e = label(empty_text, "muted", wrap=True)
            e.setContentsMargins(4, 6, 0, 6)
            box.addWidget(e)
            return
        for title, sub, on_del in rows:
            f = QFrame()
            f.setObjectName("histrow")
            fl = QHBoxLayout(f)
            fl.setContentsMargins(18, 12, 10, 12)
            tl = QVBoxLayout()
            tl.setSpacing(2)
            t = label(title, None, wrap=True)
            t.setStyleSheet("font-size: 14px; font-weight: 600;")
            tl.addWidget(t)
            if sub:
                tl.addWidget(label(sub, "muted", wrap=True))
            fl.addLayout(tl, 1)
            b = QToolButton()
            b.setObjectName("iconbtn")
            b.setIcon(theme.icon("trash-2", self.t["muted"], 16))
            b.setToolTip("Löschen")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(on_del)
            fl.addWidget(b, 0, Qt.AlignTop)
            box.addWidget(f)

    # -------------------------------------------------------------- Wörterbuch
    def _dictionary(self):
        w, lay = self._list_page("Wörterbuch", "Namen und Fachwörter, die Murmel richtig schreiben soll. "
                                 "Optional: wie es oft falsch erkannt wird – das wird dann automatisch ersetzt.")
        self.dict_word = QLineEdit()
        self.dict_word.setPlaceholderText("Richtig, z. B. ein Name")
        self.dict_heard = QLineEdit()
        self.dict_heard.setPlaceholderText("Wird erkannt als … (optional)")
        self._form_card(lay, [self.dict_word, self.dict_heard], "Hinzufügen", self._add_word)
        self.dict_box = QVBoxLayout()
        self.dict_box.setSpacing(10)
        lay.addLayout(self.dict_box)
        lay.addStretch()
        return w

    def _add_word(self):
        word = self.dict_word.text().strip()
        if not word:
            return
        storage.add_dictionary(word, self.dict_heard.text().strip())
        self.dict_word.clear()
        self.dict_heard.clear()
        self.dict_word.setFocus()
        self._refresh_dictionary()

    def _add_word_from(self, body_label):
        sel = body_label.selectedText().strip()
        self.show_page("dictionary")
        self.dict_word.setText(sel)
        self.dict_word.setFocus()

    def _refresh_dictionary(self):
        rows = [(r["word"], f"wird ersetzt, wenn erkannt als „{r['replacement']}“" if r["replacement"] else
                 "hilft der Erkennung", lambda _=False, i=r["id"]: (storage.delete_dictionary(i),
                                                                   self._refresh_dictionary()))
                for r in storage.dictionary()]
        self._simple_rows(self.dict_box, rows, "Noch leer. Trag oben Namen oder Fachwörter ein, "
                                               "die Murmel falsch schreibt.")

    # ---------------------------------------------------------------- Snippets
    def _snippets(self):
        w, lay = self._list_page("Snippets", "Sag nur das Kürzel – Murmel fügt den ganzen Text ein. "
                                 "Greift nur, wenn das Kürzel die komplette Aufnahme ist.")
        self.snip_trigger = QLineEdit()
        self.snip_trigger.setPlaceholderText("Kürzel, z. B. meine Signatur")
        self.snip_trigger.setProperty("stretch", 1)
        self.snip_text = QPlainTextEdit()
        self.snip_text.setPlaceholderText("Text, der eingefügt wird …")
        self.snip_text.setFixedHeight(64)
        self.snip_text.setProperty("stretch", 2)
        self._form_card(lay, [self.snip_trigger, self.snip_text], "Hinzufügen", self._add_snippet)
        self.snip_box = QVBoxLayout()
        self.snip_box.setSpacing(10)
        lay.addLayout(self.snip_box)
        lay.addStretch()
        return w

    def _add_snippet(self):
        trig, text = self.snip_trigger.text().strip(), self.snip_text.toPlainText().strip()
        if not trig or not text:
            return
        storage.add_snippet(trig, text)
        self.snip_trigger.clear()
        self.snip_text.clear()
        self._refresh_snippets()

    def _refresh_snippets(self):
        rows = [(f"„{r['trigger']}“", r["text"][:160] + ("…" if len(r["text"]) > 160 else ""),
                 lambda _=False, i=r["id"]: (storage.delete_snippet(i), self._refresh_snippets()))
                for r in storage.snippets()]
        self._simple_rows(self.snip_box, rows, "Noch keine Snippets. Beispiel: Kürzel „meine Adresse“ → "
                                               "deine komplette Anschrift.")

    # ------------------------------------------------------------------- Stile
    def _styles(self):
        import styles
        w, lay = self._list_page("Stile", "Murmel passt den Text an die App an, in die du diktierst.")
        legend = card()
        ll = QVBoxLayout(legend)
        ll.setContentsMargins(22, 6, 22, 6)
        for i, (k, desc) in enumerate((("Formell", "Mail & Dokumente – sauberes Satzende."),
                                      ("Locker", "Chats – kein Punkt am Ende kurzer Nachrichten."),
                                      ("Code", "Editor & Terminal – keine Großschreibung am Anfang."),
                                      ("Standard", "Alles andere – so wie gesprochen."))):
            r = QFrame()
            r.setObjectName("row" if i < 3 else "")
            rl = QHBoxLayout(r)
            rl.setContentsMargins(0, 11, 0, 11)
            name = label(k)
            name.setFixedWidth(110)
            name.setStyleSheet("font-weight: 600;")
            rl.addWidget(name)
            rl.addWidget(label(desc, "muted"), 1)
            ll.addWidget(r)
        lay.addWidget(legend)
        lay.addSpacing(26)
        lay.addWidget(label("DEINE APPS", "section"))
        lay.addSpacing(10)
        self.style_card = card()
        self.style_box = QVBoxLayout(self.style_card)
        self.style_box.setContentsMargins(22, 4, 22, 4)
        self.style_box.setSpacing(0)
        lay.addWidget(self.style_card)
        lay.addSpacing(14)
        add = QHBoxLayout()
        self.style_new = QLineEdit()
        self.style_new.setPlaceholderText("Weitere App, z. B. notion.exe")
        self.style_new.setFixedWidth(280)
        self.style_new.returnPressed.connect(self._add_style_app)
        add.addWidget(self.style_new)
        b = QPushButton("Hinzufügen")
        b.setObjectName("ghost")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self._add_style_app)
        add.addWidget(b)
        add.addStretch()
        lay.addLayout(add)
        lay.addStretch()
        self._styles_mod = styles
        return w

    def _add_style_app(self):
        name = self.style_new.text().strip().lower().removesuffix(".exe")
        if not name:
            return
        ov = dict(self.cfg.get("app_styles", {}))
        ov.setdefault(name, "standard")
        self.setting_changed.emit("app_styles", ov)
        self.style_new.clear()
        self._refresh_styles()

    def _refresh_styles(self):
        st = self._styles_mod
        while self.style_box.count():
            it = self.style_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        ov = self.cfg.get("app_styles", {})
        apps = []
        for a in storage.recent_apps(12) + list(ov):
            k = st.app_key(a)
            if k and k not in apps:
                apps.append(k)
        for k in ("outlook", "winword", "discord", "whatsapp", "code"):
            if k not in apps:
                apps.append(k)
        for i, k in enumerate(apps):
            r = QFrame()
            r.setObjectName("row" if i < len(apps) - 1 else "")
            rl = QHBoxLayout(r)
            rl.setContentsMargins(0, 10, 0, 10)
            rl.addWidget(label(pretty_app(k)), 1)
            cur = st.style_for(k, "", ov)
            seg = Segmented([(s, n) for s, n in st.STYLES.items()], cur)
            seg.changed.connect(lambda v, key=k: self._set_style(key, v))
            rl.addWidget(seg)
            self.style_box.addWidget(r)

    def _set_style(self, key, value):
        ov = dict(self.cfg.get("app_styles", {}))
        ov[key] = value
        self.setting_changed.emit("app_styles", ov)

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
        self.mic_combo.addItem(osapi.SYSTEM_DEFAULT_MIC, None)
        for name in self.ctl.list_mics():
            self.mic_combo.addItem(name, name)
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
        cur_name = next((k for k, v in HOTKEYS.items() if v == c.get("hotkey")), next(iter(HOTKEYS)))
        hk.setCurrentText(cur_name)
        hk.currentTextChanged.connect(lambda t: self.setting_changed.emit("hotkey", HOTKEYS[t]))
        self._setting_row(g, "Tastenkürzel", "Halten zum Sprechen, doppelt tippen für Freihand.", hk)
        lang = Segmented([("auto", "Auto (DE/EN)"), ("de", "Deutsch"), ("en", "Englisch")], c.get("language", "auto"))
        lang.changed.connect(lambda v: self.setting_changed.emit("language", v))
        self._setting_row(g, "Sprache", None, lang)
        import llm
        has_ollama = llm.installed()
        edit = Segmented([("off", "Aus"), ("normal", "Normal"), ("strong", "Stark")], c.get("cleanup", "normal"),
                         disabled=() if has_ollama else ("strong",),
                         tips={"strong": "Regeln + lokale KI (Ollama) glättet die Sätze" if has_ollama
                               else "Braucht Ollama (ollama.com) – ist nicht installiert"})
        edit.changed.connect(lambda v: self.setting_changed.emit("cleanup", v))
        self._setting_row(g, "Auto-Edit", "Füllwörter, Selbstkorrekturen, „neue Zeile“, Listen. "
                                          "Stark = zusätzlich lokale KI (langsamer).", edit)
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
        auto = Toggle(bool(c.get("autostart", False)))
        auto.toggled.connect(lambda v: self.setting_changed.emit("autostart", v))
        self._setting_row(g, osapi.AUTOSTART_LABEL, "Murmel startet beim Anmelden im Tray.", auto)
        oled = Toggle(int(c.get("screen_off_s", 60)) > 0)
        oled.toggled.connect(lambda v: self.setting_changed.emit("screen_off_s", 60 if v else 0))
        self._setting_row(g, "Bildschirm automatisch aus", "Bei Aufnahme nach 1 Min. – schont OLED.", oled)
        recdir = QPushButton("Ändern")
        recdir.setObjectName("ghost")
        recdir.setCursor(Qt.PointingHandCursor)
        recdir.clicked.connect(self._choose_rec_dir)
        self._setting_row(g, "Speicherort für Aufnahmen", self.ctl._rec_dir().as_posix()
                          if hasattr(self.ctl, "_rec_dir") else "", recdir)
        th = Segmented([("light", "Hell"), ("dark", "Dunkel"), ("system", "System")], c.get("theme", "system"))
        th.changed.connect(lambda v: self.setting_changed.emit("theme", v))
        self._setting_row(g, "Design", None, th)
        intro = QPushButton("Einführung zeigen")
        intro.setObjectName("ghost")
        intro.setCursor(Qt.PointingHandCursor)
        intro.clicked.connect(lambda: self.setting_changed.emit("show_onboarding", time.time()))
        self._setting_row(g, "Einführung", "Die 5 Schritte vom ersten Start noch mal.", intro, last=True)

        g = self._group(lay, "Lokale KI (Ollama)")
        self.ollama_chip = label("prüfe …", "chip")
        self._setting_row(g, "Status", "Nur auf diesem Rechner (localhost). Ohne Ollama geht alles außer "
                                       "„Stark“ und dem Command Mode.", self.ollama_chip)
        self.ollama_combo = QComboBox()
        self.ollama_combo.currentIndexChanged.connect(self._ollama_model_changed)
        self._setting_row(g, "Modell", None, self.ollama_combo)
        self._setting_row(g, "Command Mode", f"Text markieren, {osapi.combo_text(c.get('command_hotkey', ['ctrl', 'win', 'alt']))} halten, Anweisung sprechen "
                                             "(„mach das formeller“, „übersetz ins Englische“).",
                          label(osapi.combo_text(c.get("command_hotkey", ["ctrl", "win", "alt"])), "chip"), last=True)
        lay.addStretch()
        return w

    def _choose_rec_dir(self):
        from PySide6.QtWidgets import QFileDialog
        cur = self.ctl._rec_dir() if hasattr(self.ctl, "_rec_dir") else None
        d = QFileDialog.getExistingDirectory(self, "Speicherort für Aufnahmen", str(cur or ""))
        if d:
            self.setting_changed.emit("rec_dir", d)
            h = getattr(self, "_hints", {}).get("Speicherort für Aufnahmen")
            if h:
                h.setText(d)

    def _refresh_settings(self):
        """Ollama-Status im Hintergrund prüfen (HTTP darf das UI nicht blockieren)."""
        import threading
        import llm

        def work():
            st = llm.status()
            self._ollama_status = st
            QTimer.singleShot(0, self, self._show_ollama)    # zurück in den UI-Thread
        threading.Thread(target=work, daemon=True).start()

    def _show_ollama(self):
        st = getattr(self, "_ollama_status", {})
        if not st.get("installed"):
            self.ollama_chip.setText("nicht installiert")
        elif not st.get("running"):
            self.ollama_chip.setText("installiert · startet bei Bedarf")
        else:
            self.ollama_chip.setText(f"läuft · {len(st['models'])} Modelle")
        self.ollama_combo.blockSignals(True)
        self.ollama_combo.clear()
        self.ollama_combo.addItem("Automatisch", None)
        for m in st.get("models", []):
            self.ollama_combo.addItem(m, m)
        cur = self.ollama_combo.findData(self.cfg.get("ollama_model"))
        self.ollama_combo.setCurrentIndex(max(0, cur))
        self.ollama_combo.setEnabled(bool(st.get("models")))
        self.ollama_combo.blockSignals(False)

    def _ollama_model_changed(self, _):
        self.setting_changed.emit("ollama_model", self.ollama_combo.currentData())

    def set_engine(self, text, gpu: bool):
        self.engine_label.setText(text)
        h = getattr(self, "_hints", {}).get("Erkennung")
        if h:
            h.setText("Läuft auf der Grafikkarte – schnell." if gpu else
                      "Läuft auf dem Prozessor. Schneller geht es mit einer aktiven NVIDIA-GPU "
                      "(ASUS: GPU-Modus „Standard“ in Armoury Crate bzw. G-Helper).")

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
