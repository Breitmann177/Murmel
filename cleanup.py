"""Regelbasierte Textbereinigung – lokal, schnell (< 1 ms), deterministisch.

Grundsatz: KONSERVATIV. Lieber ein Füllwort stehen lassen als einen echten Satzteil löschen.
Whisper liefert schon Satzzeichen und Großschreibung; wir räumen nur auf.

Reihenfolge ist wichtig:
  1. Füllwörter        ("ähm", "also" am Satzanfang …)
  2. Selbstkorrekturen ("um drei, nein, um vier" -> "um vier")
  3. Wiederholungen    ("ich ich" -> "ich")
  4. Sprechbefehle     ("neue Zeile", "Fragezeichen" …)
  5. Listen            ("erstens … zweitens …")
  6. Wörterbuch        (eigene Ersetzungen)
  7. Feinschliff       (Leerzeichen, Großschreibung, Fragezeichen bei Fragen)
"""
import re

# ---------------------------------------------------------------- Füllwörter
ALWAYS_FILLERS = {
    "de": ["ähm+", "äh+", "öhm+", "öh+", "hmm+", "hm", "mhm", "ehm+"],
    "en": ["um+", "uh+", "uhm+", "erm+", "er", "hmm+"],     # "er" nur EN – im Deutschen ein Pronomen
}
# nur am Satzanfang oder zwischen Kommas ("…, sozusagen, …")
SOFT_FILLERS = {
    "de": ["also", "halt", "quasi", "sozusagen", "ja also", "na ja", "naja"],
    "en": ["so", "like", "you know", "well", "basically"],
}
# Artikel/Pronomen dürfen doppelt vorkommen ("die die Regeln brechen") -> nicht zusammenfassen
LEGIT_DOUBLES = {"der", "die", "das", "den", "dem", "des", "sie", "er", "es", "ein", "eine",
                 "that", "had", "is"}

CORRECTION_MARKERS = [
    r"nein", r"ne", r"äh,? nein", r"ich meine", r"ich mein", r"sorry", r"quatsch",
    r"besser gesagt", r"moment", r"no", r"i mean", r"actually", r"wait,? no", r"sorry",
    r"scratch that",
]

DE_QUESTION_START = ("wer", "was", "wann", "wo", "wie", "warum", "wieso", "weshalb", "welche",
                     "welcher", "welches", "wem", "wen", "wessen", "woher", "wohin", "kannst",
                     "könnt", "können", "könntest", "hast", "habt", "haben", "bist", "seid",
                     "ist", "sind", "gibt", "würdest", "würden", "willst", "wollen", "sollen",
                     "sollte", "sollten", "darf", "dürfen", "machst", "weißt", "kennst", "magst")
EN_QUESTION_START = ("what", "who", "when", "where", "why", "how", "which", "do", "does", "did",
                     "can", "could", "would", "will", "should", "is", "are", "was", "were",
                     "have", "has")
INDIRECT_QUESTION = re.compile(r"(?i)\b(wollte|möchte|will|würde gern|wollt)\s+(dich|euch|sie|)\s*"
                               r"(fragen|wissen),?\s+(ob|wann|wie|was|wo|warum|wer)\b"
                               r"|\b(i (?:wanted|want) to (?:ask|know))\s+(?:if|whether|when|how)\b")

ORDINALS = {
    "de": ["erstens", "zweitens", "drittens", "viertens", "fünftens", "sechstens"],
    "en": ["first", "second", "third", "fourth", "fifth", "sixth"],
}
PUNKT_N = ["eins", "zwei", "drei", "vier", "fünf", "sechs"]

_W = r"[^\W\d_]+"        # ein Wort (Buchstaben inkl. Umlaute)


def _sentences(text):
    """Text in (Satz, Trenner)-Paare zerlegen, ohne Zeichen zu verlieren."""
    parts = re.split(r"([.!?]+\s*|\n+)", text)
    return [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]


