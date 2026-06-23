"""Docs API: serves the grouped User Manual from docs/manual/, path-safe, sane titles."""
import pytest
from fastapi import HTTPException

from app import config
from app.routers import docs


@pytest.fixture
def manual(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    d = tmp_path / "docs" / "manual"
    d.mkdir(parents=True)
    (d / "_nav.yml").write_text(
        "sections:\n"
        "  - title: Getting started\n"
        "    pages: [install, what-is]\n"
        "  - title: Advanced\n"
        "    pages: [secret, missing]\n",  # 'missing' has no file -> dropped from the nav
        encoding="utf-8",
    )
    # A fenced '#' comment must NOT be mistaken for the title (the real-README trap).
    (d / "install.md").write_text(
        "```bash\n# not a title\n```\n\n# Install & open\n\nbody\n", encoding="utf-8"
    )
    (d / "what-is.md").write_text("# What is Peregrine\n\nintro\n", encoding="utf-8")
    (d / "secret.md").write_text("# Secret\n\nshh\n", encoding="utf-8")
    return tmp_path


def test_lists_grouped_sections_in_order(manual):
    r = docs.list_docs()
    assert [s["title"] for s in r["sections"]] == ["Getting started", "Advanced"]
    assert [p["slug"] for p in r["sections"][0]["pages"]] == ["install", "what-is"]
    assert [p["slug"] for p in r["sections"][1]["pages"]] == ["secret"]  # 'missing' dropped


def test_title_skips_code_fence(manual):
    titles = {p["slug"]: p["title"] for s in docs.list_docs()["sections"] for p in s["pages"]}
    assert titles["install"] == "Install & open"   # not the '# not a title' fence line
    assert titles["what-is"] == "What is Peregrine"


def test_get_doc_returns_markdown(manual):
    d = docs.get_doc("what-is")
    assert d["slug"] == "what-is" and "intro" in d["markdown"]


def test_malformed_manifest_is_safe(manual):
    nav = manual / "docs" / "manual" / "_nav.yml"
    # A non-mapping YAML -> empty nav, never a 500.
    nav.write_text("- just\n- a list\n", encoding="utf-8")
    assert docs.list_docs() == {"sections": []}
    # A stray non-dict section is skipped; a valid one is kept.
    nav.write_text("sections:\n  - nope\n  - title: OK\n    pages: [install]\n", encoding="utf-8")
    r = docs.list_docs()
    assert [s["title"] for s in r["sections"]] == ["OK"]


def test_unknown_and_traversal_slugs_404(manual):
    # Slugs are served only from the manifest, so unknown / traversal / no-file slugs 404.
    for bad in ("nope", "../../etc/passwd", "missing", "_nav"):
        with pytest.raises(HTTPException) as exc:
            docs.get_doc(bad)
        assert exc.value.status_code == 404
