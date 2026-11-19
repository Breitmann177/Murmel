#!/usr/bin/env bash
# Murmel – Installer für macOS (Apple Silicon und Intel, macOS 12 oder neuer)
# Im Terminal ausführen:   bash install-mac.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
green() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!! \033[0m %s\n' "$*"; }

# --- uv: lädt ein passendes Python herunter, egal was auf dem Mac installiert ist ---------------
UV="$(command -v uv || true)"
[[ -z "$UV" && -x "$HOME/.local/bin/uv" ]] && UV="$HOME/.local/bin/uv"
if [[ -z "$UV" ]]; then
    green "uv (Python-Paketmanager) installieren"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV="$HOME/.local/bin/uv"
fi

green "Python-Umgebung anlegen"
"$UV" venv --python 3.12 --allow-existing .venv
green "Pakete installieren (beim ersten Mal ein paar Minuten)"
"$UV" pip install --python .venv/bin/python -r requirements.txt

# --- Murmel.app bauen: eigenes App-Paket, damit macOS die Erlaubnisse "Murmel" zuordnet ----------
APP="$HOME/Applications/Murmel.app"
green "App anlegen: $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/Murmel" <<EOF
#!/bin/bash
cd "$DIR"
exec "$DIR/.venv/bin/python" "$DIR/main.pyw"
EOF
chmod +x "$APP/Contents/MacOS/Murmel"

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Murmel</string>
  <key>CFBundleDisplayName</key><string>Murmel</string>
  <key>CFBundleIdentifier</key><string>de.murmel.app</string>
  <key>CFBundleExecutable</key><string>Murmel</string>
  <key>CFBundleIconFile</key><string>murmel</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Murmel hört nur zu, während du die Tastenkombination hältst oder eine Aufnahme startest. Alles bleibt auf diesem Mac.</string>
</dict></plist>
EOF

# Symbol aus dem Ring-Logo erzeugen (.icns)
ICONSET="$(mktemp -d)/murmel.iconset"
mkdir -p "$ICONSET"
.venv/bin/python - "$ICONSET" <<'PY'
import sys, logo
out = sys.argv[1]
for s in (16, 32, 64, 128, 256, 512, 1024):
    data = logo.png_bytes(logo.render_icon(s))
    names = {16: ["icon_16x16"], 32: ["icon_16x16@2x", "icon_32x32"], 64: ["icon_32x32@2x"],
             128: ["icon_128x128"], 256: ["icon_128x128@2x", "icon_256x256"],
             512: ["icon_256x256@2x", "icon_512x512"], 1024: ["icon_512x512@2x"]}[s]
    for n in names:
        open(f"{out}/{n}.png", "wb").write(data)
PY
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/murmel.icns" || warn "Symbol konnte nicht erzeugt werden"

green "Fertig! Murmel startet jetzt."
cat <<'TXT'

  Zwei Erlaubnisse braucht Murmel (einmalig):

  1. MIKROFON – macOS fragt beim ersten Diktat selbst nach. "Erlauben" klicken.
  2. BEDIENUNGSHILFEN – für das Tastenkürzel (Ctrl + Cmd halten) und das Einfügen:
     Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen → "Murmel" einschalten.
     (Das Fenster öffnet sich gleich automatisch.) Danach Murmel einmal neu starten.

  Murmel findest du danach unter Programme (~/Applications) und oben in der Menüleiste.
  Laptop-Ton (z. B. Zoom-Vorlesung) aufnehmen: kostenloses "BlackHole 2ch" installieren.

TXT
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" || true
open "$APP"