def remove_fillers(text, lang):
    t = text
    langs = ("de", "en") if lang == "en" else ("de",)
    for lg in langs:
        pat = "|".join(ALWAYS_FILLERS[lg])
        t = re.sub(rf"(?i)(^|[\s,.;:!?(])(?:{pat})(?=[\s,.;:!?)]|$)[,.]?", r"\1", t)
    t = re.sub(r"(^|[.!?]\s*|\n)\s+", r"\1", t.lstrip())    # Lücken am Satzanfang schließen
    soft = SOFT_FILLERS["en" if lang == "en" else "de"]
    pat = "|".join(re.escape(s) for s in sorted(soft, key=len, reverse=True))
    # am Satzanfang: "Also ich wollte …" -> "Ich wollte …"  (nur wenn danach noch was kommt)
    t = re.sub(rf"(?i)(^|[.!?]\s+|\n)(?:{pat})\b[,]?\s+(?=\w)", r"\1", t)
    # eingeschoben zwischen Kommas: "…, sozusagen, …" -> "…, …"
    t = re.sub(rf"(?i),\s*(?:{pat}),", ",", t)
    # doppelt: "also also" -> ""
    t = re.sub(rf"(?i)\b({pat})\s+\1\b[,]?\s*", "", t)
    return t


def apply_corrections(text):
    """"X, nein, Y" -> Y ersetzt das passende Ende von X. Sehr vorsichtig:
    - Steht Y's erstes Wort in den letzten 6 Wörtern vor der Korrektur, wird ab dort ersetzt
      ("um drei, nein, um vier" -> "um vier").
    - Sonst nur, wenn Y kurz ist (1–2 Wörter bis zum nächsten Satzzeichen): letztes Wort tauschen
      ("Montag, nein, Dienstag" -> "Dienstag").
    - Sonst bleibt alles stehen (z. B. "Er sagte, nein, das geht nicht")."""
    markers = "|".join(sorted(CORRECTION_MARKERS, key=len, reverse=True))
    rx = re.compile(rf"(?i),\s*(?:{markers})\s*,\s*")
    out = []
    for sent, sep in _sentences(text):
        for _ in range(3):                         # mehrere Korrekturen pro Satz
            m = rx.search(sent)
            if not m:
                break
            before, after = sent[:m.start()], sent[m.end():]
            bw = before.split()
            aw = after.split()
            if not bw or not aw:
                break
            first = re.sub(r"\W", "", aw[0]).lower()
            idx = None
            for k in range(len(bw) - 1, max(-1, len(bw) - 7), -1):
                if re.sub(r"\W", "", bw[k]).lower() == first:
                    idx = k
                    break
            if idx is not None:
                sent = " ".join(bw[:idx] + aw)
                continue
            short = re.match(r"^\s*(\S+(?:\s+\S+)?)\s*(?:[,;:]|$)", after)
            if short and len(short.group(1).split()) <= 2 and len(bw) >= 2:
                sent = " ".join(bw[:-1] + aw)
                continue
            break
        out.append(sent + sep)
    return "".join(out)


def remove_repeats(text):
    def rep(m):
        w = m.group(1)
        return m.group(0) if w.lower() in LEGIT_DOUBLES and m.group(0).lower().count(w.lower()) < 3 else w
    return re.sub(rf"(?i)\b({_W})(?:\s+\1\b)+", rep, text)


