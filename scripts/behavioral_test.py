#!/usr/bin/env python3
"""Behavioral + regression suite for the Peregrine API (black-box, live server).

Run against a running stack (`docker compose up`):  python3 scripts/behavioral_test.py
Uses only the stdlib. Mutates data — restore the seed before/after (the examples
are copied on first run; in dev: docker compose exec api cp data/*.example.csv ...).
Exit code is non-zero if any check fails. Live Ashby/Lever postings can expire;
those are reported as SKIP, not FAIL.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date

BASE = "http://localhost:8000"
APPLE = "https://jobs.apple.com/en-us/details/200668037-0836/technical-program-manager-sensing"
results: list[tuple[str, str, str]] = []  # (status, name, detail)


def api(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "{}")
        except Exception:
            return e.code, {}


def upload(path: str, filename: str, content: bytes, ctype: str):
    b = "----peregrine"
    body = (
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode() + content + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(
        BASE + path, data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={b}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def check(name, cond, detail=""):
    results.append(("PASS" if cond else "FAIL", name, "" if cond else detail))


def skip(name, detail=""):
    results.append(("SKIP", name, detail))


def section(title):
    results.append(("SECTION", title, ""))


def minimal_pdf(text: str) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode()
    objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pdf = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        pdf += b"%010d 00000 n \n" % o
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return pdf


def run():
    # --- health & seed ----------------------------------------------------
    section("Health & seed state")
    s, h = api("GET", "/api/health")
    check("health 200 + provider", s == 200 and "provider" in h, f"{s} {h}")
    s, d = api("GET", "/api/jobs")
    seed_ok = s == 200 and d.get("count") == 1 and d["jobs"][0]["company"] == "Anthropic"
    check("seed = 1 Anthropic job", seed_ok, f"{d.get('count')} jobs")
    check("seed role backfilled (ML Engineer)", d["jobs"][0].get("role_category") == "ML Engineer", str(d["jobs"][0].get("role_category")))

    # --- chat router intents ---------------------------------------------
    section("Chat — bounded intent router")
    _, r = api("POST", "/api/chat", {"message": "find jobs matching my CV", "history": []})
    tools_used = [a.get("tool") for a in r.get("actions", [])]
    check("'find jobs' -> scan+list", "scan_jobs" in tools_used and "list_jobs" in tools_used, str(tools_used))
    _, r = api("POST", "/api/chat", {"message": "evaluate my fit for Anthropic", "history": []})
    check("'evaluate ... Anthropic' -> evaluate_fit", "evaluate_fit" in [a.get("tool") for a in r.get("actions", [])], str(r.get("reply", ""))[:60])
    _, r = api("POST", "/api/chat", {"message": "what skills do I need for Anthropic", "history": []})
    check("'skills I need' -> assess_upskilling", "assess_upskilling" in [a.get("tool") for a in r.get("actions", [])], "")
    _, r = api("POST", "/api/chat", {"message": "https://www.linkedin.com/jobs/view/123/", "history": []})
    check("chat refuses LinkedIn URL", "blocked by policy" in r.get("reply", ""), r.get("reply", "")[:60])
    _, r = api("POST", "/api/chat", {"message": "how should I prioritize this week?", "history": []})
    check("'ask' -> single answer, no tools", r.get("actions") == [], str(r.get("actions")))

    # --- crawl policy (regression) ---------------------------------------
    section("Crawl policy (regression)")
    for host in ("https://www.linkedin.com/jobs/view/1/", "https://www.indeed.com/viewjob?jk=1",
                 "https://www.glassdoor.com/job/1", "https://www.metacareers.com/jobs/1/"):
        s, d = api("POST", "/api/jobs/ingest", {"url": host})
        check(f"blocked: {host.split('//')[1][:24]}", s == 422 and "blocked by policy" in d.get("detail", ""), f"{s} {d.get('detail','')[:40]}")
    s, d = api("POST", "/api/jobs/ingest", {"url": "https://evil.example.com/jobs/1"})
    detail = d.get("detail", "")
    # Refused without ingestion — either "unsupported" (no provider matches, so no
    # fetch) or "allow-list" (safe_get refuses). Both mean: arbitrary host not crawled.
    check("arbitrary host refused (no fetch)", s == 422 and ("allow-list" in detail or "unsupported" in detail), f"{s} {detail[:40]}")

    # --- ingest + role + dedup (regression) -------------------------------
    section("Ingest, role classification, dedup")
    s, d = api("POST", "/api/jobs/ingest", {"url": APPLE})
    apple_id = d.get("job", {}).get("id")
    check("Apple ingest 200 (live)", s == 200 and apple_id, f"{s}")
    check("Apple role = Program Manager", d.get("job", {}).get("role_category") == "Program Manager", str(d.get("job", {}).get("role_category")))
    check("surrogate id YYYY-NNN", bool(apple_id) and apple_id[:4].isdigit() and "-" in apple_id, str(apple_id))
    s, d2 = api("POST", "/api/jobs/ingest", {"url": APPLE})
    check("re-ingest dedupes", d2.get("deduped") is True, str(d2.get("deduped")))
    # Ashby / Lever (live, soft — postings can expire)
    for label, url in (
        ("Ashby", "https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3"),
        ("Lever", "https://jobs.lever.co/leverdemo/33538a2f-d27d-4a96-8f05-fa4b0e4d940e"),
    ):
        s, d = api("POST", "/api/jobs/ingest", {"url": url})
        if s == 200:
            check(f"{label} ingest (live)", True)
        else:
            skip(f"{label} ingest (live)", f"HTTP {s} — posting may have expired")

    # --- evaluate + apply gate -------------------------------------------
    section("Evaluate fit + apply gate")
    s, ev = api("POST", f"/api/jobs/{apple_id}/evaluate")
    check("evaluate returns fit_score", isinstance(ev.get("fit_score"), (int, float)), str(ev.get("fit_score")))
    check("recommendation in {apply,hold,skip}", ev.get("recommendation") in ("apply", "hold", "skip"), str(ev.get("recommendation")))
    s, jd = api("GET", f"/api/jobs/{apple_id}")
    check("evaluation cards data in md", "## Agent evaluation" in jd.get("markdown", "") and "### Strengths" in jd.get("markdown", ""), "")
    s, pr = api("POST", f"/api/jobs/{apple_id}/prepare")
    check("apply gate returns apply_url", pr.get("apply_url", "").startswith("http"), str(pr.get("apply_url"))[:40])

    # --- mark applied + tracker CRUD (regression) ------------------------
    section("Applications tracker")
    s, ap = api("POST", f"/api/jobs/{apple_id}/apply")
    check("mark applied -> status applied", ap.get("application", {}).get("status") == "applied", "")
    check("applied_date = today", ap.get("application", {}).get("applied_date") == date.today().isoformat(), str(ap.get("application", {}).get("applied_date")))
    s, d = api("GET", "/api/applications")
    check("application appears in list", any(a["id"] == apple_id for a in d.get("applications", [])), f"count {d.get('count')}")
    s, d = api("PATCH", f"/api/applications/{apple_id}", {"status": "interviewing", "notes": "onsite", "company": "HACKED"})
    a = d.get("application", {})
    check("PATCH updates whitelisted fields", a.get("status") == "interviewing" and a.get("notes") == "onsite", str(a.get("status")))
    check("PATCH ignores non-whitelisted field", a.get("company") != "HACKED", str(a.get("company")))
    # manual add + id-collision regression
    s, d = api("POST", "/api/applications", {"company": "Stripe", "position": "Staff Engineer"})
    manual_id = d.get("application", {}).get("id")
    check("manual add -> applied", d.get("application", {}).get("status") == "applied", "")
    check("manual id != existing job id (collision guard)", manual_id != apple_id and manual_id is not None, str(manual_id))
    s, d = api("DELETE", f"/api/applications/{manual_id}")
    check("delete manual application", d.get("deleted") == manual_id, str(d))

    # --- star / role override --------------------------------------------
    section("Star & role override")
    s, d = api("PATCH", f"/api/jobs/{apple_id}", {"starred": True})
    check("star job (PATCH)", d.get("job", {}).get("starred") is True, "")
    s, d = api("PATCH", f"/api/jobs/{apple_id}", {"role_category": "Applied Scientist"})
    check("role override (PATCH)", d.get("job", {}).get("role_category") == "Applied Scientist", "")

    # --- preferences ------------------------------------------------------
    section("Preferences (search intent)")
    prefs = {"roles": ["Backend"], "work_mode": "remote", "exclude_keywords": ["crypto"]}
    s, _ = api("PUT", "/api/preferences", prefs)
    s, got = api("GET", "/api/preferences")
    check("preferences round-trip", got == prefs, str(got))
    api("PUT", "/api/preferences", {})  # reset

    # --- CV upload --------------------------------------------------------
    section("CV upload")
    s, _ = upload("/api/cv/upload", "cv.txt", b"Jane Doe\nSenior Backend Engineer\nPython, FastAPI", "text/plain")
    check("CV upload .txt -> 200", s == 200, str(s))
    s, _ = upload("/api/cv/upload", "cv.pdf", minimal_pdf("Jane Doe Backend Engineer Python"), "application/pdf")
    check("CV upload PDF (pypdf) -> 200", s == 200, str(s))
    s, _ = upload("/api/cv/upload", "bad.pdf", b"not a pdf", "application/pdf")
    check("CV upload invalid PDF -> 422", s == 422, str(s))


def report() -> int:
    print("\n" + "=" * 64)
    print("BEHAVIORAL + REGRESSION REPORT")
    print("=" * 64)
    p = f = sk = 0
    for status, name, detail in results:
        if status == "SECTION":
            print(f"\n— {name} —")
            continue
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "~"}[status]
        print(f"  {mark} {status:4} {name}" + (f"   [{detail}]" if detail else ""))
        p += status == "PASS"
        f += status == "FAIL"
        sk += status == "SKIP"
    print("\n" + "-" * 64)
    print(f"TOTAL: {p} passed, {f} failed, {sk} skipped")
    print("-" * 64)
    return 1 if f else 0


if __name__ == "__main__":
    run()
    sys.exit(report())
