#!/usr/bin/env bash
#
# Install (or remove) a systemd USER service that runs Peregrine's local Claude
# terminal for the assistant's "Internal (Claude)" mode — so it's always running
# and you never start scripts/terminal.sh by hand.
#
# No sudo: this is a per-user service (it has your shell + your Claude login).
# It binds to 127.0.0.1 only (local-only; see scripts/terminal.sh).
#
#   ./scripts/install-terminal-service.sh             # install + enable + start
#   ./scripts/install-terminal-service.sh --uninstall # stop + disable + remove
#
set -euo pipefail

UNIT="peregrine-terminal.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v systemctl >/dev/null 2>&1 || { echo "systemctl not found — this installer needs systemd (Linux)." >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ] || [ "${1:-}" = "-u" ]; then
  systemctl --user disable --now "$UNIT" 2>/dev/null || true
  rm -f "$UNIT_DIR/$UNIT"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "Removed $UNIT — the Claude terminal will no longer auto-start."
  echo "(You can still start it manually with ./scripts/terminal.sh or ./start.sh.)"
  exit 0
fi

# Preconditions — fail before writing anything.
command -v ttyd   >/dev/null 2>&1 || { echo "ttyd not installed (sudo apt install ttyd / brew install ttyd)." >&2; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "claude not on PATH — install Claude Code and run 'claude' once to log in first." >&2; exit 1; }

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$UNIT" <<EOF
[Unit]
Description=Peregrine local Claude terminal (assistant "Internal (Claude)" mode)
Documentation=https://github.com/LinerSu/peregrine
After=default.target

[Service]
Type=simple
# User services start with a minimal PATH; ~/.local/bin is where claude usually
# lives. WorkingDirectory is baked in so claude opens with this repo loaded.
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=$REPO
# Quoted so a repo path containing spaces parses as a single executable
# (systemd splits ExecStart on whitespace; WorkingDirectory takes the literal line).
ExecStart="$REPO/scripts/terminal.sh"
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"

echo "✓ Installed $UNIT (user service — no sudo)."
echo "  Runs ttyd + claude on http://127.0.0.1:7681, auto-starts on login."
echo
echo "  Status:  systemctl --user status $UNIT"
echo "  Logs:    journalctl --user -u $UNIT -f"
echo "  Stop:    systemctl --user stop $UNIT"
echo "  Remove:  ./scripts/install-terminal-service.sh --uninstall"
echo
echo "Now just 'docker compose up' and click 'Internal (Claude)' in the web UI."
echo
echo "Note: this runs while you're logged in. To keep it running even when you're"
echo "not logged in (headless), run once:  sudo loginctl enable-linger $USER"
