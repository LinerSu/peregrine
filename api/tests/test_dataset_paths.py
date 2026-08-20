"""A dataset switch must move the local CLI too, not just the API.

`PEREGRINE_DATASET=<persona>` re-points `config.DATA_DIR` / `CONFIG_DIR` under
`.demo/<persona>/`, and `scripts/dataset.sh` presents that as "your real data is left
untouched". That holds only for readers that go through `app.config` — the API. Internal
mode puts a local CLI in the repo root with a shell, and if it resolves `data/` itself it
keeps reading and writing the user's REAL files while the app serves the demo ones: reads
analyse the wrong posting, writes destroy exactly what the switch promised to protect.

Design rules pinned here:
  * `/api/health` publishes where the data actually lives, so a CLI can join against it
    instead of assuming — the ONLY signal it has, since nothing else crosses that gap;
  * the published paths are REPO-RELATIVE. The API resolves ROOT to `/app` inside its
    container while the CLI resolves it to the repo on the host, so an absolute path
    would be actively misleading on one side of the pair;
  * every path in the Internal-mode router goes through that resolution. This is the
    half that rots: the router is prose, so a new capability can hardcode `data/…` and
    nothing else would notice.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / ".claude" / "skills" / "peregrine" / "SKILL.md"
API_DIR = REPO_ROOT / "api"

_PUBLISHED = ("data", "config", "applications", "resume")


def test_health_publishes_where_the_data_actually_lives():
    paths = TestClient(app).get("/api/health").json()["paths"]
    assert set(paths) == set(_PUBLISHED)
    # Relative to the repo root: an absolute path would name the API's container root,
    # which does not exist on the host where the CLI runs.
    for name, value in paths.items():
        assert not Path(value).is_absolute(), f"{name} is absolute: {value}"
        assert value == Path(getattr(config, f"{name.upper()}_DIR")).relative_to(config.ROOT).as_posix()


def test_a_demo_dataset_moves_every_published_path(tmp_path):
    """The whole point: with a dataset active, nothing published still points at `data/`."""
    r = subprocess.run(
        [sys.executable, "-c",
         "from app.config import repo_relative_dirs; import json; print(json.dumps(repo_relative_dirs()))"],
        cwd=API_DIR, capture_output=True, text=True, timeout=180,
        env={"PATH": "/usr/bin:/bin", "APP_ROOT": str(tmp_path),
             "PEREGRINE_DATASET": "ai-engineer"},
    )
    assert r.returncode == 0, r.stderr
    paths = json.loads(r.stdout)
    assert set(paths) == set(_PUBLISHED)
    for name, value in paths.items():
        assert value.startswith(".demo/ai-engineer/"), f"{name} escaped the dataset: {value}"


needs_router = pytest.mark.skipif(
    not ROUTER.exists(),
    reason="needs the repo-root .claude/ tree (absent when ./api is mounted as /app)",
)


@needs_router
def test_the_router_tells_the_cli_to_resolve_paths_before_reading_anything():
    text = ROUTER.read_text(encoding="utf-8")
    assert "/api/health" in text
    assert "paths" in text
    # The instruction must come before the first capability, or a CLI that stops reading
    # once it has matched the user's phrase never sees it.
    assert text.index("/api/health") < text.index('## "')


@needs_router
def test_the_router_never_hardcodes_the_live_data_directory():
    """A capability that writes `data/jobs/<id>.md` instead of `<data>/jobs/<id>.md`
    silently reads the real files under a demo dataset. Prose can't be type-checked, so
    this is the only thing standing between that mistake and the user's data."""
    text = ROUTER.read_text(encoding="utf-8")
    # Drop the section that explains the rule — it names the literal paths on purpose.
    start = text.index("## First, resolve where the data lives")
    body = text[:start] + text[text.index("\n## ", start):]
    stray = re.findall(r"`(?:data|config)/[^`]*`", body)
    assert not stray, f"router hardcodes live paths instead of the resolved <data>/<config>: {stray}"
