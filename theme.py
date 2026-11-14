"""Farb-Tokens, Schriften, Icons und das zentrale QSS – alles Design an EINER Stelle.

Stimmung: ruhig, warm, editorial. Creme statt Weiß, tiefes Grün als Akzent, Flieder für
Primär-Buttons, feine 1-px-Linien statt Schatten, große Serif-Überschriften.
"""
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

LIGHT = {
    "bg": "#F7F5EE", "sidebar": "#F0EDE3", "card": "#FFFFFF", "card_alt": "#FBFAF5",
    "text": "#1B1B18", "muted": "#6F6C63", "faint": "#A19D92", "line": "#E5E1D5",
    "hover": "#EBE7DB", "accent": "#1E5A47", "accent_soft": "#DDEAE3",
    "primary": "#E8DEF8", "primary_hover": "#DDD0F3", "primary_text": "#1B1B18",
    "primary_border": "#1B1B18", "danger": "#B42318", "pill": "#FFFFFF", "pill_fg": "#1B1B18",
}
DARK = {
    "bg": "#161616", "sidebar": "#121212", "card": "#1F1F1F", "card_alt": "#1A1A1A",
    "text": "#EDEDED", "muted": "#9C9A93", "faint": "#6B6A65", "line": "#2A2A2A",
    "hover": "#262626", "accent": "#7CC4A6", "accent_soft": "#1D2B25",
    "primary": "#DCD0F6", "primary_hover": "#CDBEF0", "primary_text": "#151515",
    "primary_border": "#DCD0F6", "danger": "#F97066", "pill": "#121214", "pill_fg": "#F2F2F2",
}

SERIF = "Instrument Serif"
SANS = "Inter"


def load_fonts():
    global SERIF, SANS
    fams = {}
    for f in ("InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf", "Inter.ttf"):
        fid = QFontDatabase.addApplicationFont(os.path.join(ASSETS, "fonts", f))
        if fid >= 0:
            for fam in QFontDatabase.applicationFontFamilies(fid):
                fams[fam] = True
    SERIF = "Instrument Serif" if "Instrument Serif" in fams else "Georgia"
    SANS = "Inter" if "Inter" in fams else "Segoe UI"


def is_dark(mode: str) -> bool:
    if mode == "dark":
        return True
    if mode == "light":
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def tokens(mode: str) -> dict:
    return DARK if is_dark(mode) else LIGHT


_svg_cache = {}


def icon_pixmap(name: str, color: str, size: int = 18, dpr: float = 1.5) -> QPixmap:
    key = (name, color, size, dpr)
    if key in _svg_cache:
        return _svg_cache[key]
    with open(os.path.join(ASSETS, "icons", f"{name}.svg"), encoding="utf-8") as fh:
        svg = fh.read().replace("currentColor", color).replace('stroke-width="2"', 'stroke-width="1.75"')
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    _svg_cache[key] = pm
    return pm


def icon(name, color, size=18):
    return QIcon(icon_pixmap(name, color, size))


def _chevron(color: str) -> str:
    """Pfeil für Dropdowns als kleine SVG-Datei in der Theme-Farbe (QSS braucht einen Dateipfad)."""
    import config
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    p = config.APP_DIR / f"chevron-{color.lstrip('#')}.svg"
    if not p.exists():
        p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
                     f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
                     f'stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>', encoding="utf-8")
    return p.as_posix()


