#!/usr/bin/env bash
# CI backstop for the PII guards — the GENERIC subset only (personal-path regex +
# email scan over the pushed diff). The personal-term denylist (config/pii_terms.txt)
# deliberately stays local: uploading your real name/phone to CI would itself be the
# leak. Honest framing: by the time CI sees a hit the bytes are already on GitHub —
# this is detection-before-merge (a red X blocks the PR-protected main and tells you
# to scrub the branch), not prevention. The local hooks remain the actual wall.
#
# Usage (from repo root, full-history checkout):  bash scripts/ci_pii_guard.sh <base-sha>
#   <base-sha>: the PR base sha or push `before` sha. An unusable base (empty,
#   all-zeros on branch-creation/force-push, or unreachable after a rewrite) falls
#   back to the EMPTY TREE — i.e. scan every file reachable from HEAD. Fail closed:
#   a HEAD~1-style fallback would scan only the last commit of a multi-commit push.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../hooks/pii-lib.sh"

base="${1:-}"
zeros="0000000000000000000000000000000000000000"
if [ -z "$base" ] || [ "$base" = "$zeros" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  base="$(git hash-object -t tree /dev/null)"
fi
# merge-base so a stale PR base doesn't blame main's own history on this branch.
range_base="$(git merge-base "$base" HEAD 2>/dev/null || echo "$base")"
echo "scanning diff ${range_base}..HEAD"

fail=0

# quotepath=off: default git C-quotes non-ASCII paths (leading literal `"`), which the
# ^-anchored path regex would never match — same fail-open fixed in hooks/pre-commit.
paths="$(git -c core.quotepath=off diff --name-only --diff-filter=ACMR "$range_base" HEAD | pii_offending_paths)"
if [ -n "$paths" ]; then
  echo "✗ ci-pii-guard: personal-data paths in this diff (these must stay on your machine):" >&2
  printf '  %s\n' "$paths" >&2
  fail=1
fi

mails="$(git -c core.quotepath=off diff -U0 --diff-filter=ACMR "$range_base" HEAD \
  | grep -E '^\+' | grep -vE '^[+]{3} ([ab]/|/dev/null)' | pii_offending_emails || true)"
if [ -n "$mails" ]; then
  echo "✗ ci-pii-guard: real-looking email addresses in added lines (redacted here —" >&2
  echo "  Actions logs persist and outlive a branch scrub; run the local hook for the full strings):" >&2
  printf '%s\n' "$mails" | sed -E 's/^(.)[^@]*@(.)[^.]*/    \1***@\2***/' >&2
  echo "  use @example.com placeholders in anything that ships." >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "  the content is already pushed — scrub the BRANCH HISTORY (rebase/amend + force-push)," >&2
  echo "  don't just add a fixup commit on top. Then delete this workflow run's logs" >&2
  echo "  (Actions → this run → ⋯ → Delete workflow run) so no copy outlives the scrub." >&2
  exit 1
fi
echo "✓ ci-pii-guard: no personal paths or real-looking emails in the diff"
