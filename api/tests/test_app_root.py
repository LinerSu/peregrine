"""A test run must not write into the working tree.

`app/config.py` resolves `ROOT` at import time and `app/main.py` calls `ensure_dirs()`
at import time, so importing the app is enough to create `data/`, `config/`, `logs/`,
`applications/` and `resume/` wherever `ROOT` happens to point. `api/conftest.py` steers
that at a throwaway directory before collection starts.

Design rules pinned here:
  * a run never creates or writes anything inside the repo — the failure this prevents is
    not cosmetic: on a clone where a `docker compose` run already made those directories
    root-owned, collection dies with PermissionError and the suite cannot run at all;
  * `config.py` still READS `APP_ROOT`. A conftest that sets the variable is worthless if
    the code stops honouring it, and that half would otherwise be pinned by nothing;
  * `PEREGRINE_DATASET` is cleared. It is also import-time, and against an empty temp root
    a private dataset sends `ensure_dirs()` into `raise SystemExit` *during import*, which
    pytest reports as INTERNALERROR with zero tests run.

Skipped when the repo-root tree is absent, which is the container (`./api` mounted as
`/app`, where `ROOT=/app` is correct and lives outside any checkout).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import config

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "web" / "src").is_dir(),
    reason="needs the repo-root tree; absent when ./api is mounted as /app in the container",
)

# Every path ensure_dirs() creates. If ROOT is inside the checkout, all of these are too.
_RUNTIME_DIRS = (
    "DATA_DIR", "JOBS_DIR", "EVIDENCE_DIR", "CONFIG_DIR",
    "APPLICATIONS_DIR", "RESUME_DIR", "LOGS_DIR",
)


def test_the_app_root_is_outside_the_repository():
    assert config.ROOT != REPO_ROOT
    assert REPO_ROOT not in config.ROOT.parents, (
        f"ROOT resolved to {config.ROOT}, inside the checkout — importing the app would "
        "create runtime directories in the working tree"
    )


@pytest.mark.parametrize("name", _RUNTIME_DIRS)
def test_no_runtime_directory_lands_in_the_working_tree(name):
    path = getattr(config, name)
    assert REPO_ROOT not in path.resolve().parents, f"config.{name} -> {path} is inside the repo"


def test_config_still_honours_the_app_root_override():
    # The conftest sets the variable; this pins that config.py keeps reading it. Without
    # this, a refactor of config.ROOT could ignore APP_ROOT and the suite would stay green
    # while the container run and the documented local override both silently broke.
    app_root = os.environ.get("APP_ROOT")
    assert app_root, "APP_ROOT should be set by api/conftest.py before collection"
    assert Path(app_root).is_dir()
    assert config.ROOT == Path(app_root).resolve()


# --- the guards, pinned out of process -----------------------------------------------
# These have to spawn a child pytest. Asserting on os.environ in-process proves nothing:
# the conftest already mutated it before this module was imported, so an in-process
# assertion passes whether or not the conftest still does the work.

API_DIR = Path(__file__).resolve().parents[1]


def _child_pytest(env_overrides: dict[str, str], drop: tuple[str, ...] = ()):
    env = {**os.environ, **env_overrides}
    for k in drop:
        env.pop(k, None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_health.py"],
        cwd=API_DIR, env=env, capture_output=True, text=True, timeout=180,
    )


def test_a_stray_dataset_export_cannot_abort_collection():
    r = _child_pytest({"PEREGRINE_DATASET": "nosuchpersona"}, drop=("APP_ROOT",))
    out = r.stdout + r.stderr
    assert "INTERNALERROR" not in out, f"stray PEREGRINE_DATASET aborted collection:\n{out}"
    assert r.returncode == 0, out


def test_the_suite_refuses_to_run_against_a_root_holding_live_data(tmp_path):
    # The suite writes logs/STATUS.md and applications/<id>/ artifacts under ROOT, and its
    # job ids collide with real ones. Both are gitignored, so an overwrite cannot be undone.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "profile.yml").write_text("name: Acme Candidate\n", encoding="utf-8")
    (tmp_path / "applications" / "2026-001").mkdir(parents=True)
    sentinel = tmp_path / "applications" / "2026-001" / "cover_letter.md"
    sentinel.write_text("DO NOT OVERWRITE\n", encoding="utf-8")

    r = _child_pytest({"APP_ROOT": str(tmp_path)}, drop=("PEREGRINE_TEST_ALLOW_LIVE_ROOT",))

    assert r.returncode != 0, "a live-looking APP_ROOT must be refused, not run against"
    assert "Refusing to run" in r.stdout + r.stderr
    assert sentinel.read_text(encoding="utf-8") == "DO NOT OVERWRITE\n"


def test_the_live_root_refusal_can_be_overridden_deliberately(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "profile.yml").write_text("name: Acme Candidate\n", encoding="utf-8")

    r = _child_pytest({"APP_ROOT": str(tmp_path), "PEREGRINE_TEST_ALLOW_LIVE_ROOT": "1"})

    assert r.returncode == 0, r.stdout + r.stderr
