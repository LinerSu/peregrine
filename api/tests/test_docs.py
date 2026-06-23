"""Docs API: lists curated project markdown, serves by slug, path-safe, sane titles."""
import pytest
from fastapi import HTTPException

from app import config
from app.routers import docs


@pytest.fixture
def docs_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    # README's real title is an HTML <h1>, preceded by a fenced code block whose '#' comment
    # must NOT be mistaken for the title — the exact trap the top-level README hits.
    (tmp_path / "README.md").write_text(
        "```bash\n# not a title\n```\n\n<h1 align=\"center\">Peregrine</h1>\n", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md — Peregrine\n", encoding="utf-8")
    (tmp_path / "STATUS.md").write_text("# Status\n", encoding="utf-8")  # intentionally omitted
    d = tmp_path / "docs"
    d.mkdir()
    (d / "SCANNING.md").write_text("# Scanning\n\nbody text\n", encoding="utf-8")
    (d / "README.md").write_text("# Docs\n", encoding="utf-8")  # folder index -> excluded
    return tmp_path


def test_lists_curated_docs_in_order(docs_tree):
    slugs = [x["slug"] for x in docs.list_docs()["docs"]]
    # README first, then docs/*.md (minus the folder index), then AGENTS. STATUS omitted.
    assert slugs == ["readme", "scanning", "agents"]


def test_title_skips_code_fence_and_reads_html_h1(docs_tree):
    titles = {x["slug"]: x["title"] for x in docs.list_docs()["docs"]}
    assert titles["readme"] == "Peregrine"   # from <h1>, NOT the '# not a title' fence comment
    assert titles["scanning"] == "Scanning"


def test_get_doc_returns_markdown(docs_tree):
    d = docs.get_doc("scanning")
    assert d["slug"] == "scanning" and "body text" in d["markdown"]


def test_unknown_and_traversal_slugs_404(docs_tree):
    # The slug is looked up in a fixed catalog, so traversal/unknown slugs can't read a file.
    for bad in ("nope", "../../etc/passwd", "status", "docs"):
        with pytest.raises(HTTPException) as exc:
            docs.get_doc(bad)
        assert exc.value.status_code == 404
