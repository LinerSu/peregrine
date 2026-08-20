"""Regression tests for the personal-data / PII guards.

Guards under test (all sourcing hooks/pii-lib.sh — the single source of truth):
  * hooks/pre-commit    — path guard, email content scan, personal-term denylist
  * hooks/commit-msg    — the same email/denylist scans over the commit MESSAGE
  * scripts/ci_pii_guard.sh — the generic (path+email) backstop CI runs on the pushed diff
  * .gitignore parity   — every path the hook blocks must also be gitignored (and every
    shipped exemption must NOT be), so the two hand-mirrored layers can't drift apart.

The guards are FAIL-CLOSED backstops: their only job is to block a real CV/profile/job/email
from being committed (even via `git add -f`). A silent regression — a future edit that makes a
regex match nothing — would fail OPEN with no signal, the worst outcome. This pins the behavior
by running the ACTUAL hooks against throwaway git repos. Needs git+bash (present in CI; skipped
where absent, e.g. the api container has no git).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "hooks" / "pre-commit"
MSG_HOOK = REPO_ROOT / "hooks" / "commit-msg"
CI_GUARD = REPO_ROOT / "scripts" / "ci_pii_guard.sh"
INSTALL_HOOKS = REPO_ROOT / "scripts" / "install-hooks.sh"
GITIGNORE = REPO_ROOT / ".gitignore"

pytestmark = pytest.mark.skipif(
    not (HOOK.exists() and shutil.which("git") and shutil.which("bash")),
    reason="needs git + bash + the repo-root hooks/ (absent in the api container; present in CI)",
)

# Build "real" fixture emails by concatenation so THIS file holds no committable email literal —
# the very guard it tests would otherwise block this test file from being committed. The runtime
# VALUE is a full address (written to a temp file for the hook-under-test); the SOURCE is not.
_AT = "@"
_REAL = f"victim{_AT}gmail.com"               # a real-looking address the guard must catch
_REAL2 = f"recruiter{_AT}gmail.com"
_REAL_SFX = f"victim{_AT}gmail.com.example"   # real address merely suffixed with the .example TLD

# A fictional personal-term denylist (the real one is config/pii_terms.txt, gitignored).
# "ab" pins the <4-BYTES skip; the comment line pins comment handling; 王小明 (a stock
# placeholder name, 9 UTF-8 bytes) pins that short-in-CHARACTERS CJK names still match.
_TERMS = "# comment lines are skipped\nJane Petrova\njanepetrova\nab\n王小明\n"

# One case per DISTINCT branch of the path regex (a missing branch must fail a test, not pass
# silently) — plus the README-prefix collision and the api/ test-mount copies. Shared by the
# hook tests AND the .gitignore-parity tests below.
BLOCKED_PATHS = [
    "logs/agent.log",          # the keeper is exempt; the logs themselves never are
    "api/logs/.gitkeep",       # exemption is ROOT-anchored — nested copies stay blocked
    "api/.demo/.gitkeep",
    "data/jobs.csv",            # tracked jobs
    "data/applications.csv",    # tracked applications
    "data/jobs.csv.tmp",        # atomic-write temp (data_store.py) — same PII as the .csv
    "data/jobs.bak",            # backup
    "data/index.sqlite",        # derived index over the real corpus
    "data/index.sqlite3",       # (distinct extension literal)
    "data/index.db",            # (distinct extension literal)
    "data/patterns.json",       # learned application patterns
    "data/cover_letter_samples/style.txt",  # your own cover-letter style samples
    "data/backups/index.sqlite",  # NESTED db artifact — pins the data/**/* gitignore depth
    "data/exports/jobs.csv",      # NESTED csv — same depth-parity pin
    "data/jobs/2026-001.md",    # a posting snapshot (md)
    "data/jobs/2026-001.json",  # a posting snapshot (json)
    "data/jobs/2026-001.cv.tex",   # tailored CV — full PII (was NOT gitignored before)
    "data/jobs/2026-001.cv.pdf",   # compiled tailored CV
    "api/data/applications.csv",   # the test-mount copy (api/ prefix)
    "api/config/profile.yml",      # test-mount copy of the parsed CV
    "api/config/pii_terms.txt",    # test-mount copy of the personal-term denylist
    "api/config/cv_source.md",     # test-mount copy of the raw CV text
    "api/resume/cv.pdf",           # test-mount copy of the résumé
    "data/exports/seed.example.csv",  # example exemption is anchored to data/ ROOT — a
                                      # nested one is NOT a shipped seed and stays blocked
    "config/profile.yml",       # parsed CV
    "config/profile.yaml",      # (the ya?ml variant)
    "config/memory.yml",        # agent memory
    "config/memory.yaml",       # (the ya?ml variant)
    "config/portals.yml",       # scan config
    "config/portals.yaml",      # (the ya?ml variant)
    "config/companies.yml",     # your company registry — reveals where you apply
    "config/companies.yaml",    # (the ya?ml variant)
    "config/cv_source.md",      # raw CV text
    "config/job_source.md",     # pasted posting text
    "config/pii_terms.txt",     # the personal-term denylist ITSELF (concentrated PII)
    "resume/cv.pdf",            # the résumé itself
    "resume/简历-CV.pdf",        # non-ASCII filename — pins the core.quotepath=off fix (git's
                                 # default C-quoting made the ^-anchored regex fail OPEN)
    "resume/README_SECRET.md",  # README-PREFIX collision — NOT the exempt resume/README.md
    "applications/2026-001/cover_letter.md",
    "applications/README_notes.md",  # README-PREFIX collision — NOT the exempt README.md
    ".demo/jobs.csv",           # a generated demo dataset (root)
    "src/.demo/snapshot.json",  # nested .demo (exercises the (^|/) alternative)
    "STATUS.md",                # runtime status page — carries real activity (chat
                                # excerpts, job events); legacy root location
    "api/STATUS.md",            # test-mount copy
    "logs/STATUS.md",           # current location (under the logs/ dir mount)
    "logs/agent.log",           # runtime activity log — same PII class
    ".env",                     # secrets
    ".env.local",               # secret variant (NOT caught by *.env)
    ".env.production",          # secret variant
    "deploy/prod.env",          # the `\.env$` SUFFIX branch — the three cases above all
                                # also match `(^|/)\.env($|\.)`, so only this pins it
    "data/jobs\\backup.csv",    # backslash in the name: git C-quotes it EVEN with
                                # quotepath=off — pins the fail-closed quoted-line rule
]

ALLOWED_PATHS = [
    "data/seed.example.csv",   # shipped demo seed
    "data/jobs/.gitkeep",      # the placeholder that keeps the (otherwise-blocked) dir tracked
    "resume/README.md",        # the exact re-included README
    "applications/README.md",
    "applications/.gitkeep",
    "logs/.gitkeep",           # tracked so docker doesn't create logs/ as root (fresh-clone boot)
    ".demo/.gitkeep",          # same, for the demo-persona mount
    ".env.example",
    "config/pii_terms.example.txt",  # the shipped denylist TEMPLATE (placeholder terms only)
    "config/companies.example.yml",  # the shipped registry TEMPLATE
    # Root-anchored: a same-named dir NESTED under source must NOT be blocked (the app has an
    # Applications page + resume features, so these are realistic future source paths).
    "web/src/applications/List.tsx",
    "web/src/resume/Card.tsx",
]


def _run(tmp_path: Path, files: dict[str, str],
         unstaged: dict[str, str] | None = None,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Stage `files` in a fresh git repo and run the real pre-commit hook against them.

    `unstaged` files (e.g. a planted config/pii_terms.txt) are written but NOT staged —
    the denylist must act on what it READS, not on being staged itself. `env` overlays
    the environment for the hook run (e.g. GIT_EXTERNAL_DIFF).
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    for rel, content in (unstaged or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)  # no .gitignore here -> plain add
    return subprocess.run(["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


@pytest.mark.parametrize("path", BLOCKED_PATHS)
def test_blocks_personal_data_paths(tmp_path, path):
    r = _run(tmp_path, {path: "company,position\nAcme,Eng\n"})
    assert r.returncode == 1, f"{path} should be blocked\n{r.stderr}"
    assert "personal-data" in r.stderr


@pytest.mark.parametrize("path", ALLOWED_PATHS)
def test_allows_shipped_examples_and_nested_source(tmp_path, path):
    r = _run(tmp_path, {path: "# safe to ship\n"})
    assert r.returncode == 0, f"{path} should be allowed\n{r.stderr}"


# --- .gitignore parity ----------------------------------------------------------------
# The hook regex and the personal-data block in .gitignore are hand-mirrored. The likely
# future failure is adding a new personal artifact type to ONE of them: the hook would
# still catch it (fail-closed) but `git add .` would stage it, or vice versa. Run the
# REAL .gitignore through `git check-ignore` for the same canonical path lists.

def _git_ignored(tmp_path: Path, path: str) -> bool:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    shutil.copyfile(GITIGNORE, tmp_path / ".gitignore")
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=tmp_path, capture_output=True)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


@pytest.mark.parametrize("path", BLOCKED_PATHS)
def test_gitignore_parity_blocked(tmp_path, path):
    assert _git_ignored(tmp_path, path), (
        f"{path}: the pre-commit hook blocks this but .gitignore does NOT ignore it — "
        "a plain `git add .` would stage it. Add the pattern to .gitignore."
    )


@pytest.mark.parametrize("path", ALLOWED_PATHS)
def test_gitignore_parity_allowed(tmp_path, path):
    assert not _git_ignored(tmp_path, path), (
        f"{path}: shipped/exempt in the hook but ignored by .gitignore — "
        "the two layers have drifted."
    )


# --- email content scan ---------------------------------------------------------------

def test_blocks_real_email_in_content(tmp_path):
    r = _run(tmp_path, {"docs/note.md": f"recruiter contact: {_REAL2}\n"})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()


def test_allows_placeholder_and_noreply_emails(tmp_path):
    # jane@example.com -> domain allow-list; noreply@acme.com -> the SEPARATE noreply filter (acme.com
    # is deliberately NOT allow-listed, so this case is load-bearing for that filter).
    r = _run(tmp_path, {"docs/note.md": "use jane@example.com or noreply@acme.com\n"})
    assert r.returncode == 0, r.stderr


def test_allows_reserved_example_tld_email(tmp_path):
    # a real reserved-TLD placeholder (RFC 2606) must be exempted — pins the .example allow branch.
    r = _run(tmp_path, {"docs/note.md": "ping ci@foo.example for the bot\n"})
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("content", [f"+{_REAL}\n", f"++ recruiter {_REAL}\n"])
def test_blocks_email_on_plus_leading_content_lines(tmp_path, content):
    # content lines starting with '+'/'++' render as '++…'/'+++…' in the diff; both must be scanned
    # (only the genuine '+++ b/file' / '+++ /dev/null' diff header is skipped).
    r = _run(tmp_path, {"docs/snippet.md": content})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()


def test_example_allowlist_is_label_anchored(tmp_path):
    # a real address merely SUFFIXED with .example must not be waved through by the .example exempt.
    r = _run(tmp_path, {"docs/note.md": f"leaked: {_REAL_SFX}\n"})
    assert r.returncode == 1, r.stderr


def test_blocks_a_personal_file_staged_via_rename(tmp_path):
    # ACMR: a file moved INTO a personal-data path (git status R) must still be caught.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    (tmp_path / "seed.csv").write_text("company,position\nAcme,Eng\n")
    subprocess.run(["git", "add", "seed.csv"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed", "--no-verify"], cwd=tmp_path, check=True)
    (tmp_path / "config").mkdir()
    subprocess.run(["git", "mv", "seed.csv", "config/profile.yml"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert "personal-data" in r.stderr


def test_allows_a_clean_source_file(tmp_path):
    r = _run(tmp_path, {"web/src/x.ts": "export const x = 1;\n"})
    assert r.returncode == 0, r.stderr


def test_blocks_email_in_staged_filename(tmp_path):
    # an email-shaped FILENAME (saved correspondence, exported .eml) leaks exactly
    # like content — the email scan must see staged paths, not just added lines.
    r = _run(tmp_path, {f"docs/contact-{_REAL2}.md": "clean content\n"})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()


def test_email_scan_is_case_insensitive(tmp_path):
    # dropping the -i flags would fail open on shouty or mixed-case addresses.
    r = _run(tmp_path, {"docs/note.md": f"CONTACT: VICTIM{_AT}GMAIL.COM\n"})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()


def test_email_scan_survives_external_diff_driver(tmp_path):
    # porcelain `git diff` honors GIT_EXTERNAL_DIFF / diff.external (difftastic/delta
    # setups): driver output has no ^+ lines, silently blanking the content scans.
    # --no-ext-diff must keep the real patch — else this fails OPEN with no signal.
    r = _run(tmp_path, {"docs/note.md": f"contact: {_REAL2}\n"},
             env={"GIT_EXTERNAL_DIFF": "/bin/true"})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()


def test_denylist_applies_in_linked_worktree(tmp_path):
    # the terms file is untracked and lives only in the MAIN checkout — resolved via
    # the shared git common dir, a linked worktree must still be covered (a relative
    # path would make the denylist a silent no-op there).
    main = tmp_path / "main"
    main.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=main, check=True)
    (main / "a.txt").write_text("x\n")
    subprocess.run(["git", "add", "a.txt"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-qm", "seed", "--no-verify"], cwd=main, check=True)
    (main / "config").mkdir()
    (main / "config" / "pii_terms.txt").write_text(_TERMS)
    wt = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "wtb"], cwd=main, check=True)
    (wt / "docs").mkdir()
    (wt / "docs" / "note.md").write_text("hello Jane Petrova\n")
    subprocess.run(["git", "add", "docs/note.md"], cwd=wt, check=True)
    r = subprocess.run(["bash", str(HOOK)], cwd=wt, capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert "personal term" in r.stderr


# --- personal-term denylist (config/pii_terms.txt) ------------------------------------

def test_denylist_blocks_term_in_added_content(tmp_path):
    r = _run(tmp_path, {"docs/note.md": "reach out to jane PETROVA about the role\n"},
             unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 1, r.stderr
    assert "personal term" in r.stderr


def test_denylist_blocks_term_in_staged_filename(tmp_path):
    # the term can leak via the PATH, not just file content (e.g. janepetrova_cv_notes.md).
    r = _run(tmp_path, {"docs/janepetrova_cv_notes.md": "clean content\n"},
             unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 1, r.stderr
    assert "personal term" in r.stderr


def test_denylist_skips_comments_and_short_terms(tmp_path):
    # "ab" (<4 bytes) and the "# comment…" line must NOT match, else everything false-positives.
    # The staged content contains the comment line's OWN text verbatim: if comment lines are
    # ever treated as terms, it substring-matches and this test fails (mutation-proof — a
    # content without '#' passed even with the comment-skip branch deleted).
    r = _run(tmp_path, {"docs/note.md": "ab initio # comment lines are skipped everywhere\n"},
             unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 0, r.stderr


def test_denylist_matches_short_cjk_name(tmp_path):
    # A 3-character CJK name is only 3 CHARACTERS but 9 bytes — the length floor must count
    # bytes, or the documented "name in Chinese" use case silently gets no protection.
    r = _run(tmp_path, {"docs/note.md": "intro call with 王小明 on Friday\n"},
             unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 1, r.stderr
    assert "personal term" in r.stderr


def test_denylist_absent_file_is_a_noop(tmp_path):
    r = _run(tmp_path, {"docs/note.md": "mentions Jane Petrova freely\n"})
    assert r.returncode == 0, r.stderr


# Both large-diff cases pin the SIGPIPE regression: a scanner that stops reading stdin
# early (or a `printf | grep -q` pipeline) works on toy diffs but dies — or silently
# fails OPEN — once the diff outgrows the ~64KB pipe buffer.

def test_denylist_survives_large_diff_without_terms_file(tmp_path):
    r = _run(tmp_path, {"docs/big.md": "filler line, nothing personal\n" * 20000})
    assert r.returncode == 0, r.stderr


def test_denylist_catches_early_term_in_large_diff(tmp_path):
    big = "meet jane PETROVA today\n" + "filler line\n" * 20000
    r = _run(tmp_path, {"docs/big.md": big}, unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 1, r.stderr
    assert "personal term" in r.stderr


# --- commit-msg hook ------------------------------------------------------------------

def _run_msg(tmp_path: Path, message: str, terms: str | None = None) -> subprocess.CompletedProcess:
    """Run the real commit-msg hook against a message file (no git repo needed)."""
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(message)
    if terms is not None:
        (tmp_path / "config").mkdir(exist_ok=True)
        (tmp_path / "config" / "pii_terms.txt").write_text(terms)
    return subprocess.run(["bash", str(MSG_HOOK), str(msg)],
                          cwd=tmp_path, capture_output=True, text=True)


def test_commit_msg_accepts_conventional_subject(tmp_path):
    r = _run_msg(tmp_path, "feat(web): add applications tracker\n")
    assert r.returncode == 0, r.stderr


def test_commit_msg_still_rejects_bad_subject(tmp_path):
    r = _run_msg(tmp_path, "added some stuff\n")
    assert r.returncode == 1
    assert "subject" in r.stderr


def test_commit_msg_blocks_real_email(tmp_path):
    r = _run_msg(tmp_path, f"fix: update contact to {_REAL}\n")
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_allows_coauthor_trailer(tmp_path):
    # the standard commit-authoring trailer must never trip the scan.
    r = _run_msg(tmp_path, "chore: tidy\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    assert r.returncode == 0, r.stderr


def test_commit_msg_blocks_denylist_term(tmp_path):
    r = _run_msg(tmp_path, "fix: rename Jane Petrova fixtures\n", terms=_TERMS)
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_ignores_verbose_diff_below_scissors(tmp_path):
    # `git commit -v` appends the FULL staged diff below the scissors line; git strips it
    # before recording, so a real email there (e.g. a context line, or the deletion line of
    # the very scrub commit that REMOVES a leak) must not block the commit.
    scissors = "# ------------------------ >8 ------------------------\n"
    msg = ("fix: scrub the leaked address\n\n"
           "# Please enter the commit message for your changes. Lines starting\n"
           "# with '#' will be ignored, and an empty message aborts the commit.\n"
           f"{scissors}"
           f"diff --git a/docs/note.md b/docs/note.md\n-contact: {_REAL}\n+contact: TBD\n")
    r = _run_msg(tmp_path, msg, terms=_TERMS)
    assert r.returncode == 0, r.stderr


def test_commit_msg_ignores_comment_template_lines(tmp_path):
    # The '#' status template (branch info, untracked-file listings) is stripped by git's
    # cleanup — a denylist term in an untracked FILENAME must not block an unrelated commit.
    msg = ("docs: tidy readme\n\n"
           "# Please enter the commit message for your changes. Lines starting\n"
           "# Untracked files:\n#   notes/janepetrova_call.md\n"
           f"# Author: someone <{_REAL2}>\n")
    r = _run_msg(tmp_path, msg, terms=_TERMS)
    assert r.returncode == 0, r.stderr


def test_commit_msg_blocks_pii_in_editor_flow_body(tmp_path):
    # the strip branch must remove ONLY comment/scissors content — PII in the kept
    # body must still block, or an over-aggressive sed edit fails open undetected.
    msg = (f"fix: contact {_REAL} about the role\n\n"
           "# Please enter the commit message for your changes. Lines starting\n"
           "# with '#' will be ignored, and an empty message aborts the commit.\n")
    r = _run_msg(tmp_path, msg)
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_scissors_marker_alone_marks_editor_flow(tmp_path):
    # localized git translates the '# Please enter' prose but NOT the 24-dash scissors
    # marker — the marker alone must select the strip branch, or every non-English
    # `git commit -v` scrub commit is falsely blocked.
    scissors = "# " + "-" * 24 + " >8 " + "-" * 24 + "\n"
    msg = (f"fix: scrub the leaked address\n\n{scissors}"
           f"diff --git a/x b/x\n-old: {_REAL}\n+new: TBD\n")
    r = _run_msg(tmp_path, msg, terms=_TERMS)
    assert r.returncode == 0, r.stderr


def test_commit_msg_editor_flow_scans_below_short_lookalike(tmp_path):
    # in the editor flow, git only cuts at its REAL 24-dash scissors line; a pasted
    # short lookalike is a plain comment and the recorded line after it must still be
    # scanned — the truncation floor has to match the 20-dash detection floor.
    msg = ("fix: tidy\n\n"
           "# Please enter the commit message for your changes. Lines starting\n"
           "# -- >8 --\n"
           f"see {_REAL}\n")
    r = _run_msg(tmp_path, msg)
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_scans_hash_lines_of_dash_m_messages(tmp_path):
    # `git commit -m` defaults to cleanup=whitespace: '#' lines ARE recorded. Without
    # git's editor-template marker the hook must scan them raw — stripping would fail
    # OPEN on e.g. a pasted transcript line.
    r = _run_msg(tmp_path, f"fix: tidy\n\n# ping {_REAL} for details\n")
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_scans_below_pasted_scissors_lookalike(tmp_path):
    # outside the editor/-v flow git records content below a scissors-looking line —
    # the truncation must not fire for -m/-F style messages.
    r = _run_msg(tmp_path, f"fix: tidy\n\n# -- >8 --\nsee {_REAL2}\n")
    assert r.returncode == 1
    assert "personal data" in r.stderr


def test_commit_msg_scans_merge_messages_too(tmp_path):
    # merges bypass the FORMAT check but must still be PII-scanned.
    r = _run_msg(tmp_path, f"Merge branch 'x'\n\nnotes: ping {_REAL2}\n")
    assert r.returncode == 1
    assert "personal data" in r.stderr
    r = _run_msg(tmp_path, "Merge branch 'x'\n")
    assert r.returncode == 0, r.stderr


# --- CI backstop (scripts/ci_pii_guard.sh) --------------------------------------------

def _seeded_repo(tmp_path: Path) -> str:
    """Fresh repo with one clean commit; returns that base sha."""
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("clean\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed", "--no-verify"], cwd=tmp_path, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "change", "--no-verify"], cwd=tmp_path, check=True)


def test_ci_guard_blocks_personal_path_in_diff(tmp_path):
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "config/profile.yml", "name: someone\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr
    # a résumé filename can itself carry a real name — Actions logs must only ever see
    # the directory prefix, mirroring the email redaction.
    assert "profile.yml" not in r.stderr, "verbatim basename leaked into CI output"
    assert "config/" in r.stderr


def test_ci_guard_blocks_nonascii_path(tmp_path):
    # pins the CI guard's OWN -c core.quotepath=off (independent of pre-commit's):
    # without it, git C-quotes the path and the ^-anchored regex fails OPEN.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "resume/简历-CV.pdf", "cv body\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr


def test_ci_guard_catches_pii_added_then_removed_in_range(tmp_path):
    # the fixup-on-top pattern: PII committed, then a later commit removes it. The
    # ENDPOINT diff is clean, but the bytes are pushed (reachable via refs/pull
    # forever) — the per-commit scan must still fail the run.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "config/profile.yml", "name: someone\n")
    (tmp_path / "config/profile.yml").unlink()
    subprocess.run(["git", "rm", "-q", "config/profile.yml"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "remove", "--no-verify"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr


def _evil_merge_repo(tmp_path: Path) -> str:
    """History whose ONLY PII is introduced in a merge conflict resolution."""
    base = _seeded_repo(tmp_path)
    default = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path,
                             check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "-qb", "side"], cwd=tmp_path, check=True)
    _commit(tmp_path, "docs/x.md", "side version\n")
    subprocess.run(["git", "checkout", "-q", default], cwd=tmp_path, check=True)
    _commit(tmp_path, "docs/x.md", "main version\n")
    subprocess.run(["git", "merge", "side"], cwd=tmp_path, capture_output=True)  # conflicts
    (tmp_path / "docs" / "x.md").write_text(f"resolved: ping {_REAL}\n")
    subprocess.run(["git", "add", "docs/x.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--no-verify", "-m", "fix: merge side"],
                   cwd=tmp_path, check=True)
    return base


def test_ci_guard_catches_pii_in_merge_conflict_resolution(tmp_path):
    # `git log -p` skips merge diffs, so PII introduced ONLY in an evil-merge conflict
    # resolution is invisible to the per-commit scan — the endpoint-diff belt must
    # catch it (this is the case the belt exists for).
    base = _evil_merge_repo(tmp_path)
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "email" in r.stderr.lower()


def test_ci_guard_catches_evil_merge_even_without_usable_base(tmp_path):
    # when base AND baseline are both unusable the belt must fall back to the EMPTY
    # TREE, not vanish — `git log -p` alone would greenlight the merge resolution.
    _evil_merge_repo(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "PII_GUARD_BASELINE"}
    r = subprocess.run(["bash", str(CI_GUARD), _ZEROS], cwd=tmp_path,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "email" in r.stderr.lower()


def test_ci_guard_merge_base_normalizes_stale_pr_base(tmp_path):
    # a PR base sha that is main's ADVANCED tip (not an ancestor of the branch head)
    # must be normalized via merge-base — otherwise content main scrubbed since the
    # fork reads as branch ADDITIONS: a guaranteed false-red on any non-rebased PR.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    _commit(tmp_path, "docs/x.md", f"ping {_REAL}\n")          # fork point (pre-base history)
    default = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=tmp_path,
                             check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "-qb", "feat"], cwd=tmp_path, check=True)
    _commit(tmp_path, "docs/clean.md", "clean\n")
    subprocess.run(["git", "checkout", "-q", default], cwd=tmp_path, check=True)
    _commit(tmp_path, "docs/x.md", "scrubbed\n")               # main advances past the fork
    stale_base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                                capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "feat"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash", str(CI_GUARD), stale_base], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ci_guard_redaction_never_prints_nonstructural_first_component(tmp_path):
    # the any-depth branches (.demo/, *.env) can put a USER-NAMED directory first —
    # only the known structural roots may survive into the Actions log.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "JaneDoe-workspace/.demo/jobs.csv", "x\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "JaneDoe" not in r.stderr, "user-named first component leaked into CI output"


def test_pinned_baseline_sha_resolves():
    # PII_GUARD_BASELINE in ci.yml must stay resolvable: after any main-history
    # rewrite it silently stops bounding the fallback (guaranteed-red full scans).
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    m = re.search(r"PII_GUARD_BASELINE:\s*([0-9a-f]{40})", ci)
    assert m, "PII_GUARD_BASELINE env missing from ci.yml"
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=REPO_ROOT,
                             capture_output=True, text=True).stdout.strip()
    if shallow == "true":
        pytest.skip("shallow checkout cannot resolve historic shas")
    r = subprocess.run(["git", "cat-file", "-e", f"{m.group(1)}^{{commit}}"], cwd=REPO_ROOT)
    assert r.returncode == 0, "baseline sha no longer resolves — update ci.yml after the history rewrite"


def test_ci_guard_baseline_bounds_unusable_base_fallback(tmp_path):
    # this repo's permanent early history holds since-removed demo files under
    # personal-data paths: an UNBOUNDED full-history fallback is guaranteed-red
    # forever (worst on the run right after a leak-scrub force-push). The baseline
    # env caps the fallback at a known-clean floor; without it, full history scans.
    _seeded_repo(tmp_path)
    _commit(tmp_path, "config/profile.yml", "legacy demo\n")
    subprocess.run(["git", "rm", "-q", "config/profile.yml"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "cleanup", "--no-verify"], cwd=tmp_path, check=True)
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                              capture_output=True, text=True).stdout.strip()
    _commit(tmp_path, "docs/clean.md", "clean\n")
    r = subprocess.run(["bash", str(CI_GUARD), _ZEROS], cwd=tmp_path, capture_output=True,
                       text=True, env={**os.environ, "PII_GUARD_BASELINE": baseline})
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run(["bash", str(CI_GUARD), _ZEROS], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, "unbounded fallback must still scan full history"


def test_ci_guard_email_redaction_hides_org_domain(tmp_path):
    # masking only the first domain label would print `j***@m***.acme-corp.com` — the
    # registrable org domain identifies the person; everything after the first domain
    # character must be masked.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "docs/note.md", f"ping jsmith{_AT}mail.acme-corp.com\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "acme-corp" not in r.stderr, "org domain leaked into CI output"
    assert "j***@m***" in r.stderr


def test_ci_guard_path_redaction_hides_subdirectories(tmp_path):
    # user-named SUBDIRECTORIES under resume/ or applications/ carry names just like
    # basenames — only the first, repo-structural component may survive into the log.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "resume/JanePetrova_2026/cv.pdf", "cv\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "JanePetrova" not in r.stderr, "user-named directory leaked into CI output"
    assert "resume/<redacted>" in r.stderr


def test_ci_guard_scans_commit_messages_in_range(tmp_path):
    # the commit-msg hook is bypassable (--no-verify / uninstalled hooks); a leaked
    # address in a MESSAGE lands on GitHub like file content and must fail CI.
    base = _seeded_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/clean.md").write_text("clean\n")
    subprocess.run(["git", "add", "docs/clean.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--no-verify", "-m", f"fix: ping {_REAL2}"],
                   cwd=tmp_path, check=True)
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "message" in r.stderr.lower()
    assert _REAL2 not in r.stderr, "verbatim email leaked into CI output"


def test_ci_guard_blocks_email_in_diff(tmp_path):
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "docs/note.md", f"ping {_REAL2}\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "email" in r.stderr.lower()
    # Actions logs persist beyond a branch scrub — the guard must print a REDACTED form,
    # never the verbatim address (that would mint a second, harder-to-clean copy of the PII).
    assert _REAL2 not in r.stderr, "verbatim email leaked into CI output"
    assert "r***@g***" in r.stderr


def test_ci_guard_passes_clean_diff(tmp_path):
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "docs/note.md", "all placeholders, e.g. jane@example.com\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


_ZEROS = "0" * 40  # what GitHub sends as `before` on branch creation / force-push


@pytest.mark.parametrize("args", [[], [_ZEROS]])
def test_ci_guard_single_commit_falls_back_to_empty_tree(tmp_path, args):
    # no usable base sha (first push of a one-commit repo): scan everything, still catch it.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    _commit(tmp_path, "config/profile.yml", "name: someone\n")
    r = subprocess.run(["bash", str(CI_GUARD), *args], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr


def test_ci_guard_unusable_base_scans_whole_history_not_just_head(tmp_path):
    # FAIL-CLOSED pin: with an unusable base and a MULTI-commit history, PII buried one
    # commit below a clean HEAD must still be caught. (A HEAD~1 fallback scans only the
    # last commit and certified this exact case as clean.)
    _seeded_repo(tmp_path)
    _commit(tmp_path, "config/profile.yml", "name: someone\n")
    _commit(tmp_path, "docs/clean.md", "nothing personal here\n")
    r = subprocess.run(["bash", str(CI_GUARD), _ZEROS], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr


# --- hook installer (scripts/install-hooks.sh) ----------------------------------------

def test_install_hooks_refuses_nested_copy(tmp_path):
    # a tarball copy nested inside ANOTHER repo's work tree must be refused — running
    # would rewrite that unrelated repo's core.hooksPath (silently disabling its own
    # hooks) while claiming these guards were installed.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    nested = tmp_path / "nested-copy"
    (nested / "scripts").mkdir(parents=True)
    shutil.copy(INSTALL_HOOKS, nested / "scripts" / "install-hooks.sh")
    shutil.copytree(REPO_ROOT / "hooks", nested / "hooks")
    r = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=nested,
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "refusing" in r.stderr
    hp = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path,
                        capture_output=True, text=True)
    assert hp.stdout.strip() != "hooks", "enclosing repo's hooksPath was rewritten"


def test_install_hooks_installs_in_own_checkout(tmp_path):
    # happy path, including a checkout reached via its physical location.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(INSTALL_HOOKS, tmp_path / "scripts" / "install-hooks.sh")
    shutil.copytree(REPO_ROOT / "hooks", tmp_path / "hooks")
    r = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    hp = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path,
                        capture_output=True, text=True)
    assert hp.stdout.strip() == "hooks"


# --- launch-time self-heal (scripts/ensure-hooks.sh, called by start.sh) --------------

ENSURE_HOOKS = REPO_ROOT / "scripts" / "ensure-hooks.sh"


def _project_copy(dst: Path) -> None:
    (dst / "scripts").mkdir(parents=True)
    shutil.copy(INSTALL_HOOKS, dst / "scripts" / "install-hooks.sh")
    shutil.copy(ENSURE_HOOKS, dst / "scripts" / "ensure-hooks.sh")
    shutil.copytree(REPO_ROOT / "hooks", dst / "hooks")


def test_ensure_hooks_installs_in_own_fresh_clone(tmp_path):
    # the fail-open direction: an inverted gate would silently skip installation on a
    # fresh clone — the exact 'commit with NO guard' scenario the self-heal closes.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _project_copy(tmp_path)
    r = subprocess.run(["bash", "scripts/ensure-hooks.sh"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    hp = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path,
                        capture_output=True, text=True)
    assert hp.stdout.strip() == "hooks"


def test_ensure_hooks_warns_but_never_fails_launch_in_nested_copy(tmp_path):
    # nested tarball copy: must warn, exit 0 (the launch continues), and leave the
    # enclosing repo's hook config untouched.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    nested = tmp_path / "nested-copy"
    _project_copy(nested)
    r = subprocess.run(["bash", "scripts/ensure-hooks.sh"], cwd=nested,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "NOT installed" in r.stderr
    hp = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path,
                        capture_output=True, text=True)
    assert hp.stdout.strip() != "hooks", "enclosing repo's hooksPath was rewritten"


def test_ci_guard_blocks_email_in_committed_filename(tmp_path):
    # filenames feed the email scan in CI too, and stay redacted in the output.
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, f"docs/contact-{_REAL2}.md", "clean content\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "email" in r.stderr.lower()
    assert _REAL2 not in r.stderr, "verbatim email leaked into CI output"


# --- provider keys ------------------------------------------------------------------
# Push protection covers this on a public repo, but not on a private one and not before
# the commit exists. A leaked key is worse than a leaked name: it spends money.

SECRET_LINES = [
    "ANTHROPIC_API_KEY=sk-ant-api03-" + "A" * 32,
    "openai = 'sk-" + "B" * 40 + "'",
    "aws_access_key_id = " + "AKIA" + "IOSFODNN7EXAMPLE",  # split: the hook scans THIS file too
    "token: ghp_" + "C" * 36,
    "slack = xoxb-" + "1" * 20,
    "-----BEGIN " + "RSA PRIVATE KEY-----",
]

PLACEHOLDER_LINES = [
    "ANTHROPIC_API_KEY=",                 # the shape .env.example ships
    "ANTHROPIC_API_KEY=YOUR_KEY_HERE",
    'key = "sk-ant-..."',                 # docs illustrating the format
    "# set OPENAI_API_KEY in .env",
]


@pytest.mark.parametrize("line", SECRET_LINES)
def test_blocks_provider_keys(tmp_path, line):
    r = _run(tmp_path, {"api/app/settings.py": f"KEY = \"{line}\"\n"})
    assert r.returncode == 1, f"{line[:16]}… should be blocked\n{r.stderr}"
    assert "API key" in r.stderr


@pytest.mark.parametrize("line", PLACEHOLDER_LINES)
def test_allows_key_placeholders(tmp_path, line):
    r = _run(tmp_path, {"docs/config.md": line + "\n"})
    assert r.returncode == 0, f"{line} should pass\n{r.stderr}"


def test_reported_keys_are_truncated(tmp_path):
    # The report itself must not become the leak: terminal scrollback and CI logs keep it.
    secret = "sk-ant-api03-" + "Z" * 40
    r = _run(tmp_path, {"api/app/settings.py": f"KEY = \"{secret}\"\n"})
    assert r.returncode == 1
    assert secret not in r.stderr
    assert "(redacted)" in r.stderr



def test_commit_msg_allows_dependabot_signoff_trailer(tmp_path):
    # Dependabot signs off as support@github.com on EVERY bump. The PII guard is a
    # required check, so matching that trailer made every dependency-bump PR
    # permanently unmergeable — pins the bot-address exemption.
    r = _run_msg(
        tmp_path,
        "chore(deps): bump pypdf from 6.14.2 to 6.15.0 in /api\n\n"
        "Signed-off-by: dependabot[bot] <support@github.com>\n",
    )
    assert r.returncode == 0, r.stderr


def test_allows_github_privacy_author_address(tmp_path):
    # 12345+user@users.noreply.github.com is the address GitHub hands out precisely SO
    # a real one never appears — flagging it as personal data is exactly backwards.
    r = _run(tmp_path, {"docs/note.md": "author: 12345+octocat@users.noreply.github.com\n"})
    assert r.returncode == 0, r.stderr


def test_blocks_a_real_person_at_the_github_domain(tmp_path):
    # The exemption is address-specific, not domain-wide: allowing all of @github.com
    # would hide a real employee's address behind the bot rule.
    r = _run(tmp_path, {"docs/note.md": f"reviewer: jane.doe{_AT}github.com\n"})
    assert r.returncode == 1, r.stderr
    assert "email" in r.stderr.lower()
