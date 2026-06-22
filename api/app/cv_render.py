"""Tailored-CV rendering: graceful LaTeX -> PDF compilation + a deterministic
fallback document.

The tailored CV body (LaTeX) is produced by the LLM (External) or local Claude
(Internal); this module compiles it to a PDF when a LaTeX engine is installed
(the api image ships one) and degrades gracefully to "tex only" when it isn't
(so tests/CI, which have no LaTeX, still pass). `fallback_tex` gives a valid,
compilable document for mock / no-key mode.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_ENGINES = ("pdflatex", "xelatex")

_ESCAPE = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def latex_available() -> bool:
    return any(shutil.which(e) for e in _ENGINES)


def _esc(s: Any) -> str:
    return "".join(_ESCAPE.get(c, c) for c in str(s or ""))


def fallback_tex(profile: dict[str, Any], position: str, company: str) -> str:
    """A minimal, compilable one-page CV from the profile (mock / no-key mode).
    Uses only standard LaTeX packages so a base TeX install suffices."""
    name = _esc(profile.get("name") or "Your Name")
    headline = _esc(profile.get("headline") or "")
    skills = profile.get("skills") or []
    items = "\n".join(
        rf"  \item \textbf{{{_esc(s.get('name'))}}}"
        + (rf" — {_esc(s.get('evidence'))}" if s.get("evidence") else "")
        for s in skills[:12]
    ) or r"  \item (add skills via the Profile tab)"
    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=2cm]{{geometry}}
\usepackage{{enumitem}}
\usepackage[hidelinks]{{hyperref}}
\setlist[itemize]{{leftmargin=*,nosep}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}{{\LARGE \textbf{{{name}}}}}\\[2pt]{headline}\end{{center}}
\section*{{Targeting: {_esc(position)} at {_esc(company)}}}
\textit{{Mock CV — set an LLM provider in .env, or use Internal mode, for a tailored draft.}}
\section*{{Skills}}
\begin{{itemize}}
{items}
\end{{itemize}}
\end{{document}}
"""


def compile_pdf(tex: str, out_pdf: Path) -> bool:
    """Compile LaTeX `tex` to `out_pdf`. Returns True on success; False if no engine
    is installed or compilation fails (the .tex remains the source of truth).

    Hardening for model-generated input:
    - no `-shell-escape` → `\\write18` shell execution stays disabled;
    - `openin_any=p` / `openout_any=p` → TeX file I/O is restricted to the working
      dir (no absolute/parent/hidden paths), so `\\input`/`\\openin` can't read or
      exfiltrate local files (e.g. /etc/passwd) into the served PDF;
    - compiler output is discarded (no unbounded in-memory capture);
    - a 60s timeout bounds runaway documents.

    Also clears any stale PDF up front, so a failed/skipped compile never leaves a
    PDF that disagrees with the current .tex."""
    out_pdf.unlink(missing_ok=True)
    engine = next((e for e in _ENGINES if shutil.which(e)), None)
    if not engine:
        return False
    env = {**os.environ, "openin_any": "p", "openout_any": "p"}
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        (work / "cv.tex").write_text(tex, encoding="utf-8")
        try:
            subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", "cv.tex"],
                cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60, env=env,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        produced = work / "cv.pdf"
        if not produced.exists():
            return False
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(produced, out_pdf)
        return True
