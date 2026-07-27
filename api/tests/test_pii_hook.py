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

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "hooks" / "pre-commit"
MSG_HOOK = REPO_ROOT / "hooks" / "commit-msg"
CI_GUARD = REPO_ROOT / "scripts" / "ci_pii_guard.sh"
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
# "ab" pins the <4-chars skip; the comment line pins comment handling.
_TERMS = "# comment lines are skipped\nJane Petrova\njanepetrova\nab\n"

# One case per DISTINCT branch of the path regex (a missing branch must fail a test, not pass
# silently) — plus the README-prefix collision and the api/ test-mount copies. Shared by the
# hook tests AND the .gitignore-parity tests below.
BLOCKED_PATHS = [
    "data/jobs.csv",            # tracked jobs
    "data/applications.csv",    # tracked applications
    "data/jobs.csv.tmp",        # atomic-write temp (data_store.py) — same PII as the .csv
    "data/jobs.bak",            # backup
    "data/index.sqlite",        # derived index over the real corpus
    "data/index.sqlite3",       # (distinct extension literal)
    "data/index.db",            # (distinct extension literal)
    "data/patterns.json",       # learned application patterns
    "data/cover_letter_samples/style.txt",  # your own cover-letter style samples
    "data/jobs/2026-001.md",    # a posting snapshot (md)
    "data/jobs/2026-001.json",  # a posting snapshot (json)
    "data/jobs/2026-001.cv.tex",   # tailored CV — full PII (was NOT gitignored before)
    "data/jobs/2026-001.cv.pdf",   # compiled tailored CV
    "api/data/applications.csv",   # the test-mount copy (api/ prefix)
    "config/profile.yml",       # parsed CV
    "config/profile.yaml",      # (the ya?ml variant)
    "config/memory.yml",        # agent memory
    "config/portals.yml",       # scan config
    "config/cv_source.md",      # raw CV text
    "config/job_source.md",     # pasted posting text
    "config/pii_terms.txt",     # the personal-term denylist ITSELF (concentrated PII)
    "resume/cv.pdf",            # the résumé itself
    "resume/README_SECRET.md",  # README-PREFIX collision — NOT the exempt resume/README.md
    "applications/2026-001/cover_letter.md",
    "applications/README_notes.md",  # README-PREFIX collision — NOT the exempt README.md
    ".demo/jobs.csv",           # a generated demo dataset (root)
    "src/.demo/snapshot.json",  # nested .demo (exercises the (^|/) alternative)
    ".env",                     # secrets
    ".env.local",               # secret variant (NOT caught by *.env)
    ".env.production",          # secret variant
]

ALLOWED_PATHS = [
    "data/seed.example.csv",   # shipped demo seed
    "data/jobs/.gitkeep",      # the placeholder that keeps the (otherwise-blocked) dir tracked
    "resume/README.md",        # the exact re-included README
    "applications/README.md",
    "applications/.gitkeep",
    ".env.example",
    "config/pii_terms.example.txt",  # the shipped denylist TEMPLATE (placeholder terms only)
    # Root-anchored: a same-named dir NESTED under source must NOT be blocked (the app has an
    # Applications page + resume features, so these are realistic future source paths).
    "web/src/applications/List.tsx",
    "web/src/resume/Card.tsx",
]


def _run(tmp_path: Path, files: dict[str, str],
         unstaged: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Stage `files` in a fresh git repo and run the real pre-commit hook against them.

    `unstaged` files (e.g. a planted config/pii_terms.txt) are written but NOT staged —
    the denylist must act on what it READS, not on being staged itself.
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
    return subprocess.run(["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True)


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
    # "ab" (<4 chars) and the "# comment…" line must NOT match, else everything false-positives.
    r = _run(tmp_path, {"docs/note.md": "ab initio comment lines everywhere\n"},
             unstaged={"config/pii_terms.txt": _TERMS})
    assert r.returncode == 0, r.stderr


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


def test_ci_guard_blocks_email_in_diff(tmp_path):
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "docs/note.md", f"ping {_REAL2}\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "email" in r.stderr.lower()


def test_ci_guard_passes_clean_diff(tmp_path):
    base = _seeded_repo(tmp_path)
    _commit(tmp_path, "docs/note.md", "all placeholders, e.g. jane@example.com\n")
    r = subprocess.run(["bash", str(CI_GUARD), base], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ci_guard_single_commit_falls_back_to_empty_tree(tmp_path):
    # no usable base sha (first push of a one-commit repo): scan everything, still catch it.
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=tmp_path, check=True)
    _commit(tmp_path, "config/profile.yml", "name: someone\n")
    r = subprocess.run(["bash", str(CI_GUARD)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "personal-data" in r.stderr
