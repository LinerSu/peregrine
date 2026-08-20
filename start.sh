#!/usr/bin/env bash
#
# One-command launch for Peregrine.
#
# Brings up the web + api stack (Docker), then starts the LOCAL Claude terminal
# that powers the assistant's Internal mode. Run this instead of
# `docker compose up`.
#
# Claude runs on THIS machine (your host), using your own login — not in a
# container — so it has your subscription and sees this repo. Ctrl-C stops the
# terminal; the web/api stack keeps running in the background
# (stop it with `docker compose down`).
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # repo root (this script lives here)

# Self-heal the git hooks (PII + crawl-policy guards) — a fresh clone that never ran
# scripts/install-hooks.sh would otherwise commit with NO guard, silently. The logic
# lives in its own script so the test suite can pin it; it never fails the launch.
./scripts/ensure-hooks.sh

# Container identity: the api runs as YOU (docker-compose.yml `user:`), so export
# the real uid/gid — a hard-coded default would break hosts where they aren't 1000.
export PEREGRINE_UID="${PEREGRINE_UID:-$(id -u)}" PEREGRINE_GID="${PEREGRINE_GID:-$(id -g)}"

# Pre-create gitignored bind-mount sources (fresh clone: the Docker engine would
# otherwise create them ROOT-owned, crashing the non-root api on first boot), then
# fail fast with the exact fix if an old root-mode install left mounts root-owned —
# better than a crash loop with the real error buried in `docker compose logs`.
mkdir -p logs .demo
bad=""
for p in data config logs .demo applications resume .agents; do
  [ -e "$p" ] && [ ! -w "$p" ] && bad="$bad $p"
done
if [ -n "$bad" ]; then
  echo "✗ not writable by $(id -un) (root-owned from a pre-non-root install):$bad" >&2
  echo "  fix once, then re-run:" >&2
  echo "      sudo chown -R \$(id -u):\$(id -g)$bad" >&2
  exit 1
fi

echo "▶ Bringing up the Peregrine stack (web + api)…"
docker compose up -d --build

echo
echo "  Web UI:    http://localhost:5173"
echo "  Stack logs: docker compose logs -f      Stop stack: docker compose down"
echo
echo "▶ Starting the local terminal for Internal mode…"
echo "  Open the web UI, switch the assistant to Internal. Ctrl-C stops the terminal."
echo

# Hand off to the terminal launcher (it cd's into the repo and runs ttyd + claude).
exec ./scripts/terminal.sh