def spoken_commands(text, lang):
    t = text
    cmds = [
        (r"neuer absatz|new paragraph", "\n\n"),
        (r"neue zeile|nächste zeile|new line|next line", "\n"),
    ]
    for pat, rep in cmds:
        # vorangehendes Komma schlucken, aber einen Satzpunkt davor stehen lassen
        t = re.sub(rf"(?i)[,;]?\s*\b(?:{pat})\b[,.;:]?\s*", rep, t)
    t = re.sub(r"(?i)\s*\bklammer auf\b[,.]?\s*|\s*\bopen (?:paren|parenthesis)\b[,.]?\s*", " (", t)
    t = re.sub(r"(?i)[,.]?\s*\bklammer zu\b|[,.]?\s*\bclose (?:paren|parenthesis)\b", ")", t)
    # Fragezeichen/Ausrufezeichen/Doppelpunkt werden praktisch nie wörtlich gemeint
    for word, ch in ((r"fragezeichen|question mark", "?"), (r"ausrufezeichen|exclamation mark", "!"),
                     (r"doppelpunkt|colon", ":")):
        t = re.sub(rf"(?i)[,.]?\s*\b(?:{word})\b[.,!?]?", ch, t)
    # "Punkt"/"Komma" nur am Ende oder direkt vor einem Zeilenumbruch (sonst "Treffpunkt", "Punkt eins")
    for word, ch in ((r"punkt|period|full stop", "."), (r"komma|comma", ",")):
        t = re.sub(rf"(?i)[,.]?\s*\b(?:{word})\b[.,!?]?(?=\s*(?:\n|$))", ch, t)
    return t


def make_lists(text, lang):
    lg = "en" if lang == "en" else "de"
    ords = ORDINALS[lg]
    words = "|".join(ords + [w + "ly" for w in ords] if lg == "en" else ords)
    punkt = r"punkt (?:" + "|".join(PUNKT_N) + r")"
    rx = re.compile(rf"(?i)[,.;:]?\s*\b(?:{words}|{punkt})\b[,:]?\s*")
    hits = list(rx.finditer(text))
    if len(hits) < 2:
        return text
    intro = text[:hits[0].start()].strip().rstrip(",")
    items = []
    for i, h in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        item = text[h.end():end].strip()
        item = re.sub(r"(?i)[,;]?\s*\b(und|and)\s*$", "", item).strip().rstrip(",;")
        item = item.rstrip(".")
        if item:
            items.append(item[0].upper() + item[1:])
    if len(items) < 2:
        return text
    body = "\n".join(f"{i + 1}. {it}" for i, it in enumerate(items))
    if intro:
        if not intro.endswith((":", ".", "!", "?")):
            intro += ":"
        return intro + "\n" + body
    return body


def apply_dictionary(text, replacements):
    for src, dst in (replacements or {}).items():
        if src.strip():
            text = re.sub(rf"(?i)(?<!\w){re.escape(src)}(?!\w)", dst, text)
    return text


def _is_question(sentence, lang):
    s = sentence.strip()
    if not s:
        return False
    first = re.sub(r"\W", "", s.split()[0]).lower()
    if INDIRECT_QUESTION.search(s):
        return True
    return first in (EN_QUESTION_START if lang == "en" else DE_QUESTION_START)


def polish(text, lang):
    t = text
    t = re.sub(r"[ \t]+([,.;:!?)])", r"\1", t)          # Leerzeichen vor Satzzeichen
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)                 # ",." -> "."
    t = re.sub(r"([,;:])(?=[^\s\d\n])", r"\1 ", t)       # Leerzeichen nach Komma
    t = re.sub(r"([.!?])\1+", r"\1", t)                  # ".." -> "."
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    t = re.sub(r"^[\s,.;:]+", "", t).rstrip(" ,;")
    # Fragen erkennen: Satz endet mit "." aber beginnt wie eine Frage
    out = []
    for sent, sep in _sentences(t):
        if sep.startswith(".") and _is_question(sent, lang):
            sep = "?" + sep[1:]
        out.append(sent + sep)
    t = "".join(out)
    # Großschreibung am Anfang und nach Satzende/Zeilenumbruch
    t = re.sub(r"(^|[.!?]\s+|\n)([a-zäöü])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t.strip()


def clean(text: str, lang: str = "de", level: str = "normal", replacements=None) -> str:
    if not text:
        return ""
    if level == "off":
        return apply_dictionary(text.strip(), replacements)
    t = remove_fillers(text, lang)
    t = apply_corrections(t)
    t = remove_repeats(t)
    t = spoken_commands(t, lang)
    t = make_lists(t, lang)
    t = apply_dictionary(t, replacements)
    return polish(t, lang)
