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

# Fail clearly if the port is already taken, rather than ttyd's cryptic bind error.
if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
  exec 3>&-
  # Our own always-on user service holding the DEFAULT port is the RECOMMENDED state,
  # not an error — say so plainly instead of the worried bullets below (a real user
  # hit this and thought something was broken). INVOCATION_ID guard: when THIS run
  # IS the service (systemd sets it; the unit's ExecStart is this script), asking
  # systemd "is the service active?" is a tautology — exiting 0 here would mask a
  # foreign port-holder (e.g. apt's root ttyd) as success and stop Restart= retries.
  if [ -z "${INVOCATION_ID:-}" ] && [ "${PORT}" = "7681" ] \
      && systemctl --user is-active --quiet peregrine-terminal 2>/dev/null; then
    echo "✓ terminal already running via the peregrine-terminal service (port ${PORT}) — nothing to start."
    echo "  Open the web UI and switch the assistant to 'Internal (Claude)'."
    exit 0
  fi
  echo "Port ${PORT} is already in use — not starting a second terminal." >&2
  echo "  • Already set? The peregrine-terminal service may be running:" >&2
  echo "      systemctl --user status peregrine-terminal" >&2
  echo "  • apt's login terminal? Disable it:  sudo systemctl disable --now ttyd.service" >&2
  echo "  • Need another one? Use a different port: PEREGRINE_TERMINAL_PORT=7682 $0" >&2
  exit 1
fi

echo "Peregrine terminal → http://127.0.0.1:${PORT}  (running: ${CMD[*]}, local-only)"
echo "Switch the assistant to 'Internal (Claude)' in the web UI. Ctrl-C to stop."

# The writable flag moved across ttyd versions: ttyd >= 1.7 is read-only by
# default and needs -W/--writable; ttyd <= 1.6 is writable by default and has no
# -W (passing it prints "invalid option -- 'W'"). Add it only if this build has it.
WRITABLE=()
if ttyd --help 2>&1 | grep -q -- '--writable'; then
  WRITABLE=(-W)
fi

# -i 127.0.0.1 : bind to loopback only (do not change to 0.0.0.0)
exec ttyd -i 127.0.0.1 -p "${PORT}" "${WRITABLE[@]}" "${CMD[@]}"
