#!/usr/bin/env bash
set -euo pipefail

APP_ID="claude-usage-widget"
INSTALL_DIR="$HOME/.local/share/$APP_ID"
BIN_DIR="$HOME/.local/bin"

echo "Installing Claude Usage Widget..."

# Check dependencies
if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('AppIndicator3','0.1'); gi.require_version('Notify','0.7')" 2>/dev/null; then
    echo "Missing dependencies. Install with:"
    echo "  sudo apt install python3 python3-gi gir1.2-appindicator3-0.1 gir1.2-notify-0.7"
    read -rp "Install now? [Y/n] " yn
    case "${yn,,}" in
        n|no) exit 1 ;;
        *) sudo apt install -y python3 python3-gi gir1.2-appindicator3-0.1 gir1.2-notify-0.7 ;;
    esac
fi

# Install script
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
cp claude_usage_widget.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/claude_usage_widget.py"

# Start wrapper (clean env to avoid pyenv/snap conflicts)
cat > "$BIN_DIR/claude-widget-start" <<'EOF'
#!/bin/bash
env -i HOME="$HOME" DISPLAY="$DISPLAY" DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" PATH="/usr/local/bin:/usr/bin:/bin" \
  /usr/bin/python3 ~/.local/share/claude-usage-widget/claude_usage_widget.py > /tmp/claude-widget.log 2>&1 &
sleep 1 && ps aux | grep -q '[c]laude_usage_widget' && echo "Widget started" || { echo "Failed — see /tmp/claude-widget.log"; exit 1; }
EOF

# Stop wrapper
cat > "$BIN_DIR/claude-widget-stop" <<'EOF'
#!/bin/bash
pkill -f claude_usage_widget.py 2>/dev/null && echo "Widget stopped" || echo "Not running"
EOF

chmod +x "$BIN_DIR/claude-widget-start" "$BIN_DIR/claude-widget-stop"

# Autostart on login
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Widget
Exec=env -u LD_LIBRARY_PATH PATH="/usr/local/bin:/usr/bin:/bin" /usr/bin/python3 $INSTALL_DIR/claude_usage_widget.py
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

echo "Done. Run: claude-widget-start"
