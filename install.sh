#!/usr/bin/env bash
# Murmel – Installer für Linux (Fedora, Ubuntu/Debian, Arch, openSUSE; GNOME oder KDE)
# Ausführen als normaler Nutzer:  ./install.sh   (fragt einmal nach sudo)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
green() { printf '\e[1;32m==>\e[0m %s\n' "$*"; }
warn()  { printf '\e[1;33m!! \e[0m %s\n' "$*"; }

if [[ $EUID -eq 0 ]]; then
    echo "Bitte als normaler Nutzer starten (nicht mit sudo) – das Skript fragt selbst nach sudo."
    exit 1
fi

# --- Systempakete: PortAudio (Mikrofon), XWayland-Bibliotheken für Qt, Compiler für evdev -------
green "Systempakete installieren"
if command -v dnf >/dev/null; then
    sudo dnf install -y portaudio xcb-util-cursor gcc kernel-headers pipewire-utils curl uv
elif command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y libportaudio2 libxcb-cursor0 gcc linux-libc-dev pipewire-bin curl pipx
elif command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm portaudio xcb-util-cursor gcc linux-api-headers pipewire curl uv
elif command -v zypper >/dev/null; then
    sudo zypper install -y portaudio libxcb-cursor0 gcc linux-glibc-devel pipewire-tools curl
else
    warn "Unbekannter Paketmanager – bitte PortAudio, xcb-util-cursor und gcc selbst installieren."
fi

# --- Python 3.13 in eigener Umgebung (uv lädt es, egal welches Python das System hat) -----------
UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then UV="$HOME/.local/bin/uv"; fi
if [[ -z "$UV" ]]; then
    green "uv (Python-Paketmanager) installieren"
    if command -v pipx >/dev/null; then
        pipx install uv
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    UV="$HOME/.local/bin/uv"
fi

green "Python-Umgebung anlegen (.venv, Python 3.13)"
"$UV" venv --python 3.13 --allow-existing .venv
REQ=requirements.txt
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
    green "NVIDIA-Grafikkarte gefunden: GPU-Pakete werden mitinstalliert"
    REQ=requirements-gpu.txt
fi
"$UV" pip install --python .venv/bin/python -r "$REQ"

# --- Rechte: Tastatur lesen (Tastenkürzel) und virtuelle Tastatur (Einfügen) -------------------
# uaccess = nur der Nutzer, der gerade lokal am Bildschirm angemeldet ist, nicht andere Konten.
green "udev-Regel für Tastenkürzel und Einfügen"
sudo tee /etc/udev/rules.d/70-murmel.rules >/dev/null <<'EOF'
# Murmel: Tastatur lesen (Push-to-Talk) und virtuelle Tastatur für Strg+V (Einfügen)
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess"
EOF
sudo modprobe uinput || true
echo uinput | sudo tee /etc/modules-load.d/murmel-uinput.conf >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input --subsystem-match=misc || true

# --- Startmenü-Eintrag ---------------------------------------------------------------------------
green "Eintrag im App-Menü"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"
cat > "$APPS/murmel.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Murmel
Comment=Lokales Diktieren: Tastenkürzel halten, sprechen, loslassen
Exec="$DIR/.venv/bin/python" "$DIR/main.pyw"
Icon=$DIR/assets/murmel.png
Terminal=false
Categories=Utility;Accessibility;
Keywords=diktat;sprache;whisper;dictation;speech;
EOF
update-desktop-database "$APPS" 2>/dev/null || true

if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]] && command -v gnome-extensions >/dev/null; then
    gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null \
        || warn "Für das Tray-Symbol unter GNOME die Erweiterung „AppIndicator Support“ installieren."
fi

green "Fertig! Murmel startet jetzt (später: App-Menü → Murmel)."
warn "Falls das Tastenkürzel nicht reagiert: einmal ab- und wieder anmelden (neue Rechte)."
nohup "$DIR/.venv/bin/python" "$DIR/main.pyw" >/dev/null 2>&1 &
