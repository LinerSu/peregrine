#!/usr/bin/env bash
#
# One-command launch for Peregrine.
#
# Brings up the web + api stack (Docker), then starts the LOCAL Claude terminal
# that powers the assistant's "Internal (Claude)" mode. Run this instead of
# `docker compose up`.
#
# Claude runs on THIS machine (your host), using your own login — not in a
# container — so it has your subscription and sees this repo. Ctrl-C stops the
# terminal; the web/api stack keeps running in the background
# (stop it with `docker compose down`).
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # repo root (this script lives here)

# Self-heal the git hooks (PII + crawl-policy guards). A fresh clone that never ran
# scripts/install-hooks.sh would otherwise commit with NO guard — silently.
if [ "$(git config core.hooksPath 2>/dev/null || true)" != "hooks" ]; then
  ./scripts/install-hooks.sh
fi

echo "▶ Bringing up the Peregrine stack (web + api)…"
docker compose up -d --build

echo
echo "  Web UI:    http://localhost:5173"
echo "  Stack logs: docker compose logs -f      Stop stack: docker compose down"
echo
echo "▶ Starting the local Claude terminal for 'Internal (Claude)' mode…"
echo "  Open the web UI, switch the assistant to 'Internal (Claude)'. Ctrl-C stops the terminal."
echo

# Hand off to the terminal launcher (it cd's into the repo and runs ttyd + claude).
exec ./scripts/terminal.sh
