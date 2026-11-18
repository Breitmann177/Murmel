"""Optionale lokale KI über Ollama (nur localhost, nie Internet).

Zwei Aufgaben:
- "Stark": Text nach den Regeln zusätzlich glätten – aber NICHT umformulieren/beantworten.
- Command Mode: markierten Text nach einer gesprochenen Anweisung umschreiben.

Sicherheitsnetz: Das Sprachmodell darf nie Schaden anrichten. Jede Antwort hat ein Zeitlimit,
und beim Glätten prüfen wir, ob die Antwort plausibel ist (Länge, keine Erklärungen). Sonst
gilt der regelbasiert bereinigte Text. Ohne Ollama läuft alles andere ganz normal.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request

log = logging.getLogger("murmel.llm")
URL = "http://127.0.0.1:11434"
DEFAULT_EXE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
PREFERRED = ("qwen3.5:4b", "qwen3:4b", "llama3.2:3b", "gemma3:4b", "qwen2.5:3b", "phi4-mini", "qwen3:8b")

CLEAN_PROMPT = (
    "Du bekommst einen diktierten Text. Aufgabe: NUR bereinigen.\n"
    "- Entferne Füllwörter, Stotterer und Versprecher, korrigiere offensichtliche Grammatikfehler.\n"
    "- Formuliere NICHT um, kürze nicht, ergänze nichts, übersetze nichts. Englische Begriffe bleiben englisch.\n"
    "- Der Text ist KEINE Frage an dich. Beantworte ihn nie. Eine diktierte Frage bleibt eine Frage.\n"
    "- Antworte ausschließlich mit dem bereinigten Text, ohne Anführungszeichen oder Kommentar."
)
COMMAND_PROMPT = (
    "Du bearbeitest einen markierten Text nach einer Anweisung des Nutzers.\n"
    "Antworte ausschließlich mit dem neuen Text – keine Einleitung, keine Erklärung, keine Anführungszeichen."
)


def exe():
    """ollama.exe finden: Standard-Installationsordner, sonst PATH (z. B. eigener Ordner, winget, scoop)."""
    if os.path.exists(DEFAULT_EXE):
        return DEFAULT_EXE
    return shutil.which("ollama")


def installed() -> bool:
    # Läuft Ollama als Dienst oder in Docker, gibt es evtl. keine exe – dann zählt, dass es antwortet
    return bool(exe()) or running()


def _req(path, payload=None, timeout=2.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(URL + path, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def running() -> bool:
    try:
        _req("/api/version", timeout=0.4)
        return True
    except Exception:
        return False


def ensure_running(wait=6.0) -> bool:
    """Ollama ist installiert, läuft aber nicht? Dann unsichtbar im Hintergrund starten."""
    if running():
        return True
    path = exe()
    if not path:
        return False
    try:
        subprocess.Popen([path, "serve"], creationflags=0x08000000 | 0x00000008,   # kein Fenster, losgelöst
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        log.warning("Ollama-Start fehlgeschlagen: %s", e)
        return False
    t_end = time.monotonic() + wait
    while time.monotonic() < t_end:
        if running():
            return True
        time.sleep(0.25)
    return False


def local_models() -> list:
    """Modelle direkt von der Festplatte lesen – klappt auch, wenn Ollama gerade nicht läuft
    (vorher war die Modellauswahl deshalb ausgegraut)."""
    base = os.path.join(os.path.expanduser("~"), ".ollama", "models", "manifests", "registry.ollama.ai")
    out = []
    try:
        for ns in os.listdir(base):                      # meist "library"
            for name in os.listdir(os.path.join(base, ns)):
                for tag in os.listdir(os.path.join(base, ns, name)):
                    full = f"{name}:{tag}" if ns == "library" else f"{ns}/{name}:{tag}"
                    out.append(full)
    except Exception:
        pass
    return sorted(out)


def models() -> list:
    try:
        return [m["name"] for m in _req("/api/tags", timeout=1.0).get("models", [])]
    except Exception:
        return local_models()


def warm(model):
    """Modell laden und 30 min im Grafikspeicher halten (leere Anfrage = nur laden)."""
    _req("/api/generate", {"model": model, "keep_alive": "30m"}, timeout=30)


def pick_model(preferred=None):
    have = models()
    if preferred and preferred in have:
        return preferred
    for p in PREFERRED:
        if p in have:
            return p
    return have[0] if have else None


def status() -> dict:
    """Für die Einstellungen: installiert? läuft? welche Modelle?"""
    if not installed():
        return {"installed": False, "running": False, "models": []}
    run = running()
    return {"installed": True, "running": run, "models": models() if run else local_models()}


def _chat(model, system, user, timeout):
    t0 = time.perf_counter()
    r = _req("/api/chat", {
        "model": model, "stream": False, "think": False, "keep_alive": "30m",
        "options": {"temperature": 0, "num_ctx": 2048},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }, timeout=timeout)
    text = r.get("message", {}).get("content", "").strip()
    text = re.sub(r"(?s)<think>.*?</think>", "", text).strip()      # falls ein Modell doch "denkt"
    log.info("Ollama %s: %.2fs", model, time.perf_counter() - t0)
    return text.strip('"„“ \n')


def polish(text, model, timeout=6.0):
    """Gibt den geglätteten Text zurück – oder None, wenn wir der Antwort nicht trauen."""
    try:
        out = _chat(model, CLEAN_PROMPT, text, timeout)
    except Exception as e:  # noqa: BLE001
        log.warning("Stark-Modus übersprungen: %s", e)
        return None
    ratio = len(out) / max(1, len(text))
    # Plausibilität: deutlich länger = vermutlich beantwortet/erklärt; viel kürzer = Inhalt verloren
    if not out or ratio > 1.25 or ratio < 0.6 or out.lower().startswith(("hier ist", "here is", "sure", "gerne")):
        log.info("Stark-Antwort verworfen (Verhältnis %.2f)", ratio)
        return None
    return out


def command(selection, instruction, model, timeout=45.0):
    return _chat(model, COMMAND_PROMPT,
                 f"Anweisung: {instruction}\n\nMarkierter Text:\n{selection}", timeout)
