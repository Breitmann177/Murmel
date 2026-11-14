"""Regelbasierte Textbereinigung (Phase 1: Grundregeln; Phase 2 baut das mit Tests aus)."""
import re

FILLERS = {
    "de": r"ähm+|äh+|öhm+|öh+|hmm+|hm|mhm",
    "en": r"um+|uh+|uhm+|erm+|er",     # "er" nur im Englischen – im Deutschen ein Pronomen!
}


def clean(text: str, lang: str = "de", level: str = "normal") -> str:
    if level == "off" or not text:
        return text.strip()
    t = text
    for lg in ("de", "en") if lang == "en" else ("de",):
        t = re.sub(rf"(?i)(^|[\s,.;:!?])(?:{FILLERS[lg]})(?=[\s,.;:!?]|$)[,.]?", r"\1", t)
    # Wortwiederholungen: "ich ich wollte" -> "ich wollte"
    t = re.sub(r"(?i)\b(\w+)(\s+\1\b)+", r"\1", t)
    # Leerzeichen vor Satzzeichen, doppelte Leerzeichen, verwaiste Kommas am Anfang
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"^[,.;:]\s*", "", t)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t
