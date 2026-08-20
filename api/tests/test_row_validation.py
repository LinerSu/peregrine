"""What a job row is allowed to hold, and why those two fields are not free text.

A tracked row looks inert. Two of its fields are not:

  * **`url`** is rendered as an href on Peregrine's own "Apply on company site" button and
    is handed to a local CLI as the link to open. It arrives from a scraped board or from
    a model that read a stranger's posting, so `javascript:` is a value it can hold, and
    the click that follows happens on `localhost:5173` — an allowed origin, with the whole
    API behind it. The web sanitises at render time; this pins the store, because Internal
    mode's reader is not a browser and never sees the web's guard.
  * **`id`** is a filesystem path component. It names `data/jobs/<id>.*`, and deleting a
    job runs `shutil.rmtree(applications/<id>)`. No route lets a client pick one — but
    `data/jobs.csv` is documented as hand-editable and a coding CLI writes it directly,
    which is precisely the reader that has never been through a route. So the row itself
    insists on the minted shape (`2026-001`), and an off-contract id is a loud validation
    error at read time rather than a quiet recursive delete later.

Both are `field_validator`s on the model rather than checks at the call sites, because the
call sites are the part that keeps growing.
"""
import pytest
from pydantic import ValidationError

from app.schemas import Job, JobIngestInput

_BASE = dict(id="2026-001", company="Acme", company_job_id="R1", position="Engineer")


@pytest.mark.parametrize(
    "hostile",
    [
        "javascript:fetch('/api/profile').then(r=>r.text()).then(t=>fetch('//x/'+t))",
        "JaVaScRiPt:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4x",
        "vbscript:msgbox",
        "file:///etc/passwd",
        "  javascript:alert(1)  ",
    ],
)
def test_a_job_row_refuses_to_store_a_url_that_is_not_http(hostile):
    assert Job(**_BASE, url=hostile).url == ""


@pytest.mark.parametrize("ok", ["https://example.com/jobs/1", "http://example.com/jobs/1"])
def test_a_job_row_keeps_a_real_posting_link(ok):
    assert Job(**_BASE, url=ok).url == ok


def test_internal_mode_ingest_refuses_a_url_that_is_not_http():
    """The Internal ingest body is filled in by a local CLI that just read the posting —
    the same third-party text, one process further away from us."""
    payload = dict(company="Initech", position="Engineer")
    assert JobIngestInput(**payload, url="javascript:alert(1)").url == ""
    assert JobIngestInput(**payload, url="https://example.com/x").url == "https://example.com/x"
    assert JobIngestInput(**payload, url=None).url == ""  # null-tolerance is unchanged


@pytest.mark.parametrize(
    "bad",
    ["../../etc", "..", "", "2026", "not-an-id", "2026-01", "2026-001/../../x",
     "/etc/passwd", "2026-001 ", "*"],
)
def test_a_row_refuses_an_id_that_is_not_a_minted_id(bad):
    with pytest.raises(ValidationError):
        Job(**{**_BASE, "id": bad})


@pytest.mark.parametrize("good", ["2026-001", "2026-999", "2026-1000", "1999-000"])
def test_a_row_accepts_every_id_the_minter_can_produce(good):
    """`_allocate_id` emits `{year}-{n:03d}` and does NOT stop at three digits — the
    thousandth job of a year is `2026-1000`, and validation must not reject a row the
    app itself just minted."""
    assert Job(**{**_BASE, "id": good}).id == good
