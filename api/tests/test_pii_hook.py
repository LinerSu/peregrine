"""Regression test for the personal-data / PII pre-commit guard (hooks/pre-commit, section 3).

The guard is a FAIL-CLOSED backstop: its only job is to block a real CV/profile/job/email from
being committed (even via `git add -f`). A silent regression — a future edit that makes a regex
match nothing — would fail OPEN with no signal, the worst outcome. This pins the behavior by
running the ACTUAL hook against a throwaway git repo. Needs git+bash (present in CI; skipped where
absent, e.g. the api container has no git).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "pre-commit"

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


def _run(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess:
    """Stage `files` in a fresh git repo and run the real pre-commit hook against them."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)  # no .gitignore here -> plain add
    return subprocess.run(["bash", str(HOOK)], cwd=tmp_path, capture_output=True, text=True)


# One case per DISTINCT branch of the path regex (a missing branch must fail a test, not pass
# silently) — plus the README-prefix collision and the api/ test-mount copies.
@pytest.mark.parametrize(
    "path",
    [
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
        "resume/cv.pdf",            # the résumé itself
        "resume/README_SECRET.md",  # README-PREFIX collision — NOT the exempt resume/README.md
        "applications/2026-001/cover_letter.md",
        "applications/README_notes.md",  # README-PREFIX collision — NOT the exempt README.md
        ".demo/jobs.csv",           # a generated demo dataset (root)
        "src/.demo/snapshot.json",  # nested .demo (exercises the (^|/) alternative)
        ".env",                     # secrets
        ".env.local",               # secret variant (NOT caught by *.env)
        ".env.production",          # secret variant
    ],
)
def test_blocks_personal_data_paths(tmp_path, path):
    r = _run(tmp_path, {path: "company,position\nAcme,Eng\n"})
    assert r.returncode == 1, f"{path} should be blocked\n{r.stderr}"
    assert "personal-data" in r.stderr


@pytest.mark.parametrize(
    "path",
    [
        "data/seed.example.csv",   # shipped demo seed
        "data/jobs/.gitkeep",      # the placeholder that keeps the (otherwise-blocked) dir tracked
        "resume/README.md",        # the exact re-included README
        "applications/README.md",
        "applications/.gitkeep",
        ".env.example",
        # Root-anchored: a same-named dir NESTED under source must NOT be blocked (the app has an
        # Applications page + resume features, so these are realistic future source paths).
        "web/src/applications/List.tsx",
        "web/src/resume/Card.tsx",
    ],
)
def test_allows_shipped_examples_and_nested_source(tmp_path, path):
    r = _run(tmp_path, {path: "# safe to ship\n"})
    assert r.returncode == 0, f"{path} should be allowed\n{r.stderr}"


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
