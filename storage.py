"""SQLite-Speicher für Verlauf (und später Wörterbuch/Snippets).

Warum SQLite? Eine Datei, keine Installation, eingebaut in Python, transaktionssicher und mit
Volltext-tauglichem LIKE schnell genug für zehntausende Diktate. Jeder Thread bekommt seine
eigene Verbindung (sqlite3-Verbindungen dürfen nicht zwischen Threads geteilt werden).
"""
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import config

DB_PATH = config.APP_DIR / "murmel.db"
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    app      TEXT,
    raw      TEXT,
    clean    TEXT,
    lang     TEXT,
    duration REAL,          -- Sekunden gesprochen
    latency  REAL,          -- Sekunden vom Loslassen bis eingefügt
    words    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts);
CREATE TABLE IF NOT EXISTS dictionary (
    id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT NOT NULL, replacement TEXT
);
CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trigger TEXT NOT NULL, text TEXT NOT NULL
);
"""


def db():
    con = getattr(_local, "con", None)
    if con is None:
        config.APP_DIR.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        _local.con = con
    return con


def add_history(app, raw, clean, lang, duration, latency):
    con = db()
    con.execute("INSERT INTO history(ts, app, raw, clean, lang, duration, latency, words) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (time.time(), app, raw, clean, lang, duration, latency, len(clean.split())))
    con.commit()


def history(search="", limit=200):
    q = "SELECT * FROM history"
    args = []
    if search:
        q += " WHERE clean LIKE ? OR raw LIKE ? OR app LIKE ?"
        args = [f"%{search}%"] * 3
    q += " ORDER BY ts DESC LIMIT ?"
    return [dict(r) for r in db().execute(q, args + [limit])]


def delete_history(entry_id=None):
    con = db()
    if entry_id is None:
        con.execute("DELETE FROM history")
    else:
        con.execute("DELETE FROM history WHERE id=?", (entry_id,))
    con.commit()


def stats():
    """Wörter heute/Woche/gesamt, Sprechtempo, gesparte Zeit (vs. 40 WPM tippen), Streak."""
    con = db()
    now = datetime.now()
    start_today = datetime(now.year, now.month, now.day).timestamp()
    start_week = (datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())).timestamp()

    def words_since(ts):
        return con.execute("SELECT COALESCE(SUM(words),0) FROM history WHERE ts>=?", (ts,)).fetchone()[0]

    total_words, total_secs = con.execute(
        "SELECT COALESCE(SUM(words),0), COALESCE(SUM(duration),0) FROM history").fetchone()
    wpm = round(total_words / (total_secs / 60)) if total_secs > 5 else 0
    saved_min = max(0.0, total_words / 40 - total_secs / 60)

    days = {datetime.fromtimestamp(r[0]).date()
            for r in con.execute("SELECT ts FROM history WHERE ts>=?", (time.time() - 400 * 86400,))}
    streak, d = 0, now.date()
    if d not in days:
        d -= timedelta(days=1)                       # heute noch nichts diktiert: Streak bleibt
    while d in days:
        streak += 1
        d -= timedelta(days=1)
    return {"today": words_since(start_today), "week": words_since(start_week),
            "total": total_words, "wpm": wpm, "saved_min": saved_min, "streak": streak}
