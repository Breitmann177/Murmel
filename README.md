# Murmel

Lokale Diktier-App für **Windows 11 und Linux**. **Strg + Win (Linux: Strg + Super) halten, sprechen, loslassen** – der Text landet dort, wo der Cursor ist. Alles läuft auf dem eigenen Rechner: keine Cloud, kein Konto, kein API-Key.

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
- Verlauf, Wörterbuch und Einstellungen liegen in `%APPDATA%\Murmel` (Linux: `~/.config/murmel`) – nicht in diesem Repo
- Diktate werden vom Windows-Zwischenablageverlauf (Win + V) ausgenommen; die alte Zwischenablage wird wiederhergestellt
- Der Tastatur-Hook reagiert nur auf die eingestellte Tastenkombination und speichert keine Tasten
- Das Log (`murmel.log`) enthält keine diktierten Texte, nur Zeiten und Längen

## Installation (Windows)

1. **Python 3.12 (64-bit)** von [python.org](https://www.python.org/downloads/) installieren, dabei „Add python.exe to PATH“ anhaken.
2. Dieses Repo herunterladen (Code → Download ZIP) und entpacken.
3. **`install.bat`** doppelklicken. Das legt eine eigene Umgebung an, installiert alles, erstellt einen Eintrag im Startmenü und startet Murmel.

Mit NVIDIA-GPU werden die CUDA-Pakete automatisch mitinstalliert und `large-v3-turbo` auf der GPU genutzt (beim ersten Start ~1,6 GB Download), sonst `small` auf der CPU. Autostart lässt sich in den Einstellungen einschalten.

<details><summary>Manuell</summary>

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt        # ohne NVIDIA
.venv\Scripts\python -m pip install -r requirements-gpu.txt    # mit NVIDIA
.venv\Scripts\pythonw main.pyw
```
</details>

## Installation (Linux)

Getestet auf Fedora mit GNOME (Wayland). Das Skript kennt auch Ubuntu/Debian, Arch und openSUSE.

```bash
git clone https://github.com/Breitmann177/Murmel.git
cd Murmel
./install.sh
```

Das Skript installiert ein paar Systempakete, legt eine eigene Python-3.13-Umgebung an (über
`uv`, egal welches Python dein System hat), richtet die Tastenrechte ein und trägt Murmel ins
App-Menü ein. Danach einmal ab- und wieder anmelden.

**Unterschiede zu Windows**

- Tastenkürzel: Strg + Super (Super = Windows-Taste). Unter Wayland gibt es keine globalen
  Tasten-Hooks, deshalb liest Murmel die Tastatur über evdev.
- Eingefügt wird über eine virtuelle Tastatur (uinput): Strg + V, in Terminals Strg + Shift + V.
- Die aktive App erkennt Murmel über die Barrierefreiheits-Schnittstelle (AT-SPI). Das klappt bei
  GTK/Qt-Apps und Terminals. Wenn eine App nicht erkannt wird, gilt der Stil „Standard“.
- Mikrofon: immer das Standardgerät von PipeWire/PulseAudio (in den Systemeinstellungen wählbar).
- Esc bricht die Aufnahme ab, kommt aber zusätzlich auch bei der App an.

**Rechte:** `install.sh` legt die udev-Regel `/etc/udev/rules.d/70-murmel.rules` an. Damit darf der
gerade angemeldete Nutzer Tastaturen lesen und eine virtuelle Tastatur anlegen. Murmel achtet nur
auf die eingestellte Tastenkombination und speichert keine Tasten. Die Regel gilt aber für alle
Programme dieses Nutzers. Wer das nicht möchte, löscht die Datei, dann bleibt der Text nur in
der Zwischenablage.

## Tests

```bash
.venv\Scripts\python -m unittest discover tests
```

## Lizenzen von Drittanbietern

- Schriften: Instrument Serif, Inter – SIL Open Font License (`assets/fonts/OFL-*.txt`)
- Icons: Lucide – ISC (`assets/icons/LICENSE-lucide.txt`)

## Lizenz

MIT – siehe [LICENSE](LICENSE). Schriften und Icons stehen unter ihren eigenen Lizenzen (siehe oben).
