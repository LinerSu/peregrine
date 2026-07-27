#!/usr/bin/env bash
# CI backstop for the PII guards — the GENERIC subset only (personal-path regex +
# email scan over the pushed diff). The personal-term denylist (config/pii_terms.txt)
# deliberately stays local: uploading your real name/phone to CI would itself be the
# leak. Honest framing: by the time CI sees a hit the bytes are already on GitHub —
# this is detection-before-merge (a red X blocks the PR-protected main and tells you
# to scrub the branch), not prevention. The local hooks remain the actual wall.
#
# Usage (from repo root, full-history checkout):  bash scripts/ci_pii_guard.sh <base-sha>
#   <base-sha>: the PR base sha or push `before` sha; falls back to HEAD~1, then to
#   the empty tree (single-commit repo ⇒ scan everything).
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../hooks/pii-lib.sh"

base="${1:-}"
zeros="0000000000000000000000000000000000000000"
if [ -z "$base" ] || [ "$base" = "$zeros" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  base="$(git rev-parse HEAD~1 2>/dev/null)" || base="$(git hash-object -t tree /dev/null)"
fi
# merge-base so a stale PR base doesn't blame main's own history on this branch.
range_base="$(git merge-base "$base" HEAD 2>/dev/null || echo "$base")"
echo "scanning diff ${range_base}..HEAD"

fail=0

paths="$(git diff --name-only --diff-filter=ACMR "$range_base" HEAD | pii_offending_paths)"
if [ -n "$paths" ]; then
  echo "✗ ci-pii-guard: personal-data paths in this diff (these must stay on your machine):" >&2
  printf '  %s\n' "$paths" >&2
  fail=1
fi

mails="$(git diff -U0 --diff-filter=ACMR "$range_base" HEAD \
  | grep -E '^\+' | grep -vE '^[+]{3} ([ab]/|/dev/null)' | pii_offending_emails || true)"
if [ -n "$mails" ]; then
  echo "✗ ci-pii-guard: real-looking email addresses in added lines:" >&2
  printf '    %s\n' "$mails" >&2
  echo "  use @example.com placeholders in anything that ships." >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "  the content is already pushed — scrub the BRANCH HISTORY (rebase/amend + force-push)," >&2
  echo "  don't just add a fixup commit on top." >&2
  exit 1
fi
echo "✓ ci-pii-guard: no personal paths or real-looking emails in the diff"
