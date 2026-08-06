#!/usr/bin/env bash
#
# Install (or remove) a systemd USER service that runs Peregrine's local terminal
# for the assistant's Internal mode — so it's always running and you never start
# scripts/terminal.sh by hand.
#
# No sudo: this is a per-user service (it has your shell + your CLI login).
# It binds to 127.0.0.1 only (local-only; see scripts/terminal.sh).
#
#   ./scripts/install-terminal-service.sh                 # install + enable + start
#   PEREGRINE_TERMINAL_CMD=codex ./scripts/install-terminal-service.sh
#   ./scripts/install-terminal-service.sh --uninstall     # stop + disable + remove
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
  echo "Removed $UNIT — the Internal-mode terminal will no longer auto-start."
  echo "(You can still start it manually with ./scripts/terminal.sh or ./start.sh.)"
  exit 0
fi

# Which CLI the service should serve. Same knob scripts/terminal.sh reads, so the
# service and a hand-run terminal agree.
read -r -a CMD <<< "${PEREGRINE_TERMINAL_CMD:-claude}"
CLI="${CMD[0]}"

# Preconditions — fail before writing anything.
command -v ttyd >/dev/null 2>&1 || { echo "ttyd not installed (sudo apt install ttyd / brew install ttyd)." >&2; exit 1; }
if ! command -v "$CLI" >/dev/null 2>&1; then
  echo "'$CLI' is not on PATH — install it and sign in once first." >&2
  echo "  claude: https://claude.com/claude-code      codex: npm i -g @openai/codex" >&2
  echo "Or set PEREGRINE_TERMINAL_CMD to a command you have." >&2
  exit 1
fi

# A user unit starts with a minimal PATH, so a CLI installed anywhere else — nvm
# (~/.nvm/versions/node/<ver>/bin), an npm prefix, Homebrew — is simply not found
# and the service dies on every restart. Resolve it now and put its real directory
# first. Re-run this installer if you later move the CLI (e.g. switch node version).
CLI_DIR="$(cd "$(dirname "$(command -v "$CLI")")" && pwd)"
UNIT_PATH="$CLI_DIR:%h/.local/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$UNIT" <<EOF
[Unit]
Description=Peregrine local terminal for Internal mode ($CLI)
Documentation=https://github.com/LinerSu/peregrine
After=default.target

[Service]
Type=simple
# User services start with a minimal PATH, so the CLI's real directory (resolved
# at install time) goes first. WorkingDirectory is baked in so the CLI opens with
# this repo loaded.
Environment=PATH=$UNIT_PATH
Environment=PEREGRINE_TERMINAL_CMD=${PEREGRINE_TERMINAL_CMD:-claude}
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
echo "  Runs ttyd + $CLI on http://127.0.0.1:${PEREGRINE_TERMINAL_PORT:-7681}, auto-starts on login."
echo
echo "  Status:  systemctl --user status $UNIT"
echo "  Logs:    journalctl --user -u $UNIT -f"
echo "  Stop:    systemctl --user stop $UNIT"
echo "  Remove:  ./scripts/install-terminal-service.sh --uninstall"
echo
echo "Now just 'docker compose up' and click Internal in the web UI."
echo
echo "Note: this runs while you're logged in. To keep it running even when you're"
echo "not logged in (headless), run once:  sudo loginctl enable-linger $USER"
