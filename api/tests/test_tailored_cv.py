"""Tailored CV: graceful LaTeX render/compile + store-only save (both modes)."""
from pathlib import Path

import pytest

from app import config
from app import cv_render
from app import data_store as store
from app.schemas import Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def test_fallback_tex_is_wellformed_and_escapes():
    tex = cv_render.fallback_tex({"name": "A & B", "skills": [{"name": "Py"}]}, "Eng", "Acme")
    assert tex.startswith("\\documentclass")
    assert tex.rstrip().endswith("\\end{document}")
    assert r"\&" in tex  # the ampersand in the name is escaped


def test_compile_pdf_graceful_without_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(cv_render.shutil, "which", lambda *_: None)  # pretend no LaTeX
    ok = cv_render.compile_pdf(
        "\\documentclass{article}\\begin{document}x\\end{document}", tmp_path / "o.pdf"
    )
    assert ok is False  # graceful: returns False, never raises


def test_compile_pdf_clears_stale_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(cv_render.shutil, "which", lambda *_: None)  # no engine -> compile fails
    stale = tmp_path / "o.pdf"
    stale.write_bytes(b"%PDF-old")
    assert cv_render.compile_pdf("x", stale) is False
    assert not stale.exists()  # never serve a PDF that disagrees with the current .tex


def test_compile_pdf_hardens_io_and_no_shell_escape(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(cv_render.shutil, "which", lambda e: "/usr/bin/pdflatex" if e == "pdflatex" else None)

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        (Path(kw["cwd"]) / "cv.pdf").write_bytes(b"%PDF-1.4")  # simulate a successful compile

        class _Proc:
            returncode = 0

        return _Proc()

    monkeypatch.setattr(cv_render.subprocess, "run", fake_run)
    out = tmp_path / "o.pdf"
    assert cv_render.compile_pdf("\\documentclass{article}\\begin{document}x\\end{document}", out) is True
    # File I/O restricted to cwd; \write18 shell-escape never enabled.
    assert captured["env"].get("openin_any") == "p"
    assert captured["env"].get("openout_any") == "p"
    assert "-no-shell-escape" in captured["cmd"]  # explicitly disabled, not distro-default


def test_compile_pdf_fails_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(cv_render.shutil, "which", lambda e: "/usr/bin/pdflatex" if e == "pdflatex" else None)

    def fake_run(cmd, **kw):
        (Path(kw["cwd"]) / "cv.pdf").write_bytes(b"%PDF-partial")  # a partial PDF is left behind

        class _Proc:
            returncode = 1  # LaTeX failed

        return _Proc()

    monkeypatch.setattr(cv_render.subprocess, "run", fake_run)
    out = tmp_path / "o.pdf"
    assert cv_render.compile_pdf("x", out) is False  # non-zero exit -> not success
    assert not out.exists()  # the partial/broken PDF is not served


def test_extract_latex_takes_first_end_marker():
    from app.agent.subagents import _extract_latex

    t = "pre \\documentclass{article}\\begin{document}A\\end{document} junk \\end{document}"
    out = _extract_latex(t)
    assert out.endswith("A\\end{document}")
    assert "junk" not in out


def test_generate_tailored_cv_mock(tmp_store):
    from app.agent import tools

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    store.write_job_md("2026-001", "# Engineer — Acme\n\n## Posting\nBuild stuff.")
    res = tools.generate_tailored_cv("2026-001")
    assert "\\documentclass" in res["tex"]
    assert isinstance(res["pdf_available"], bool)
    assert store.read_cv_tex("2026-001") == res["tex"]


def test_save_and_get_tailored_cv(tmp_store):
    from app.agent import tools

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    assert tools.get_tailored_cv("2026-001") is None
    tex = "\\documentclass{article}\\begin{document}hi\\end{document}"
    saved = tools.save_tailored_cv("2026-001", tex)
    assert saved["tex"] == tex
    assert tools.get_tailored_cv("2026-001")["tex"] == tex
    assert "error" in tools.save_tailored_cv("nope", tex)  # unknown job


def test_cv_endpoints(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    client = TestClient(app)
    r = client.put("/api/jobs/2026-001/cv", json={"tex": "\\documentclass{article}\\begin{document}hi\\end{document}"})
    assert r.status_code == 200
    assert "\\documentclass" in client.get("/api/jobs/2026-001/cv").json()["tex"]
    # PDF download: 200 if LaTeX present (compiled), else 404 — both acceptable.
    assert client.get("/api/jobs/2026-001/cv.pdf").status_code in (200, 404)
    assert client.get("/api/jobs/nope/cv").status_code == 404  # unknown job
    assert client.get("/api/jobs/nope/cv.pdf").status_code == 404  # unknown job (pdf route)
