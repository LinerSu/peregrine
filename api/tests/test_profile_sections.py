"""Rich profile: CV-intake normalization + store-only PUT of links/sections."""
import pytest

from app import config


def test_normalize_cv_fields_coerces_sections_and_links():
    from app.agent.tools import _normalize_cv_fields

    parsed = {
        "name": "Jane", "headline": "Engineer", "location": None,
        "links": {"github": "https://github.com/j", "empty": ""},
        "skills": [{"name": "Python", "level": "expert"}, "SQL", {"no": "name"}],
        "sections": [
            {"id": "education", "title": "Education", "summary": "PhD in CS",
             "items": [{"heading": "PhD CS", "subhead": "2024", "detail": "thesis",
                        "links": ["https://x.com", {"label": "site", "url": "https://y.com"}]}]},
            "garbage",  # not a dict -> dropped
        ],
    }
    out = _normalize_cv_fields(parsed)
    assert out["name"] == "Jane" and "location" not in out          # null/empty omitted
    assert out["links"] == {"github": "https://github.com/j"}        # empty value dropped
    names = {s["name"] for s in out["skills"]}
    assert names == {"Python", "SQL"}                                # string skill coerced; no-name dropped
    sec = out["sections"]
    assert len(sec) == 1 and sec[0]["id"] == "education"             # garbage section dropped
    links = sec[0]["items"][0]["links"]
    assert links[0]["url"] == "https://x.com" and links[1]["label"] == "site"  # str + dict link


@pytest.fixture
def tmp_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    return tmp_path


def test_put_profile_round_trips_sections_and_links(tmp_profile):
    from fastapi.testclient import TestClient

    from app import data_store as store
    from app.main import app

    body = {
        "name": "Jane",
        "links": {"github": "https://github.com/j", "blank": ""},
        "sections": [{"id": "projects", "title": "Projects", "summary": "Two OSS tools",
                      "items": [{"heading": "tool", "links": ["https://repo"]}]}],
    }
    r = TestClient(app).put("/api/profile", json=body)
    assert r.status_code == 200
    prof = store.read_profile()
    assert prof["name"] == "Jane"
    assert prof["links"] == {"github": "https://github.com/j"}        # blank dropped by validator
    assert prof["sections"][0]["id"] == "projects"
    assert prof["sections"][0]["items"][0]["links"][0]["url"] == "https://repo"  # str link coerced


def test_put_profile_still_accepts_legacy_minimal(tmp_profile):
    from fastapi.testclient import TestClient

    from app.main import app

    # no sections/links -> still fine (backward compatible)
    r = TestClient(app).put("/api/profile", json={"name": "Bob", "skills": [{"name": "Go"}]})
    assert r.status_code == 200


def test_put_profile_drops_bad_sections_not_422(tmp_profile):
    from fastapi.testclient import TestClient

    from app import data_store as store
    from app.main import app

    # a stray non-dict element must NOT 422 the whole save (matches the External path)
    body = {"name": "X", "sections": [{"id": "education", "title": "Ed", "summary": "s"}, "garbage", 5]}
    r = TestClient(app).put("/api/profile", json=body)
    assert r.status_code == 200
    assert [s["id"] for s in store.read_profile()["sections"]] == ["education"]


def test_put_profile_drops_bad_section_items(tmp_profile):
    from fastapi.testclient import TestClient

    from app import data_store as store
    from app.main import app

    # a stray non-dict element inside items must be dropped, not 422 the whole save
    body = {"sections": [{"id": "x", "title": "X", "items": [{"heading": "ok"}, "stray", 3]}]}
    r = TestClient(app).put("/api/profile", json=body)
    assert r.status_code == 200
    items = store.read_profile()["sections"][0]["items"]
    assert len(items) == 1 and items[0]["heading"] == "ok"


def test_links_only_normalizes_and_is_accepted():
    from app.agent.tools import _normalize_cv_fields

    out = _normalize_cv_fields({"links": {"github": "https://github.com/x"}})
    assert out == {"links": {"github": "https://github.com/x"}}  # links survive on their own
