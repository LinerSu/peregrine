"""Extract plain text from an uploaded document (PDF / .txt / .md).

Shared by CV intake and job-posting ingestion so a user can hand us a saved page
or résumé as a file instead of a URL we'd have to scrape.
"""
from __future__ import annotations

import io


def extract_text(filename: str, raw: bytes) -> str:
    if (filename or "").lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8", errors="ignore")
