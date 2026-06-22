"""Importing the résumé from resume/ into the profile (both modes)."""
import os

import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_dirs(tmp_path, monkeypatch):
    # Fully isolate every path the from-resume flow + app startup (ensure_dirs) touch,
    # so nothing writes into the real repo tree.
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "RESUME_DIR", tmp_path / "resume")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "data" / "jobs")
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "data" / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "data" / "applications.csv")
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "applications")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "config" / "profile.yml")
    monkeypatch.setattr(config, "CV_SOURCE", tmp_path / "config" / "cv_source.md")
    (tmp_path / "config").mkdir()
    (tmp_path / "resume").mkdir()
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def test_resolve_prefers_resume_path_then_newest(tmp_dirs):
    rdir = tmp_dirs / "resume"
    (rdir / "README.md").write_text("readme")   # ignored
    (rdir / ".hidden.pdf").write_bytes(b"x")     # ignored (dotfile)
    older, newer = rdir / "old.txt", rdir / "new.md"
    older.write_text("old cv")
    newer.write_text("new cv")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))  # newer is more recently modified
    assert store.resolve_resume_file().name == "new.md"          # newest real file
    store.write_profile({"resume_path": "resume/old.txt"})
    assert store.resolve_resume_file().name == "old.txt"         # resume_path wins when present
    store.write_profile({"resume_path": "resume/gone.pdf"})
    assert store.resolve_resume_file().name == "new.md"          # stale path -> newest


def test_resolve_none_when_empty(tmp_dirs):
    (tmp_dirs / "resume" / "README.md").write_text("readme")
    assert store.resolve_resume_file() is None


def test_resume_path_traversal_is_rejected(tmp_dirs):
    # an absolute or escaping resume_path must NOT read a file outside resume/
    (tmp_dirs / "resume" / "real.md").write_text("real cv")
    secret = tmp_dirs / "secret.txt"
    secret.write_text("TOP SECRET")  # lives OUTSIDE resume/
    for bad in ("resume/../secret.txt", str(secret)):
        store.write_profile({"resume_path": bad})
        got = store.resolve_resume_file()
        assert got is not None and got.name == "real.md"   # rejected -> newest in resume/
        assert got.read_text() != "TOP SECRET"


def test_fallback_skips_symlinks_and_readme_variants(tmp_dirs):
    rdir = tmp_dirs / "resume"
    (rdir / "real.txt").write_text("real cv")
    (rdir / "README.txt").write_text("readme variant")  # any README.* is ignored
    secret = tmp_dirs / "secret.pdf"
    secret.write_bytes(b"%PDF secret")  # outside resume/
    try:
        (rdir / "evil.pdf").symlink_to(secret)  # symlink escaping resume/ -> must be skipped
    except OSError:
        pass  # symlinks unsupported here; the README-exclusion half still validates
    got = store.resolve_resume_file()
    assert got is not None and got.name == "real.txt"  # not the symlink, not README.txt


def test_cv_from_resume_external(tmp_dirs):
    from fastapi.testclient import TestClient

    from app.main import app

    (tmp_dirs / "resume" / "cv.md").write_text("Jane Doe — Senior Engineer — Python")
    r = TestClient(app).post("/api/cv/from-resume")
    assert r.status_code == 200
    assert r.json()["resume_path"] == "resume/cv.md"
    assert store.read_profile().get("resume_path") == "resume/cv.md"  # recorded as the master


def test_cv_source_from_resume_internal_store_only(tmp_dirs):
    from fastapi.testclient import TestClient

    from app.main import app

    (tmp_dirs / "resume" / "cv.txt").write_text("My CV text")
    r = TestClient(app).post("/api/cv/source/from-resume")
    assert r.status_code == 200
    assert r.json()["resume_path"] == "resume/cv.txt"
    assert store.read_cv_source() == "My CV text"                    # stashed for local Claude
    assert store.read_profile().get("resume_path") == "resume/cv.txt"


def test_cv_from_resume_404_when_none(tmp_dirs):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).post("/api/cv/from-resume").status_code == 404
    assert TestClient(app).post("/api/cv/source/from-resume").status_code == 404
