"""Point the app at a throwaway root before anything imports it, and refuse to run
against a live one.

`app/config.py` resolves `ROOT` from `APP_ROOT` **at import time**, and `app/main.py`
calls `ensure_dirs()` at import time too. So the first test module that does
`from app.main import app` creates `data/`, `config/`, `logs/`, `applications/` and
`resume/` under whatever `ROOT` points at — before a single fixture runs.

Unset, `ROOT` is `api/`, so a plain `pytest` writes into the working tree, and on a clone
where a `docker compose` run already made those directories root-owned, collection dies
with `PermissionError` and the suite cannot run locally at all.

Setting `APP_ROOT` here fixes that: pytest imports the rootdir conftest before it collects
anything, which is the only hook early enough to beat the import-time resolution.

**The override fails closed.** `APP_ROOT` is also the documented way to run against a real
install (README), so a stale export from a host session would silently point the suite at
live data — and the suite is not read-only: it writes `logs/STATUS.md`, `logs/agent.log`
and `applications/<id>/` artifacts. `2026-001` is the canonical job id used across the
tests, so it collides with a real application, and both directories are gitignored, so
the overwrite is unrecoverable. A run against such a root is refused rather than trusted;
`PEREGRINE_TEST_ALLOW_LIVE_ROOT=1` is the deliberate escape hatch.

`PEREGRINE_DATASET` is cleared for a related reason. It is also import-time, and it
anchors under `ROOT/.demo/<name>/` — which the temp root has made empty. For a private
local dataset that sends `ensure_dirs()` into `raise SystemExit` *during import*, which
pytest reports as `INTERNALERROR ... caught unexpected SystemExit` with zero tests run.

This does not replace the per-file `tmp_store` fixtures — those re-point the same
constants at a per-test `tmp_path` and still own isolation *between* tests. This only
moves the import-time baseline somewhere safe. `api/tests/test_app_root.py` pins it.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# Files and directories that mean "this is somebody's real install", not a scratch root.
_LIVE_FILES = ("config/profile.yml", "config/profile.yaml", "data/jobs.csv",
               "data/applications.csv", "logs/STATUS.md")
_LIVE_DIRS = ("resume", "applications", "data/evidence", "data/jobs")


def _live_markers(root: Path) -> list[str]:
    found = [f for f in _LIVE_FILES if (root / f).is_file()]
    for d in _LIVE_DIRS:
        p = root / d
        if p.is_dir() and any(p.iterdir()):
            found.append(f"{d}/")
    return found


_supplied = os.environ.get("APP_ROOT")

if not _supplied:
    # Only mint a temp root if we are actually going to use one — otherwise an explicit
    # APP_ROOT=... run leaks an empty directory every time.
    _root = tempfile.mkdtemp(prefix="peregrine-tests-")
    os.environ["APP_ROOT"] = _root
    atexit.register(shutil.rmtree, _root, ignore_errors=True)
elif not os.environ.get("PEREGRINE_TEST_ALLOW_LIVE_ROOT"):
    _markers = _live_markers(Path(_supplied))
    if _markers:
        raise SystemExit(
            f"\nRefusing to run the test suite against APP_ROOT={_supplied}\n"
            f"It holds live data ({', '.join(_markers)}).\n\n"
            "The suite writes logs/STATUS.md, logs/agent.log and applications/<id>/ "
            "artifacts, and the ids it uses collide with real ones. Both directories are "
            "gitignored, so an overwrite is not recoverable.\n\n"
            "Unset APP_ROOT to run isolated, or set PEREGRINE_TEST_ALLOW_LIVE_ROOT=1 if "
            "you really mean it.\n"
        )

os.environ.pop("PEREGRINE_DATASET", None)