def qss(t: dict) -> str:
    chev = _chevron(t["muted"])
    return f"""
* {{ font-family: "{SANS}"; color: {t['text']}; }}
QWidget#root, QWidget#page, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {t['bg']}; border: none;
}}
QFrame#sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['line']}; }}
QLabel#brand {{ font-family: "{SERIF}"; font-size: 26px; }}
QLabel#h1 {{ font-family: "{SERIF}"; font-size: 46px; }}
QLabel#h2 {{ font-family: "{SERIF}"; font-size: 30px; }}
QLabel#sub {{ color: {t['muted']}; font-size: 14px; }}
QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
QLabel#faint {{ color: {t['faint']}; font-size: 11px; letter-spacing: 0.6px; }}
QLabel#statnum {{ font-family: "{SERIF}"; font-size: 40px; }}
QLabel#section {{ color: {t['faint']}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#chip {{ background: {t['accent_soft']}; color: {t['accent']}; border-radius: 11px;
               padding: 3px 10px; font-size: 11px; font-weight: 600; }}

QPushButton#nav {{ text-align: left; padding: 9px 12px; border-radius: 10px; border: none;
                   background: transparent; font-size: 14px; color: {t['muted']}; }}
QPushButton#nav:hover {{ background: {t['hover']}; color: {t['text']}; }}
QPushButton#nav:checked {{ background: {t['card']}; color: {t['text']};
                           border: 1px solid {t['line']}; font-weight: 600; }}

QFrame#card {{ background: {t['card']}; border: 1px solid {t['line']}; border-radius: 16px; }}
QFrame#row {{ background: transparent; border: none; border-bottom: 1px solid {t['line']}; }}
QFrame#histrow {{ background: {t['card']}; border: 1px solid {t['line']}; border-radius: 14px; }}
QFrame#histrow:hover {{ border: 1px solid {t['faint']}; }}
QFrame#divider {{ background: {t['line']}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton#primary {{ background: {t['primary']}; color: {t['primary_text']};
    border: 1px solid {t['primary_border']}; border-radius: 12px; padding: 9px 18px;
    font-weight: 600; font-size: 13px; }}
QPushButton#primary:hover {{ background: {t['primary_hover']}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {t['line']}; border-radius: 12px;
    padding: 8px 14px; font-size: 13px; color: {t['text']}; }}
QPushButton#ghost:hover {{ background: {t['hover']}; }}
QPushButton#danger {{ background: transparent; border: 1px solid {t['line']}; border-radius: 12px;
    padding: 8px 14px; font-size: 13px; color: {t['danger']}; }}
QPushButton#danger:hover {{ background: {t['hover']}; }}
QToolButton#iconbtn {{ background: transparent; border: none; border-radius: 9px; padding: 6px; }}
QToolButton#iconbtn:hover {{ background: {t['hover']}; }}

QPushButton#seg {{ background: transparent; border: none; border-radius: 9px; padding: 7px 14px;
    font-size: 13px; color: {t['muted']}; }}
QPushButton#seg:hover {{ color: {t['text']}; }}
QPushButton#seg:checked {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['line']};
    font-weight: 600; }}
QPushButton#seg:disabled {{ color: {t['faint']}; }}
QFrame#segbox {{ background: {t['hover']}; border-radius: 12px; border: none; }}

QLineEdit, QPlainTextEdit {{ background: {t['card']}; border: 1px solid {t['line']};
    border-radius: 12px; padding: 10px 12px; font-size: 14px;
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {t['accent']}; }}
QComboBox {{ background: {t['card']}; border: 1px solid {t['line']}; border-radius: 10px;
    padding: 7px 12px; font-size: 13px; min-width: 220px; }}
QComboBox:hover {{ border: 1px solid {t['faint']}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox::down-arrow {{ image: url("{chev}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {t['card']}; border: 1px solid {t['line']};
    selection-background-color: {t['hover']}; selection-color: {t['text']}; outline: 0; padding: 4px; }}
QProgressBar#level {{ background: {t['hover']}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar#level::chunk {{ background: {t['accent']}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {t['line']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; height: 0; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['line']};
    padding: 6px 8px; border-radius: 8px; }}
QMenu {{ background: {t['card']}; border: 1px solid {t['line']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['hover']}; }}
QMenu::separator {{ height: 1px; background: {t['line']}; margin: 5px 8px; }}
"""
