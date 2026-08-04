"""Mechanical checks on a drafted cover letter.

A rubric only binds the writer that reads it. These are the subset of its rules that can
be checked by counting rather than by judgement, so the same verdict is reached in
External and Internal mode, on every draft, without a second model call and without
spending a token. It is the same bargain as `evaluation.assess_legitimacy`.

What it deliberately does NOT do is score the letter. Whether an argument is persuasive
is not countable, and a number attached to it would be false precision. Every check here
answers a yes/no question that a careful reader would also answer the same way.
"""
from __future__ import annotations

import re
from typing import Any

# Roughly one page. The lower bound matters as much as the upper: a very short letter is
# usually one that never got to the evidence.
MIN_WORDS, MAX_WORDS = 250, 350

# Phrases that appear in letters that could have been sent to anyone. Kept short and
# specific on purpose — a long banned-phrase list starts flagging honest sentences.
_CLICHES = (
    "welcome the opportunity",
    "i am excited to",
    "i am passionate about",
    "perfect fit",
    "ideal candidate",
    "team player",
    "hit the ground running",
    "wealth of experience",
    "proven track record",
    "think outside the box",
    "your esteemed",
    "dear sir or madam",
    "to whom it may concern",
)

# Informal register. These are the ones that actually turned up in drafts rather than a
# dictionary of idioms — this list should grow from real letters, not from imagination.
_IDIOMS = ("cry wolf", "nobody reads", "the hard half", "the interesting half", "a no-brainer")

# Contractions, NOT possessives. "the Foundation's scale" is formal English; "it's" is
# not. The apostrophe-s case is the only ambiguous one, so it is matched on the specific
# pronouns and expletives that take it rather than on any noun.
_CONTRACTION = re.compile(
    r"\b\w+['’](?:t|re|ve|ll|m)\b"                      # don't, we're, I've, we'll, I'm
    r"|\b(?:it|that|there|here|he|she|who|what|let)['’]s\b"  # it's — not "Acme's"
    r"|\b(?:I|we|you|they|he|she|it|that|who)['’]d\b",       # I'd — not "Acme'd" (unreal)
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z0-9'’\-]+")


def _body(text: str) -> str:
    """The letter minus its salutation and sign-off, which distort every count.

    "Dear …" and "Yours sincerely," are fixed forms; including them would make a letter
    look longer than it reads and would count a salutation as a sentence.
    """
    lines = [ln for ln in (text or "").splitlines()]
    keep = []
    for ln in lines:
        s = ln.strip()
        low = s.lower()
        if low.startswith("dear ") or low.startswith(("yours sincerely", "yours faithfully",
                                                      "sincerely", "kind regards", "best regards")):
            continue
        keep.append(ln)
    return "\n".join(keep).strip()


def _sentences(body: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def check_letter(text: str, job: Any = None, unused_evidence: list[str] | None = None) -> list[dict[str, str]]:
    """Return the rules this draft breaks, worst first. Empty list means it passes.

    `job` supplies the employer name; `unused_evidence` is the labels of passages the
    selector offered and the letter did not draw on — the caller knows those, this module
    does not read the library itself.
    """
    body = _body(text)
    if not body:
        return [{"rule": "empty", "severity": "high", "detail": "There is no letter text to check."}]

    out: list[dict[str, str]] = []
    words = _WORD.findall(body)
    sentences = _sentences(body)
    paragraphs = _paragraphs(body)
    low = body.lower()

    if len(words) < MIN_WORDS:
        out.append({"rule": "length", "severity": "medium",
                    "detail": f"{len(words)} words — under {MIN_WORDS}. A letter this short "
                              "usually never reached the evidence."})
    elif len(words) > MAX_WORDS:
        out.append({"rule": "length", "severity": "medium",
                    "detail": f"{len(words)} words — over {MAX_WORDS}, past one page."})

    found = [c for c in _CLICHES if c in low]
    if found:
        out.append({"rule": "cliche", "severity": "high",
                    "detail": "Phrases any applicant could have written: "
                              + ", ".join(f"“{c}”" for c in found[:3])})

    idioms = [i for i in _IDIOMS if i in low]
    if idioms:
        out.append({"rule": "register", "severity": "medium",
                    "detail": "Colloquial for a formal letter: " + ", ".join(f"“{i}”" for i in idioms)})

    contractions = _CONTRACTION.findall(body)
    if contractions:
        out.append({"rule": "register", "severity": "low",
                    "detail": f"Contractions ({', '.join(sorted(set(contractions))[:4])}) — "
                              "formal register avoids them."})

    i_openers = [s for s in sentences if re.match(r"^I\b", s)]
    if sentences and len(i_openers) > len(sentences) / 2:
        out.append({"rule": "i-openers", "severity": "medium",
                    "detail": f"{len(i_openers)} of {len(sentences)} sentences begin with “I”. "
                              "Vary the subject so the work and the employer share the frame."})
    consecutive = [
        (a, b) for a, b in zip(paragraphs, paragraphs[1:])
        if re.match(r"^I\b", a) and re.match(r"^I\b", b)
    ]
    if consecutive:
        out.append({"rule": "i-openers", "severity": "low",
                    "detail": "Consecutive paragraphs both open with “I”."})

    company = (getattr(job, "company", "") or "").strip()
    if company:
        # Counted over the FULL text, salutation included: "Dear Members of the Python
        # Security Response Team" genuinely names them. Requiring two mentions is what
        # separates a letter that engages with the employer from one that merely
        # addresses them — the salutation alone cannot satisfy it.
        head = re.escape(company.split()[0])
        mentions = len(re.findall(rf"\b{head}", text or "", re.I))
        if mentions < 2:
            out.append({"rule": "employer", "severity": "high",
                        "detail": f"{company} is named {mentions} time(s). A letter that could be "
                                  "sent to another employer with a find-and-replace is a stock letter."})

    if not re.search(r"\d", body):
        out.append({"rule": "specifics", "severity": "medium",
                    "detail": "No figure anywhere. A letter with nothing quantified is usually "
                              "the vague one."})

    if unused_evidence:
        out.append({"rule": "evidence", "severity": "medium",
                    "detail": "Selected but unused: " + ", ".join(unused_evidence[:3])
                              + ". These are the specifics a CV cannot carry."})

    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda c: order.get(c["severity"], 3))
    return out
