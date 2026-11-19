<p align="center"><img src="assets/murmel.png" width="88" alt=""></p>

<h1 align="center">Murmel</h1>

<p align="center">Taste halten, sprechen, loslassen – der Text landet dort, wo dein Cursor ist.<br>
Läuft komplett auf deinem Rechner: keine Cloud, kein Konto, kein API-Key.</p>

<p align="center">
  <a href="https://github.com/Breitmann177/Murmel/releases/latest/download/Murmel-Windows.zip"><img src="https://img.shields.io/badge/%E2%86%93%20Windows-0078D4?style=for-the-badge" alt="Download für Windows"></a>
  &nbsp;
  <a href="https://github.com/Breitmann177/Murmel/releases/latest/download/Murmel-macOS.zip"><img src="https://img.shields.io/badge/%E2%86%93%20macOS-6E6E78?style=for-the-badge" alt="Download für macOS"></a>
  &nbsp;
  <a href="https://github.com/Breitmann177/Murmel/releases/latest/download/Murmel-Linux.tar.gz"><img src="https://img.shields.io/badge/%E2%86%93%20Linux-E95420?style=for-the-badge" alt="Download für Linux"></a>
</p>

<p align="center"><sub>
  <b>Windows:</b> entpacken → <code>install.bat</code> doppelklicken &nbsp;·&nbsp;
  <b>macOS:</b> entpacken → im Terminal <code>bash install-mac.sh</code> &nbsp;·&nbsp;
  <b>Linux:</b> entpacken → <code>./install.sh</code><br>
  Beim ersten Start wird das Sprachmodell einmalig geladen (0,5–1,6 GB).
</sub></p>

---

## So benutzt du es

| | Windows | macOS | Linux |
|---|---|---|---|
| Diktieren (halten) | Strg + Win | Ctrl + Cmd | Strg + Super |
| Freihand | 2× tippen | 2× tippen | 2× tippen |
| Befehl an die KI | Strg + Win + Alt | Ctrl + Cmd + Option | Strg + Super + Alt |
| Abbrechen | Esc | Esc | Esc |

Fahr mit der Maus über die kleine Pille unten am Bildschirm: **●** startet eine längere Aufnahme
(z. B. eine Vorlesung), die als `.txt` gespeichert wird. Der schmale Pfeil daneben wählt die
Tonquelle: **Mikrofon**, **Laptop-Ton** oder **beides**.

## Was Murmel kann

- **Push-to-Talk** und **Freihand** (mit Pause, bis 4 h), Live-Vorschau beim Sprechen (mit NVIDIA-GPU)
- **Aufnahmen** über die Pille werden schon während der Aufnahme als Datei gespeichert
- **Bereinigung**: Füllwörter, Selbstkorrekturen („um drei, nein, um vier“), „neue Zeile“, Listen, Fragezeichen
- **Wörterbuch**, **Snippets** und **Stil pro App** (locker in Chats, formell in Mail/Word, Code im Editor)
- Optional **Ollama** (lokale KI) für den Stark-Modus und den Befehls-Modus
- Verlauf, Statistiken, Hell/Dunkel, Bildschirm-aus während langer Aufnahmen (OLED)

## Installation im Detail

<details><summary><b>Windows</b></summary>

1. **Python 3.12 (64-bit)** von [python.org](https://www.python.org/downloads/) installieren, dabei
   „Add python.exe to PATH“ anhaken.
2. `Murmel-Windows.zip` entpacken und **`install.bat`** doppelklicken. Das legt eine eigene
   Umgebung an, installiert alles, erstellt einen Startmenü-Eintrag und startet Murmel.

Mit NVIDIA-GPU werden die CUDA-Pakete automatisch mitinstalliert und `large-v3-turbo` auf der
GPU genutzt, sonst `small` auf der CPU. Autostart lässt sich in den Einstellungen einschalten.
</details>

<details><summary><b>macOS</b></summary>

1. `Murmel-macOS.zip` entpacken (z. B. in „Downloads“).
2. Terminal öffnen und eingeben (Ordnerpfad anpassen):
   ```bash
   cd ~/Downloads/Murmel
   bash install-mac.sh
   ```
   Das Skript lädt ein passendes Python, installiert alles und legt **Murmel.app** in
   `~/Applications` an.
3. **Zwei Erlaubnisse** (einmalig):
   - **Mikrofon** – macOS fragt beim ersten Diktat selbst.
   - **Bedienungshilfen** – Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen →
     „Murmel“ einschalten, dann Murmel neu starten. Nötig für das Tastenkürzel und das Einfügen.

Murmel läuft oben in der Menüleiste (kein Dock-Symbol). Auf Apple-Chips läuft die Erkennung auf
dem Prozessor (~1–2 s pro Diktat). **Laptop-Ton** aufnehmen geht mit dem kostenlosen
[BlackHole 2ch](https://existential.audio/blackhole/).
</details>

<details><summary><b>Linux</b></summary>

Getestet auf Fedora mit GNOME (Wayland). Das Skript kennt auch Ubuntu/Debian, Arch und openSUSE.

```bash
tar xzf Murmel-Linux.tar.gz && cd Murmel
./install.sh
```

Das Skript installiert ein paar Systempakete, legt eine eigene Python-Umgebung an (über `uv`),
richtet die Tastenrechte ein und trägt Murmel ins App-Menü ein. Danach einmal ab- und wieder
anmelden.

- Unter Wayland gibt es keine globalen Tasten-Hooks, deshalb liest Murmel die Tastatur über evdev.
- Eingefügt wird über eine virtuelle Tastatur (uinput): Strg + V, in Terminals Strg + Shift + V.
- **Rechte:** `install.sh` legt die udev-Regel `/etc/udev/rules.d/70-murmel.rules` an. Damit darf
  der angemeldete Nutzer Tastaturen lesen und eine virtuelle Tastatur anlegen. Murmel achtet nur
  auf die eingestellte Tastenkombination und speichert keine Tasten.
</details>

## Datenschutz

- Netzwerk nur für den einmaligen Modell-Download (Hugging Face) und zu Ollama auf `localhost`
- Verlauf, Wörterbuch und Einstellungen bleiben auf deinem Rechner
  (Windows `%APPDATA%\Murmel`, macOS `~/Library/Application Support/Murmel`, Linux `~/.config/murmel`)
- Diktate landen nicht im Zwischenablage-Verlauf; die alte Zwischenablage wird wiederhergestellt
- Das Tastenkürzel reagiert nur auf die eingestellte Kombination und speichert keine Tasten
- Das Log (`murmel.log`) enthält keine diktierten Texte, nur Zeiten und Längen

## Für Entwickler

```bash
python -m unittest discover tests
```

## Lizenz

MIT – siehe [LICENSE](LICENSE). Schriften (Instrument Serif, Inter – SIL Open Font License) und
Icons (Lucide – ISC) stehen unter ihren eigenen Lizenzen, siehe `assets/`.
