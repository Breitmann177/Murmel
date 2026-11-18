# Murmel

Lokale Diktier-App für Windows 11. **Strg + Win halten, sprechen, loslassen** – der Text landet dort, wo der Cursor ist. Alles läuft auf dem eigenen Rechner: keine Cloud, kein Konto, kein API-Key.

## Was Murmel kann

- **Push-to-Talk** mit Strg + Win, **Freihand** per Doppeltipp oder ● in der Pille (mit Pause, bis 4 h)
- **Live-Vorschau** beim Sprechen (mit NVIDIA-GPU), eingefügt wird der saubere Durchlauf über die ganze Aufnahme
- **Lange Aufnahmen** werden schon während der Aufnahme in Häppchen erkannt
- **Bereinigung**: Füllwörter, Selbstkorrekturen („um drei, nein, um vier“), „neue Zeile“, Listen, Fragezeichen
- **Wörterbuch**, **Snippets** und **Stil pro App** (locker in Chats, formell in Mail/Word, Code im Editor)
- Optional **Ollama** (lokale KI) für den Stark-Modus und den Command Mode (Strg + Win + Alt)
- Verlauf, Statistiken, Hell/Dunkel, Bildschirm-aus während langer Aufnahmen (OLED)

## Datenschutz

- Netzwerk nur für den einmaligen Modell-Download (Hugging Face) und zu Ollama auf `localhost`
- Verlauf, Wörterbuch und Einstellungen liegen in `%APPDATA%\Murmel` – nicht in diesem Repo
- Diktate werden vom Windows-Zwischenablageverlauf (Win + V) ausgenommen; die alte Zwischenablage wird wiederhergestellt
- Der Tastatur-Hook reagiert nur auf die eingestellte Tastenkombination und speichert keine Tasten

## Installation

Python 3.12 (64-bit):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\pythonw main.pyw
```

Mit NVIDIA-GPU wird automatisch `large-v3-turbo` auf CUDA genutzt (beim ersten Start ~1,6 GB Download), sonst `small` auf der CPU.

## Tests

```bash
.venv\Scripts\python -m unittest discover tests
```

## Lizenzen von Drittanbietern

- Schriften: Instrument Serif, Inter – SIL Open Font License (`assets/fonts/OFL-*.txt`)
- Icons: Lucide – ISC (`assets/icons/LICENSE-lucide.txt`)
