"""The evidence library: your own writing, selected per posting.

The feature exists because a letter written from profile.yml alone can only re-narrate the
CV. What's pinned here is that selection is deterministic (same passages in both modes),
that it degrades to "no evidence" rather than failing a letter, and that it never
overreaches: an unreadable file is skipped, not fatal.
"""
import pytest

from app import config, evidence
from app.schemas import Job


@pytest.fixture
def lib(tmp_path, monkeypatch):
    d = tmp_path / "evidence"
    d.mkdir()
    monkeypatch.setattr(config, "EVIDENCE_DIR", d)
    return d


def _job(**kw):
    base = dict(id="2026-001", company="Acme", company_job_id="R1", position="Compiler Engineer",
                req_skills="C++, LLVM", domains="Compilers")
    return Job(**{**base, **kw})


def test_no_library_is_not_an_error(lib):
    assert evidence.load_passages() == []
    assert evidence.select(_job()) == []
    assert evidence.as_prompt_block([]) == ""   # the writer just gets nothing extra


def test_markdown_headings_are_the_passage_seam(lib):
    (lib / "projects.md").write_text(
        "# Widget parser\n" + "Built an LLVM pass that folds widget loads. " * 6 +
        "\n\n## Rewrite\n" + "Rewrote it in C++ after the prototype deadlocked. " * 6
    )
    got = evidence.load_passages()
    assert [p.heading for p in got] == ["Widget parser", "Rewrite"]
    assert all(p.source == "projects.md" for p in got)


def test_a_file_without_headings_still_yields_passages(lib):
    (lib / "notes.txt").write_text(
        "Short line.\n\n" + "A paragraph about LLVM optimisation passes and their costs. " * 4
    )
    got = evidence.load_passages()
    assert got and all(p.heading == "" for p in got)


def test_selection_prefers_passages_matching_the_required_skills(lib):
    (lib / "a.md").write_text("# Frontend work\n" + "Wrote React components and CSS layouts. " * 6)
    (lib / "b.md").write_text("# Compiler work\n" + "Built an LLVM pass in C++ for loop folding. " * 6)

    picked = evidence.select(_job(), limit=1)
    assert len(picked) == 1
    assert picked[0].heading == "Compiler work"   # req_skills C++/LLVM outrank generic prose


def test_selection_is_capped_and_ordered(lib):
    for i in range(5):
        (lib / f"p{i}.md").write_text(f"# LLVM note {i}\n" + "C++ LLVM compiler work on passes. " * 6)
    assert len(evidence.select(_job(), limit=3)) == 3


def test_an_unreadable_file_is_skipped_not_fatal(lib):
    (lib / "good.md").write_text("# LLVM\n" + "C++ compiler pass work in LLVM. " * 6)
    (lib / "broken.pdf").write_bytes(b"not really a pdf")
    got = evidence.load_passages()   # must not raise
    assert [p.heading for p in got] == ["LLVM"]


def test_prompt_block_attributes_each_passage(lib):
    (lib / "paper.md").write_text("# Abstract\n" + "An LLVM C++ analysis for widget safety. " * 6)
    block = evidence.as_prompt_block(evidence.select(_job()))
    assert "[paper.md — Abstract]" in block
    assert "never invent" in block


def test_a_symlink_out_of_the_library_is_not_evidence(lib, tmp_path):
    """is_file() follows symlinks, so without confinement a link inside the library would
    let its target be read and pasted into a prompt — an arbitrary-file read dressed up as
    evidence. Résumé intake already guards this way; the library must match."""
    secret = tmp_path / "secret.md"
    secret.write_text("# Secret\n" + "Private notes that were never in the library. " * 6)
    (lib / "good.md").write_text("# LLVM\n" + "C++ compiler pass work in LLVM. " * 6)
    try:
        (lib / "leak.md").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable on this filesystem")

    got = evidence.load_passages()
    assert [p.heading for p in got] == ["LLVM"]
    assert all("Private notes" not in p.text for p in got)


def test_subfolders_keep_their_files_distinguishable(lib):
    # Two notes.md in different folders would otherwise cite each other's content.
    (lib / "compilers").mkdir()
    (lib / "talks").mkdir()
    (lib / "compilers" / "notes.md").write_text("# A\n" + "LLVM C++ pass notes. " * 8)
    (lib / "talks" / "notes.md").write_text("# B\n" + "Slides about LLVM C++ passes. " * 8)

    sources = {p.source for p in evidence.load_passages()}
    assert sources == {"compilers/notes.md", "talks/notes.md"}


def test_select_can_reuse_an_already_loaded_library(lib, monkeypatch):
    # evidence_for() loads once and passes it in; select() must not re-scan (PDFs are
    # expensive to parse and Internal mode fetches this per letter).
    (lib / "a.md").write_text("# LLVM\n" + "C++ LLVM compiler pass. " * 6)
    loaded = evidence.load_passages()
    monkeypatch.setattr(evidence, "load_passages", lambda: pytest.fail("re-scanned the library"))
    assert evidence.select(_job(), passages=loaded)
