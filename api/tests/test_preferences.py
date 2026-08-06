"""Search intent (`config/profile.yml::targets`), saved from the Search tab.

Two rules carry this endpoint, and both were unpinned until this file existed:

  * the body is **validated**. What is stored here is not inert — it filters every later
    scan and is shown to the fit-scoring model — so a wrong type is never contained:
    `exclude_keywords: [1, 2]` reached the YAML and then crashed the next scan on
    `kw.lower()`, and `locations: "remote"` iterated character by character and silently
    mis-filtered, which is worse: the user just saw the wrong jobs, with nothing on
    screen to point at.

  * the save **merges**. `store.write_targets` swaps the whole `targets` sub-tree, so
    writing the request body verbatim deleted every key the sender didn't happen to send.
    Sending a key still overwrites it — an explicit `[]` / `null` clears — because that is
    how the Search panel turns a filter off.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.main import app


@pytest.fixture
def tmp_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    return tmp_path


def test_stores_what_the_search_panel_sends(tmp_profile):
    # The exact shape of one Save from the Search tab — validation must not reject it.
    sent = {
        "roles": ["Machine Learning Engineer"],
        "locations": ["Toronto", "Remote"],
        "work_mode": "hybrid",
        "min_salary": 140000,
        "include_keywords": ["python"],
        "exclude_keywords": ["crypto"],
    }
    client = TestClient(app)
    r = client.put("/api/preferences", json=sent)
    assert r.status_code == 200
    assert client.get("/api/preferences").json() == {**sent, "min_salary": 140000.0}


def test_keyword_lists_are_stored_as_something_the_scan_can_lowercase(tmp_profile):
    # The reported crash: a number in the list reached the YAML, and the next scan died on
    # kw.lower(). Filtering must survive whatever a sloppy client sends.
    from app.agent import providers, tools

    client = TestClient(app)
    assert client.put("/api/preferences", json={"exclude_keywords": [1, 2], "roles": [None, " ML ", ""]}).status_code == 200
    saved = store.read_targets()
    assert saved["exclude_keywords"] == ["1", "2"]  # coerced, not left as ints
    assert saved["roles"] == ["ML"]                 # blanks dropped, None never persisted as "None"

    posting = providers.RawPosting(company="Acme", company_job_id="R1", position="Engineer",
                                   description="build things")
    assert tools._passes_filters(posting, {}, saved) is True  # would raise on an int keyword


def test_refuses_a_string_where_a_list_of_locations_belongs(tmp_profile):
    # "remote" iterates as 'r','e','m'… — accepted, and then every scan mis-filters
    # against single letters. A 422 is the only honest answer.
    store.write_targets({"locations": ["Toronto"]})
    client = TestClient(app)
    assert client.put("/api/preferences", json={"locations": "remote"}).status_code == 422
    assert client.put("/api/preferences", json={"min_salary": "a lot"}).status_code == 422
    assert store.read_targets() == {"locations": ["Toronto"]}  # nothing was written


def test_saving_preferences_keeps_the_keys_it_was_not_given(tmp_profile):
    # write_targets replaces the whole sub-tree, so a partial save must merge — otherwise
    # editing one filter silently deletes the others (and anything hand-added to
    # profile.yml that no client knows to send back).
    store.write_targets({"roles": ["ML Engineer"], "work_mode": "remote", "industries": ["robotics"]})
    r = TestClient(app).put("/api/preferences", json={"locations": ["Toronto"]})
    assert r.status_code == 200
    assert store.read_targets() == {
        "roles": ["ML Engineer"], "work_mode": "remote", "industries": ["robotics"],
        "locations": ["Toronto"],
    }


def test_a_value_that_is_sent_still_overwrites_the_stored_one(tmp_profile):
    # The other half of merging: turning a filter OFF must still work, and the panel does
    # that by sending an empty list / a null — not by omitting the key.
    store.write_targets({"exclude_keywords": ["crypto"], "min_salary": 140000})
    client = TestClient(app)
    assert client.put("/api/preferences", json={"exclude_keywords": [], "min_salary": None}).status_code == 200
    assert store.read_targets() == {"exclude_keywords": [], "min_salary": None}


def test_the_background_panels_career_goal_still_saves_here(tmp_profile):
    # REGRESSION PIN: the goal is not a search filter, but it IS stored in targets and
    # saved through this endpoint (Background panel → career_goal() → the letter prompt).
    # A model listing only the Search-tab fields would accept the save and drop it.
    from app.agent import tools

    client = TestClient(app)
    assert client.put("/api/preferences", json={"roles": ["ML Engineer"],
                                                "goal": "lead an inference platform"}).status_code == 200
    assert tools.career_goal() == "lead an inference platform"
    assert client.get("/api/preferences").json()["goal"] == "lead an inference platform"


def test_the_profile_around_targets_is_untouched(tmp_profile):
    # A preferences save must not be a profile edit: it writes one sub-tree of profile.yml.
    store.write_profile({"name": "Ada Example", "skills": [{"name": "Python"}],
                         "targets": {"roles": ["ML Engineer"]}})
    assert TestClient(app).put("/api/preferences", json={"work_mode": "remote"}).status_code == 200
    profile = store.read_profile()
    assert profile["name"] == "Ada Example" and profile["skills"] == [{"name": "Python"}]
    assert profile["targets"] == {"roles": ["ML Engineer"], "work_mode": "remote"}
