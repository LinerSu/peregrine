"""Internal-mode CV intake: store-only profile merge + raw CV source roundtrip."""
import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(config, "CV_SOURCE", tmp_path / "cv_source.md")
    return tmp_path


def test_save_profile_merges_non_empty(tmp_cfg):
    from app.agent import tools

    store.write_profile({"name": "Old", "headline": "Eng", "skills": [{"name": "Py"}]})
    out = tools.save_profile({"name": "New", "location": "Remote", "skills": []})

    assert out["name"] == "New"          # non-empty value wins
    assert out["location"] == "Remote"   # new key added
    assert out["headline"] == "Eng"      # untouched key preserved
    assert out["skills"] == [{"name": "Py"}]  # empty list does NOT clobber existing


def test_save_cv_source_roundtrip(tmp_cfg):
    from app.agent import tools

    res = tools.save_cv_source("My CV text")
    assert res["chars"] == len("My CV text")
    assert store.read_cv_source() == "My CV text"


def test_put_profile_endpoint_cannot_clobber_non_cv_keys(tmp_cfg):
    from fastapi.testclient import TestClient

    from app.main import app

    store.write_profile({"name": "Old", "targets": {"roles": ["X"]}})
    client = TestClient(app)
    r = client.put("/api/profile", json={"headline": "Designer", "targets": {"roles": ["HACKED"]}})
    assert r.status_code == 200
    prof = store.read_profile()
    assert prof["headline"] == "Designer"            # CV-derived key merged
    assert prof["name"] == "Old"                     # untouched key preserved
    assert prof["targets"] == {"roles": ["X"]}       # non-CV key dropped by ProfileInput


def test_put_cv_source_endpoint(tmp_cfg):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    r = client.put("/api/cv/source", json={"text": "raw cv"})
    assert r.status_code == 200 and r.json()["chars"] == 6
    assert store.read_cv_source() == "raw cv"
