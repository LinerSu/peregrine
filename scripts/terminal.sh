#!/usr/bin/env bash
#
# Launch the LOCAL-ONLY web terminal used by Peregrine's "Internal (Claude)"
# assistant mode. It serves an interactive `claude` session (your own Anthropic
# subscription — no API key) to the browser via ttyd.
#
# SECURITY: this is full shell access to your machine. It binds to 127.0.0.1 so
# it is reachable ONLY from this machine. Never bind it to 0.0.0.0 or expose the
# port to a network — anyone who can reach it gets a shell as you.
#
# Run it on the HOST (not inside Docker): the api container can't see your shell
# or your Claude login. The browser loads the terminal straight from the host.
#
#   ./scripts/terminal.sh           # serves `claude` on http://127.0.0.1:7681
#   PEREGRINE_TERMINAL_CMD=bash ./scripts/terminal.sh   # plain shell instead
#
set -euo pipefail

# Start in the repo root so `claude` opens with the project loaded, regardless of
# where this script is invoked from (the script lives in <repo>/scripts/).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PORT="${PEREGRINE_TERMINAL_PORT:-7681}"
# Split into an array so a multi-word override (e.g. "claude --resume") passes as
# separate args to ttyd — avoids unquoted word-splitting/globbing of the raw string.
read -r -a CMD <<< "${PEREGRINE_TERMINAL_CMD:-claude}"

if ! command -v ttyd >/dev/null 2>&1; then
  echo "ttyd is not installed. Install it, then re-run:" >&2
  echo "  macOS:        brew install ttyd" >&2
  echo "  Debian/Ubuntu: sudo apt install ttyd" >&2
  echo "  other:        https://github.com/tsl0922/ttyd#installation" >&2
  exit 1
fi

if ! command -v "${CMD[0]}" >/dev/null 2>&1; then
  echo "'${CMD[0]}' is not on PATH. Install Claude Code (https://claude.com/claude-code)" >&2
  echo "and run 'claude' once to log in, or set PEREGRINE_TERMINAL_CMD to another command." >&2
  exit 1
fi

echo "Peregrine terminal → http://127.0.0.1:${PORT}  (running: ${CMD[*]}, local-only)"
echo "Switch the assistant to 'Internal (Claude)' in the web UI. Ctrl-C to stop."

# -i 127.0.0.1 : bind to loopback only (do not change to 0.0.0.0)
# -W           : allow client keyboard input (required on ttyd >= 1.7; older
#                builds are writable by default — drop -W if your ttyd rejects it)
exec ttyd -i 127.0.0.1 -p "${PORT}" -W "${CMD[@]}"
