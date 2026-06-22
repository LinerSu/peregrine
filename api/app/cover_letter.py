"""Cover-letter style references.

Gathers *style/structure* references for the generator from two local sources:
  - curated samples that ship with the repo (app/cover_letters/*.md), and
  - the user's own past letters (data/cover_letter_samples/*.md, gitignored).

Web examples are a third source, but only in Internal mode (Claude's own web
search, on the user's subscription) — see the cover-letter skill. The substance
of a letter always comes from the job + profile + evaluation, not these samples;
they only shape tone and structure, and are never copied verbatim.
"""
from __future__ import annotations

from pathlib import Path

from . import config

CURATED_DIR = Path(__file__).resolve().parent / "cover_letters"
USER_SAMPLES_DIRNAME = "cover_letter_samples"

_PER_SAMPLE_CHARS = 2000  # cap each sample so a long file can't dominate the prompt
_MAX_SAMPLES = 6


def _read_samples(directory: Path) -> list[tuple[str, str]]:
    if not directory.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):  # skip unreadable / non-UTF8 samples
            continue
        if text:
            out.append((path.stem, text[:_PER_SAMPLE_CHARS]))
    return out


def gather_style_references() -> str:
    """Curated + user samples, formatted for inclusion in the writer's prompt.
    Returns '' when none are available (the generator then relies on its own
    sense of structure)."""
    user_dir = config.DATA_DIR / USER_SAMPLES_DIRNAME
    # De-dupe by stem (curated wins over a same-named user sample), then cap.
    seen: set[str] = set()
    samples: list[tuple[str, str]] = []
    for name, text in _read_samples(CURATED_DIR) + _read_samples(user_dir):
        if name in seen:
            continue
        seen.add(name)
        samples.append((name, text))
    samples = samples[:_MAX_SAMPLES]
    if not samples:
        return ""
    blocks = [f"### Sample: {name}\n{text}" for name, text in samples]
    return (
        "Style/structure references only — match the tone and shape, do NOT copy "
        "phrasing or invent facts from these:\n\n" + "\n\n---\n\n".join(blocks)
    )
