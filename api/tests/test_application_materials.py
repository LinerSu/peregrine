"""Generated materials are mirrored into applications/<job_id>/ (both modes save here)."""
import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "applications")
    return tmp_path


def test_cover_letter_and_cv_mirror_to_application_folder(tmp_dirs):
    store.write_cover_letter("2026-001", "Dear team,\n\nI'm a great fit.")
    store.write_cv_tex("2026-001", r"\documentclass{article}\begin{document}x\end{document}")
    app_dir = tmp_dirs / "applications" / "2026-001"
    assert (app_dir / "cover_letter.md").read_text(encoding="utf-8").startswith("Dear team,")
    assert (app_dir / "cv.tex").exists()
    # canonical copies still live beside the posting
    assert (tmp_dirs / "jobs" / "2026-001.cover_letter.md").exists()


def test_mirror_cv_pdf_only_when_present(tmp_dirs):
    app_dir = tmp_dirs / "applications" / "2026-001"
    store.mirror_cv_pdf("2026-001")  # no PDF compiled yet -> no-op, no crash
    assert not (app_dir / "cv.pdf").exists()
    store.cv_pdf_path("2026-001").parent.mkdir(parents=True, exist_ok=True)
    store.cv_pdf_path("2026-001").write_bytes(b"%PDF-1.4 fake")
    store.mirror_cv_pdf("2026-001")
    assert (app_dir / "cv.pdf").read_bytes().startswith(b"%PDF")


def test_mirror_is_best_effort_and_cleans_tmp(tmp_dirs, monkeypatch):
    # a copy failure must not break the canonical save, nor leave a .tmp behind
    monkeypatch.setattr(store.shutil, "copy", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert store.write_cover_letter("2026-002", "hi") == "data/jobs/2026-002.cover_letter.md"
    assert (tmp_dirs / "jobs" / "2026-002.cover_letter.md").read_text(encoding="utf-8") == "hi"
    app_dir = tmp_dirs / "applications" / "2026-002"
    assert not (app_dir / "cover_letter.md").exists()
    assert not list(app_dir.glob("*.tmp")) if app_dir.exists() else True  # no leftover tmp


def test_clear_mirrored_pdf_on_failed_recompile(tmp_dirs):
    # a stale mirrored PDF must be cleared so it can't disagree with the new .tex
    app_dir = tmp_dirs / "applications" / "2026-003"
    app_dir.mkdir(parents=True)
    (app_dir / "cv.pdf").write_bytes(b"%PDF old")
    store.clear_mirrored_cv_pdf("2026-003")
    assert not (app_dir / "cv.pdf").exists()
    store.clear_mirrored_cv_pdf("2026-003")  # idempotent, no crash when already gone
