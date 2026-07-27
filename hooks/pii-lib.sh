# Shared PII-guard definitions — the SINGLE source of truth for the personal-data
# patterns. Sourced by hooks/pre-commit, hooks/commit-msg, and scripts/ci_pii_guard.sh
# so the three guards can't drift apart; api/tests/test_pii_hook.py pins the behavior
# and asserts parity with the personal-data block in .gitignore.

# Personal-data paths. ROOT-anchored like git's non-trailing-slash globs (so a future
# web/src/applications/ source dir isn't falsely blocked), with an optional api/ prefix
# for the test-mount copies (api/data, api/applications). Blocks ALL of data/jobs/
# (snapshots, evaluations, tailored CVs .cv.tex/.cv.pdf, cover letters — every artifact
# is PII-derived) except its .gitkeep, plus the atomic-write .tmp/.bak/.sqlite data
# artifacts and the personal-term denylist itself (config/pii_terms.txt IS concentrated
# PII). The exempt patterns are END-anchored to the EXACT re-included filenames
# (README_SECRET.md is NOT exempt).
PII_PATH_RE='^(api/)?data/.*\.(csv|tmp|bak|sqlite|sqlite3|db)$|^(api/)?data/jobs/|^(api/)?data/patterns\.json$|^(api/)?data/cover_letter_samples/|^(api/)?resume/|^(api/)?applications/|^(api/)?config/(profile|memory|portals)\.ya?ml$|^(api/)?config/(cv_source|job_source)\.md$|^(api/)?config/pii_terms\.txt$|(^|/)\.demo/|(^|/)\.env($|\.)|\.env$'
# The example-csv exemption is anchored to WHERE shipped seeds live (direct children
# of data/) — an any-depth `.example.csv$` exemption would let the hook allow nested
# files that .gitignore's root-only `!data/*.example.csv` re-include still ignores.
PII_PATH_EXEMPT_RE='^data/[^/]*\.example\.csv$|^(api/)?data/jobs/\.gitkeep$|^(api/)?resume/README\.md$|^(api/)?applications/(README\.md|\.gitkeep)$|\.env\.example$'

# A real-looking email address (test fixtures + demo seeds use @example.com; the
# reserved RFC-2606 .example TLD and commit-authoring noreply@ are allow-listed).
PII_EMAIL_RE='\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'
PII_EMAIL_ALLOW_RE='@(example\.(com|org|net)|test\.com|localhost|anthropic\.com|sentry\.io|schema\.org|[a-z0-9-]+\.example)$'
PII_EMAIL_NOREPLY_RE='^(noreply|no-reply)@'

# Your personal-term denylist: real name, addresses, phone, handles — one per line.
# Gitignored AND path-blocked above; seed it from config/pii_terms.example.txt.
# Resolved via the shared git common dir so LINKED WORKTREES use the main checkout's
# denylist too (the untracked file exists only there — a relative path would make the
# layer a silent no-op in `git worktree add` checkouts). Falls back to the relative
# path when there is no git context (e.g. the commit-msg tests run without a repo).
_pii_common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
# Trust the output only when it is a single ABSOLUTE path: git < 2.31 doesn't know
# --path-format and echoes the flag back on stdout with exit 0, which would poison
# the path and silently disable the whole denylist layer. Junk starts with '-', so
# anything not starting with '/' falls back to the relative path (hooks run from the
# toplevel — main-checkout coverage survives; only worktree reach degrades).
case "$_pii_common" in
  /*) PII_TERMS_FILE="${_pii_common%/.git}/config/pii_terms.txt" ;;
  *)  PII_TERMS_FILE="config/pii_terms.txt" ;;
esac
# --separate-git-dir / submodule checkouts: the common dir doesn't end in /.git, so
# the strip above is a no-op and the derived path points inside the git dir. Hooks
# run from the toplevel — fall back to the cwd copy rather than silently scanning
# against a file that can never exist.
if [ ! -f "$PII_TERMS_FILE" ] && [ -f "config/pii_terms.txt" ]; then
  PII_TERMS_FILE="config/pii_terms.txt"
fi

# stdin: candidate paths (one per line) -> stdout: personal-data paths that must not ship.
# Lines starting with a literal `"` are git C-quoted names: quotepath=off does NOT stop
# quoting for double-quote/backslash/control characters, and the anchored regex can't
# see into the quoted form — fail CLOSED and flag the quoted line itself.
pii_offending_paths() {
  grep -E "${PII_PATH_RE}"'|^"' | grep -vE "$PII_PATH_EXEMPT_RE" || true
}

# stdin: text -> stdout: unique real-looking addresses after the allow-list filters.
pii_offending_emails() {
  grep -Eioh "$PII_EMAIL_RE" \
    | grep -viE "$PII_EMAIL_ALLOW_RE" \
    | grep -viE "$PII_EMAIL_NOREPLY_RE" \
    | sort -u || true
}

# stdin: text -> stdout: denylist terms found in it (case-insensitive, fixed-string).
# No-op when $PII_TERMS_FILE doesn't exist. Comment (#) / blank lines are skipped, as
# are terms under 4 chars — short terms false-positive everywhere; the example file
# tells you to keep terms distinctive.
pii_offending_terms() {
  # Drain stdin BEFORE any early return: bailing out with the pipe unread SIGPIPEs the
  # upstream writer once the diff outgrows the pipe buffer, and under `set -e -o pipefail`
  # that kills the whole hook (observed as exit 141 on real-sized commits).
  local text term
  text="$(cat)"
  [ -f "$PII_TERMS_FILE" ] || return 0
  [ -n "$text" ] || return 0
  while IFS= read -r term || [ -n "$term" ]; do
    term="${term#"${term%%[![:space:]]*}"}"
    term="${term%"${term##*[![:space:]]}"}"
    case "$term" in '' | \#*) continue ;; esac
    # Minimum length in BYTES, not characters: ${#term} counts characters under a UTF-8
    # locale, which silently skips 2-3 character CJK names — the documented use case.
    # Bytes keep the ASCII noise filter (>=4 chars) while a 2-char CJK name (6 bytes)
    # passes; the count is also locale-independent, unlike ${#term}.
    [ "$(printf %s "$term" | wc -c)" -ge 4 ] || continue
    # Herestring, NOT `printf | grep -q`: -q exits at the first hit, and the SIGPIPEd
    # printf would turn a MATCH into pipeline status 141 — a silent fail-open.
    if grep -qiF -- "$term" <<< "$text"; then
      printf '%s\n' "$term"
    fi
  done < "$PII_TERMS_FILE"
}
