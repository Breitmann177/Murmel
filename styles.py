"""Stil pro App: dieselbe Diktat-Engine, aber der Text passt sich der Ziel-App an.

- formal  : Mail/Dokumente  -> sauberes Satzende
- casual  : Chats           -> kein Punkt am Ende kurzer Nachrichten (wirkt sonst streng)
- code    : Editor/Terminal -> keine automatische Großschreibung am Anfang
- standard: alles andere    -> unverändert
Browser sind tückisch (Gmail und WhatsApp Web sind beides "chrome.exe"), daher zusätzlich
Regeln nach Fenstertitel.
"""
import re

STYLES = {"standard": "Standard", "formal": "Formell", "casual": "Locker", "code": "Code"}

DEFAULT_APPS = {
    "outlook": "formal", "olk": "formal", "winword": "formal", "thunderbird": "formal",
    "discord": "casual", "whatsapp": "casual", "telegram": "casual", "slack": "casual",
    "signal": "casual", "ms-teams": "casual",
    "code": "code", "cursor": "code", "windowsterminal": "code", "powershell": "code",
    "pwsh": "code", "cmd": "code", "pycharm64": "code", "idea64": "code", "devenv": "code",
}
BROWSERS = {"chrome", "msedge", "firefox", "opera", "brave", "vivaldi", "arc"}
TITLE_RULES = (("gmail", "formal"), ("outlook", "formal"), ("whatsapp", "casual"),
               ("discord", "casual"), ("slack", "casual"), ("telegram", "casual"),
               ("github", "code"), ("chatgpt", "standard"), ("claude", "standard"))


def app_key(exe: str) -> str:
    return exe.lower().removesuffix(".exe")


def style_for(exe: str, title: str, overrides: dict) -> str:
    key = app_key(exe)
    if key in overrides:
        return overrides[key]
    if key in BROWSERS:
        t = (title or "").lower()
        for kw, st in TITLE_RULES:
            if kw in t:
                return st
    return DEFAULT_APPS.get(key, "standard")


def apply(text: str, style: str, keep_words=()) -> str:
    if not text:
        return text
    if style == "casual":
        body = text.rstrip()
        inner = re.findall(r"[.!?](?=\s)", body[:-1])
        if body.endswith(".") and not body.endswith("..") and not inner and len(body.split()) <= 20:
            return body[:-1]
    elif style == "code":
        first = text.split()[0] if text.split() else ""
        clean_first = re.sub(r"\W", "", first)
        keep = {w.lower() for w in keep_words}
        if clean_first and not clean_first.isupper() and clean_first.lower() not in keep and clean_first != "I":
            return text[0].lower() + text[1:]
    elif style == "formal":
        if text.rstrip()[-1:].isalnum():
            return text.rstrip() + "."
    return text
