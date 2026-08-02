"""Your long-form material — the things a CV can't hold.

A cover letter drawn only from `profile.yml` can only re-narrate the résumé: profile
entries are a line or two each, so the letter restates what the reader is about to see
again. The persuasive detail — why a design decision was made, what went wrong first, the
number that made the project worth doing — lives in write-ups, papers, talks and notes
that the app never saw.

This reads those files from `data/evidence/`, splits them into passages, and scores each
passage against a specific posting. Deterministic on purpose: no tokens, identical in
External and Internal mode, and testable. The trade is recall — material that describes
the same work in different words than the posting scores low. That's a real limit, not a
bug to be surprised by later; the fix (if it matters) is a hybrid retrieval, deliberately
left out of this version.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .extract import extract_text
from .job_tags import extract_skills
from .logging_config import get_logger

log = get_logger(__name__)

# Read through config at call time (not bound at import) so demo datasets and tests that
# repoint DATA_DIR are honoured.
def _dir() -> Path:
    return getattr(config, "EVIDENCE_DIR", config.DATA_DIR / "evidence")
_READABLE = (".md", ".markdown", ".txt", ".pdf", ".tex")
_MAX_FILE_BYTES = 4_000_000     # a runaway PDF shouldn't stall a letter
_MIN_PASSAGE_CHARS = 120        # a heading with one line under it isn't evidence
_MAX_PASSAGE_CHARS = 1_400      # keep a selected passage promptable


@dataclass
class Passage:
    source: str      # file name, so the letter writer can be told where a claim came from
    heading: str     # nearest markdown heading, "" when the file has none
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "heading": self.heading, "text": self.text}


def _split(raw: str) -> list[tuple[str, str]]:
    """Break a document into (heading, body) passages.

    Markdown headings are the natural seam — they're how people already chunk their own
    write-ups. Files without headings fall back to blank-line paragraphs, grouped until
    they're substantial enough to stand alone.
    """
    lines = (raw or "").replace("\r\n", "\n").split("\n")
    out: list[tuple[str, str]] = []
    heading, buf = "", []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) >= _MIN_PASSAGE_CHARS:
            out.append((heading, body[:_MAX_PASSAGE_CHARS]))

    saw_heading = False
    for line in lines:
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        if m:
            saw_heading = True
            flush()
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    flush()

    if not saw_heading:  # no headings at all: paragraphs, glued until they carry weight
        out, chunk = [], []
        for para in re.split(r"\n\s*\n", raw or ""):
            para = para.strip()
            if not para:
                continue
            chunk.append(para)
            joined = "\n\n".join(chunk)
            if len(joined) >= _MIN_PASSAGE_CHARS:
                out.append(("", joined[:_MAX_PASSAGE_CHARS]))
                chunk = []
        if chunk:
            joined = "\n\n".join(chunk)
            if len(joined) >= _MIN_PASSAGE_CHARS:
                out.append(("", joined[:_MAX_PASSAGE_CHARS]))
    return out


def load_passages() -> list[Passage]:
    """Every readable passage in data/evidence/ (empty list when the folder is empty).

    Confined to the folder the same way résumé intake is: `is_file()` follows symlinks, so
    without resolving, a link inside the library would let its target be read and pasted
    into a prompt — an arbitrary-file read dressed up as evidence.
    """
    root = _dir()
    if not root.exists():
        return []
    root_real = root.resolve()
    passages: list[Passage] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in _READABLE or path.name.startswith("."):
            continue
        try:
            real = path.resolve()
            real.relative_to(root_real)  # a symlink out of the library is not evidence
            if not real.is_file():
                continue
        except (ValueError, OSError):
            log.warning("evidence: skipping %s (outside the library)", path.name)
            continue
        # Nothing here is worth failing a letter over: an unreadable file is skipped, loudly.
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                log.warning("evidence: skipping %s (%.1f MB)", path.name, path.stat().st_size / 1e6)
                continue
            raw = extract_text(path.name, path.read_bytes())
        except Exception as exc:
            log.warning("evidence: could not read %s (%s)", path.name, exc.__class__.__name__)
            continue
        # Relative path, not just the name: the manual allows subfolders, and two
        # `notes.md` under different ones would otherwise cite each other's content.
        try:
            label = path.relative_to(root).as_posix()
        except ValueError:
            label = path.name
        for heading, body in _split(raw):
            passages.append(Passage(source=label, heading=heading, text=body))
    return passages


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_name(filename: str) -> str:
    """A filename that can only land inside the library.

    Uploads name their own file, so this takes the basename only (killing `../` and any
    absolute path), strips anything exotic, and keeps the extension — which is also what
    decides whether we can read it at all.
    """
    base = Path(filename or "").name
    stem, dot, ext = base.rpartition(".")
    stem = _SAFE_NAME.sub("_", stem or base).strip(" ._-") or "evidence"
    ext = _SAFE_NAME.sub("", ext).lower()
    return f"{stem[:80]}.{ext}" if dot and ext else stem[:80]


def list_files() -> list[dict[str, Any]]:
    """What's in the library, with how much each file actually contributes.

    Passage count matters more than file count: a PDF of slides with six words a page
    yields nothing, and the user should see that rather than assume it landed."""
    root = _dir()
    if not root.exists():
        return []
    counts: dict[str, int] = {}
    for p in load_passages():
        counts[p.source] = counts.get(p.source, 0) + 1
    out = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in _READABLE or path.name.startswith("."):
            continue
        try:
            rel = path.relative_to(root).as_posix()
            out.append({"name": rel, "bytes": path.stat().st_size, "passages": counts.get(rel, 0)})
        except OSError:
            continue
    return out


def save_file(filename: str, raw: bytes) -> dict[str, Any]:
    """Store an uploaded file in the library. Returns {error} rather than raising."""
    name = _safe_name(filename)
    if Path(name).suffix.lower() not in _READABLE:
        return {"error": f"unsupported file type — use {', '.join(_READABLE)}"}
    if len(raw) > _MAX_FILE_BYTES:
        return {"error": f"file is larger than {_MAX_FILE_BYTES // 1_000_000} MB"}
    root = _dir()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / name
    # Don't silently replace someone's earlier upload of a different document.
    if dest.exists():
        stem, _, ext = name.rpartition(".")
        n = 2
        while dest.exists():
            dest = root / (f"{stem}-{n}.{ext}" if ext else f"{name}-{n}")
            n += 1
    dest.write_bytes(raw)
    passages = sum(1 for p in load_passages() if p.source == dest.name)
    log.info("evidence: stored %s (%d passages)", dest.name, passages)
    return {"name": dest.name, "bytes": len(raw), "passages": passages}


def delete_file(name: str) -> bool:
    """Remove one file from the library. Confined: a name that escapes is refused."""
    root = _dir().resolve()
    try:
        target = (root / name).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return False
    if not target.is_file():
        return False
    target.unlink()
    return True


def _terms(*texts: str) -> set[str]:
    """The vocabulary a posting and a passage are compared on: the app's own skill tags
    plus the distinctive words of the title, lowercased."""
    joined = " ".join(t for t in texts if t)
    terms = {s.lower() for s in extract_skills(joined, limit=40)}
    terms |= {w for w in re.findall(r"[a-z][a-z+#.-]{3,}", joined.lower())}
    return terms - _STOPWORDS


_STOPWORDS = {
    "with", "that", "this", "from", "have", "will", "your", "their", "team", "work", "role",
    "years", "experience", "including", "using", "across", "such", "into", "about", "other",
    "more", "most", "also", "well", "than", "them", "when", "what", "which", "were", "been",
    "would", "could", "should", "must", "help", "make", "made", "like", "some", "over",
}


def select(job: Any, limit: int = 3, passages: list[Passage] | None = None) -> list[Passage]:
    """The passages most worth quoting for THIS posting, best first.

    Scoring is overlap on the shared vocabulary, weighted so a passage that matches the
    job's *required skills* beats one that merely shares prose. Ties break on brevity — a
    tight passage is easier to quote than a long one that happens to mention more words.
    """
    passages = load_passages() if passages is None else passages
    if not passages:
        return []
    req = {s.strip().lower() for s in (getattr(job, "req_skills", "") or "").split(",") if s.strip()}
    wanted = _terms(getattr(job, "position", ""), getattr(job, "req_skills", ""),
                    getattr(job, "domains", ""))
    scored: list[tuple[float, int, Passage]] = []
    for p in passages:
        have = _terms(p.heading, p.text)
        overlap = len(wanted & have)
        if not overlap:
            continue
        skill_hits = len(req & have)
        scored.append((overlap + 3.0 * skill_hits, -len(p.text), p))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [p for _, _, p in scored[:limit]]


def as_prompt_block(passages: list[Passage]) -> str:
    """Render selected passages for a prompt, attributed so the writer can cite the source.

    Unlike a job posting, this is the USER'S OWN material — trusted input. It still gets a
    clear boundary so the model can tell it apart from the posting it sits beside.
    """
    if not passages:
        return ""
    parts = ["The candidate's own written material (use it for specifics a CV can't hold; "
             "cite naturally, never invent):"]
    for p in passages:
        label = f"{p.source}" + (f" — {p.heading}" if p.heading else "")
        parts.append(f"[{label}]\n{p.text}")
    return "\n\n".join(parts)
