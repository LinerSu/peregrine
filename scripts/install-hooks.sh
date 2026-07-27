#!/usr/bin/env bash
# Point git at the repo's tracked hooks (hooks/). Run once per clone.
set -euo pipefail

# Refuse unless the repo this script ships in IS the git toplevel. A bare
# `git rev-parse --show-toplevel` answers for any ENCLOSING repo, so running from a
# tarball/zip copy nested inside another repo's work tree would rewrite that
# unrelated repo's core.hooksPath — silently disabling its own hooks — while
# printing a success message for guards that were never installed here.
# pwd -P (physical): `git rev-parse --show-toplevel` resolves symlinks, so a logical
# path here would false-refuse a perfectly valid clone reached via a symlink.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null || true)"
if [ "$top" != "$root" ]; then
  echo "✗ install-hooks: $root is not the top of a git checkout (git sees: ${top:-no repo})" >&2
  echo "  refusing — this would rewrite core.hooksPath of an unrelated enclosing repo." >&2
  echo "  clone the repo properly, then re-run." >&2
  exit 1
fi

cd "$root"
git config core.hooksPath hooks
chmod +x hooks/* 2>/dev/null || true
echo "✓ git hooks installed (core.hooksPath=hooks)"
echo "  commit-msg: PII scan of the message + enforce <type>: <summary>"
echo "  pre-commit: py_compile staged + crawl-policy guard + PII path/email/denylist guard"
echo "  tip: cp config/pii_terms.example.txt config/pii_terms.txt and add YOUR terms"
