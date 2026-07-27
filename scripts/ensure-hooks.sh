#!/usr/bin/env bash
# Self-heal the git hooks (PII + crawl-policy guards) — called by start.sh on every
# launch so a fresh clone that never ran install-hooks.sh doesn't commit unguarded.
# Safe everywhere: refuses to touch an enclosing repo (a tarball copy nested inside
# some OTHER repo's work tree must not rewrite that repo's core.hooksPath), and
# NEVER fails the launch — the no-git/nested case warns loudly and exits 0.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [ "$(git rev-parse --show-toplevel 2>/dev/null || true)" = "$(pwd -P)" ]; then
  if [ "$(git config core.hooksPath 2>/dev/null || true)" != "hooks" ]; then
    ./scripts/install-hooks.sh
  fi
else
  echo "⚠ this directory is not its own git checkout (tarball copy? sudo?) —" >&2
  echo "  PII/crawl-policy commit hooks NOT installed; commit from a real clone only." >&2
fi
