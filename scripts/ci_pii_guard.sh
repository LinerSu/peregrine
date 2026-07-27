#!/usr/bin/env bash
# CI backstop for the PII guards — the GENERIC subset only (personal-path regex +
# email scan). The personal-term denylist (config/pii_terms.txt) deliberately stays
# local: uploading your real name/phone to CI would itself be the leak. Honest
# framing: by the time CI sees a hit the bytes are already on GitHub — this is
# detection-before-merge (a red X blocks the PR-protected main and tells you to
# scrub the branch), not prevention. The local hooks remain the actual wall.
#
# Scans PER-COMMIT over the pushed range (git log), not just the endpoint diff: a
# commit that adds PII followed by one that removes it leaves the endpoint diff
# clean, yet the bytes are pushed and stay reachable (refs/pull) — exactly the
# fixup-on-top pattern the remediation text warns about. Commit MESSAGES in the
# range are scanned too (the commit-msg hook is bypassable with --no-verify or an
# uninstalled hooksPath). All output is REDACTED — Actions logs persist and would
# otherwise mint a second copy of the PII that outlives a branch scrub.
#
# Usage (from repo root, full-history checkout):  bash scripts/ci_pii_guard.sh <base-sha>
#   <base-sha>: the PR base sha or push `before` sha. An unusable base (empty,
#   all-zeros on branch-creation/force-push, or unreachable after a rewrite) falls
#   back to scanning ALL commits reachable from HEAD — fail closed (a HEAD~1-style
#   fallback would scan only the last commit of a multi-commit push).
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../hooks/pii-lib.sh"

zeros="0000000000000000000000000000000000000000"
usable() { [ -n "$1" ] && [ "$1" != "$zeros" ] && git cat-file -e "$1^{commit}" 2>/dev/null; }

base="${1:-}"
# Known-clean floor for the fallback: the repo's EARLY history contains since-removed
# demo scaffolding under personal-data paths (pre-*.example.csv rename), so an
# unbounded full-history scan is guaranteed-red forever — including on the very CI
# run that follows a leak scrub (force-push ⇒ unusable `before` sha), burying the
# real signal. PII_GUARD_BASELINE (set in ci.yml) bounds the fallback to commits
# after that point; everything since is scanned, still fail-closed.
if ! usable "$base"; then base="${PII_GUARD_BASELINE:-}"; fi
if usable "$base"; then
  # merge-base so a stale PR base doesn't blame main's own history on this branch.
  endpoint_base="$(git merge-base "$base" HEAD 2>/dev/null || echo "$base")"
  range="${endpoint_base}..HEAD"
else
  endpoint_base=""
  range="HEAD"
fi
echo "scanning commits in ${range}"

# quotepath=off everywhere: default git C-quotes non-ASCII paths (leading literal
# `"`), which the ^-anchored path regex would never match — same fail-open fixed in
# hooks/pre-commit. The endpoint diff is appended as a belt for merge-commit
# conflict resolutions, which plain `git log -p`/`--name-only` skips.

changed_paths() {
  git -c core.quotepath=off log --format= --name-only --diff-filter=ACMR "$range"
  if [ -n "$endpoint_base" ]; then
    git -c core.quotepath=off diff --name-only --diff-filter=ACMR "$endpoint_base" HEAD
  fi
}

added_lines() {
  {
    git -c core.quotepath=off log -p -U0 --format= --diff-filter=ACMR "$range"
    if [ -n "$endpoint_base" ]; then
      # --no-ext-diff: porcelain `git diff` honors external diff drivers, whose output
      # has no ^+ lines — the scan would silently blank on a local run (git log
      # already defaults to no-ext-diff).
      git -c core.quotepath=off diff -U0 --no-ext-diff --diff-filter=ACMR "$endpoint_base" HEAD
    fi
  } | grep -E '^\+' | grep -vE '^[+]{3} ([ab]/|/dev/null)' || true
}

fail=0

paths="$(changed_paths | sort -u | pii_offending_paths)"
if [ -n "$paths" ]; then
  echo "✗ ci-pii-guard: personal-data paths in this push (basenames redacted here —" >&2
  echo "  a résumé/CV filename can itself carry a real name, and Actions logs persist):" >&2
  # keep only the first (repo-structural) component: user-named SUBDIRECTORIES under
  # resume/ or applications/ can carry a real name just like a basename.
  printf '%s\n' "$paths" \
    | sed -E -e 's|^([^/]+)/.+$|\1/<redacted>|' -e 's|^[^/]+$|<redacted>|' \
    | sort -u | sed 's/^/  /' >&2
  echo "  run the local pre-commit hook (or git log --name-only) for the full paths." >&2
  fail=1
fi

mails="$(added_lines | pii_offending_emails)"
if [ -n "$mails" ]; then
  echo "✗ ci-pii-guard: real-looking email addresses in added lines (redacted here —" >&2
  echo "  Actions logs persist and outlive a branch scrub; run the local hook for the full strings):" >&2
  # mask EVERYTHING after the first domain character — leaving later labels visible
  # (`j***@m***.acme-corp.com`) would leak the identifying org domain into the log.
  printf '%s\n' "$mails" | sed -E 's/^(.)[^@]*@(.).*$/    \1***@\2***/' >&2
  echo "  use @example.com placeholders in anything that ships." >&2
  fail=1
fi

msg_mails="$(git log --format=%B "$range" | pii_offending_emails)"
if [ -n "$msg_mails" ]; then
  echo "✗ ci-pii-guard: real-looking email addresses in a commit MESSAGE in this range (redacted):" >&2
  printf '%s\n' "$msg_mails" | sed -E 's/^(.)[^@]*@(.).*$/    \1***@\2***/' >&2
  echo "  reword via rebase — the message is recorded on GitHub just like file content." >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "  the content is already pushed — scrub the BRANCH HISTORY (rebase/amend + force-push)," >&2
  echo "  don't just add a fixup commit on top. Then delete this workflow run's logs" >&2
  echo "  (Actions → this run → ⋯ → Delete workflow run) so no copy outlives the scrub." >&2
  exit 1
fi
echo "✓ ci-pii-guard: no personal paths or real-looking emails in the pushed commits"
