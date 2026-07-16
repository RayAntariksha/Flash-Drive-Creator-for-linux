#!/usr/bin/env bash
# install.sh — checks dependencies and installs a desktop launcher for
# Flash Drive Creator. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DESKTOP_DIR="${HOME}/.local/share/applications"
BIN_DIR="${HOME}/.local/bin"

echo "== Flash Drive Creator installer =="

missing=()

check() {
    if ! command -v "$1" >/dev/null 2>&1; then
        missing+=("$1")
    fi
}

check python3
check lsblk
check dd
check umount

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    missing+=("python3-tk")
fi

if ! command -v pkexec >/dev/null 2>&1 && ! command -v sudo >/dev/null 2>&1; then
    missing+=("pkexec (polkit) or sudo")
fi

if [ "${#missing[@]}" -ne 0 ]; then
    echo
    echo "Missing dependencies: ${missing[*]}"
    echo
    echo "Install them with your package manager, e.g.:"
    echo "  Debian/Ubuntu:  sudo apt install python3 python3-tk util-linux coreutils policykit-1"
    echo "  Fedora:         sudo dnf install python3 python3-tkinter util-linux coreutils polkit"
    echo "  Arch:           sudo pacman -S python tk util-linux coreutils polkit"
    echo
    echo "Re-run this script after installing them."
    exit 1
fi

echo "All dependencies found."

mkdir -p "$BIN_DIR" "$APP_DESKTOP_DIR"
chmod +x "$SCRIPT_DIR/flash_drive_creator.py"

# Small wrapper so the app can be launched as `flash-drive-creator` from a
# terminal or app launcher, regardless of where this repo was cloned.
cat > "$BIN_DIR/flash-drive-creator" <<EOF
#!/usr/bin/env bash
exec python3 "$SCRIPT_DIR/flash_drive_creator.py" "\$@"
EOF
chmod +x "$BIN_DIR/flash-drive-creator"

DESKTOP_FILE="$APP_DESKTOP_DIR/flash-drive-creator.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Flash Drive Creator
Comment=Write ISO/IMG files to USB flash drives
Exec=$BIN_DIR/flash-drive-creator
Terminal=false
Categories=System;Utility;
EOF

echo "Installed launcher: $DESKTOP_FILE"
echo "Installed command:  $BIN_DIR/flash-drive-creator"
echo
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    echo "Note: $BIN_DIR is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo
echo "Done. Launch from your application menu, or run: flash-drive-creator"
