"""The example CSVs must stay HEADER-ONLY — this is load-bearing, not cosmetic.

ensure_dirs() copies them to the live files on a fresh clone. A seeded sample job
would (a) carry a pre-baked fit score with no profile to explain it and (b) make
jobs.length > 0, which suppresses the web's auto-opened "Get started" onboarding
(App.tsx) — the guided flow, not a mystery sample row, must greet a new user.
See the comment in api/app/config.py::ensure_dirs.
"""
from pathlib import Path

import pytest

REPO_DATA = Path(__file__).resolve().parents[2] / "data"

pytestmark = pytest.mark.skipif(
    not REPO_DATA.is_dir(),
    reason="needs the repo-root data/ dir (absent when ./api is mounted as /app)",
)


@pytest.mark.parametrize("name", ["jobs.example.csv", "applications.example.csv"])
def test_example_csv_is_header_only(name):
    lines = [l for l in (REPO_DATA / name).read_text().splitlines() if l.strip()]
    assert len(lines) == 1, (
        f"{name} must contain ONLY the header row — a seeded sample row suppresses "
        "the first-run onboarding and ships an unexplained fit score"
    )
