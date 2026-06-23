#!/usr/bin/env bash
# Switch the active dataset for the running stack (dev convenience). Flips
# PEREGRINE_DATASET in .env and restarts the API — the web reflects it on refresh
# (no rebuild: only the API's data changes, not the frontend).
#
#   ./scripts/dataset.sh                 # show the active dataset + what's available
#   ./scripts/dataset.sh ai-engineer     # a built-in demo persona
#   ./scripts/dataset.sh marcela         # a private local dataset (.demo/marcela/)
#   ./scripts/dataset.sh off             # back to your live config/ + data/
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env
PERSONAS="ai-engineer ux-designer chem-phd bio-scientist law-student"

[ -f "$ENV_FILE" ] || { echo "no .env — run: cp .env.example .env"; exit 1; }
# Portable in-place sed: GNU wants `-i`, BSD/macOS wants `-i ''`.
sedi() { if sed --version >/dev/null 2>&1; then sed -i "$@"; else sed -i '' "$@"; fi; }
# `|| true` so a missing line (live mode) doesn't trip `set -e`/pipefail.
current() { grep -E '^PEREGRINE_DATASET=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true; }
restart() {
  if docker compose up -d api >/dev/null; then  # keep stderr visible on failure
    echo "→ $1  (refresh the web to see it)"
  else
    echo "restart failed — is Docker running? (.env was updated)" >&2
    exit 1
  fi
}

case "${1:-}" in
  ""|status)
    cur="$(current)"
    echo "active dataset: ${cur:-<live: config/ + data/>}"
    echo "built-in personas: $PERSONAS"
    [ -d .demo ] && echo "local datasets:    $(ls .demo 2>/dev/null | tr '\n' ' ')"
    echo "usage: $0 <name> | off"
    ;;
  off|live|clear|--clear)
    sedi -E '/^[# ]*PEREGRINE_DATASET=/d' "$ENV_FILE"
    restart "live mode (your config/ + data/)"
    ;;
  *)
    name="$1"
    # Validate up front (same rule the API enforces) — also keeps the value safe for sed.
    if ! printf '%s' "$name" | grep -qE '^[a-z0-9][a-z0-9_-]*$'; then
      echo "invalid dataset name '$name' — start with a-z/0-9, then a-z/0-9/-/_." >&2
      exit 1
    fi
    # Warn if it's neither a built-in persona nor an existing private local dataset
    # (the API would otherwise exit on startup). A built-in persona self-seeds.
    if ! printf '%s ' $PERSONAS | grep -qw "$name" && [ ! -e ".demo/$name/.seeded" ]; then
      echo "warning: '$name' is not a built-in persona and has no .demo/$name/ dataset yet."
      echo "         create .demo/$name/{config,data}/ (with a .seeded marker) first, or pick: $PERSONAS"
    fi
    if grep -qE '^[# ]*PEREGRINE_DATASET=' "$ENV_FILE"; then
      sedi -E "s|^[# ]*PEREGRINE_DATASET=.*|PEREGRINE_DATASET=$name|" "$ENV_FILE"
    else
      printf '\nPEREGRINE_DATASET=%s\n' "$name" >> "$ENV_FILE"
    fi
    restart "dataset '$name'"
    ;;
esac
