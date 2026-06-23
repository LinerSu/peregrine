"""Serve the in-app User Manual (the web `/docs` page) from `docs/manual/`.

Read-only and path-safe: the API never takes a filesystem path from the client. The nav is a
fixed manifest (`docs/manual/_nav.yml`) of section -> slugs; a request is served only if its
slug appears in that manifest and matches a safe pattern, so there is no path traversal.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from .. import config

router = APIRouter(prefix="/api/docs", tags=["docs"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _base() -> Path:
    """Dir that contains `docs/`: `/app` in the container (docs are mounted there), or the
    repo root in native/dev runs (config.ROOT is `api/`, so its parent is the repo root)."""
    for b in (config.ROOT, config.ROOT.parent):
        if (b / "docs" / "manual").is_dir():
            return b
    return config.ROOT


def _manual_dir() -> Path:
    return _base() / "docs" / "manual"


def _nav() -> "list[dict]":
    """Ordered [{title, pages:[slug,...]}] from _nav.yml (empty if absent/malformed)."""
    f = _manual_dir() / "_nav.yml"
    if not f.is_file():
        return []
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8", errors="replace")) or {}
    except (yaml.YAMLError, OSError):
        return []  # unreadable / malformed manifest -> empty nav, never a 500
    sections = data.get("sections") if isinstance(data, dict) else None
    out = []
    for sec in sections or []:
        if not isinstance(sec, dict):
            continue  # tolerate a stray non-mapping entry
        pages = [s for s in (sec.get("pages") or []) if isinstance(s, str) and _SLUG_RE.match(s)]
        out.append({"title": str(sec.get("title", "")), "pages": pages})
    return out


def _page_path(slug: str) -> "Path | None":
    """The file for a slug — only if the slug is in the manifest (so it's path-safe)."""
    if not _SLUG_RE.match(slug):
        return None
    known = {s for sec in _nav() for s in sec["pages"]}
    if slug not in known:
        return None
    p = _manual_dir() / f"{slug}.md"
    return p if p.is_file() else None


def _title(p: Path) -> str:
    """The doc's first heading — Markdown `# ` or HTML `<h1>` — skipping fenced code so a `#`
    shell comment isn't mistaken for a title. Falls back to a cleaned filename."""
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
    """Grouped nav: sections, each with its pages (slug + title). Skips missing files."""
    manual = _manual_dir()
    sections = []
    for sec in _nav():
        pages = []
        for slug in sec["pages"]:
            p = manual / f"{slug}.md"
            if p.is_file():
                pages.append({"slug": slug, "title": _title(p)})
        if pages:
            sections.append({"title": sec["title"], "pages": pages})
    return {"sections": sections}


@router.get("/{slug}")
def get_doc(slug: str):
    p = _page_path(slug.lower())
    if not p:
        raise HTTPException(status_code=404, detail=f"no doc named {slug!r}")
    try:
        markdown = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise HTTPException(status_code=404, detail=f"could not read doc {slug!r}")
    return {"slug": slug.lower(), "title": _title(p), "markdown": markdown}
