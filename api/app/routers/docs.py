"""Serve the project's own Markdown docs to the web `/docs` page.

Read-only and path-safe: the API never takes a filesystem path from the client. It
builds a fixed catalog of known doc files (repo README + AGENTS + everything under
`docs/`, minus the folder index) and looks requests up by an internal slug, so there is
no way to traverse to an arbitrary file.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import config

router = APIRouter(prefix="/api/docs", tags=["docs"])


def _base() -> Path:
    """Where the docs live: `/app` in the container (docs are mounted there), or the repo
    root in native/dev runs (config.ROOT is `api/`, so its parent is the repo root)."""
    for b in (config.ROOT, config.ROOT.parent):
        if (b / "docs").is_dir() or (b / "README.md").is_file():
            return b
    return config.ROOT


def _catalog() -> "dict[str, Path]":
    """slug -> file. Order: overview (README), then docs/*.md (minus the index), then AGENTS."""
    base = _base()
    cat: dict[str, Path] = {}
    readme = base / "README.md"
    if readme.is_file():
        cat["readme"] = readme
    docs_dir = base / "docs"
    if docs_dir.is_dir():
        for p in sorted(docs_dir.glob("*.md")):
            if p.name.lower() == "readme.md":
                continue  # the folder index — the sidebar replaces it
            cat[p.stem.lower()] = p
    agents = base / "AGENTS.md"
    if agents.is_file():
        cat["agents"] = agents
    return cat


def _title(p: Path) -> str:
    """The doc's first heading — a Markdown `# ` or an HTML `<h1>` (the README uses the
    latter) — skipping fenced code blocks so a `#` shell comment isn't mistaken for a title.
    Falls back to a cleaned filename."""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if s.startswith("# "):
            return s[2:].strip()
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.IGNORECASE)
        if h1:
            return re.sub(r"<[^>]+>", "", h1.group(1)).strip()
    return p.stem.replace("_", " ").replace("-", " ").title()


@router.get("")
def list_docs():
    return {"docs": [{"slug": s, "title": _title(p), "file": p.name} for s, p in _catalog().items()]}


@router.get("/{slug}")
def get_doc(slug: str):
    p = _catalog().get(slug.lower())
    if not p:
        raise HTTPException(status_code=404, detail=f"no doc named {slug!r}")
    try:
        markdown = p.read_text(encoding="utf-8", errors="replace")
    except OSError:  # catalogued but vanished/unreadable between build and read -> 404, not 500
        raise HTTPException(status_code=404, detail=f"could not read doc {slug!r}")
    return {"slug": slug.lower(), "title": _title(p), "file": p.name, "markdown": markdown}
