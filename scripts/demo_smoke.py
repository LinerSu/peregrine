#!/usr/bin/env python3
"""End-to-end smoke test for a demo persona.

Boots the real FastAPI app with PEREGRINE_DATASET=<persona> (which seeds the
dataset on import) and asserts the key endpoints return populated, consistent
data. Run from the `api/` directory:

    python ../scripts/demo_smoke.py ai-engineer

Exits non-zero on any failure, so CI can run it per persona.
"""
import os
import sys


def main(persona: str) -> int:
    # Must be set before importing app.config (it reads the env at import time).
    os.environ["PEREGRINE_DATASET"] = persona

    from fastapi.testclient import TestClient

    from app.demo_seed import PERSONAS
    from app.main import app

    if persona not in PERSONAS:
        print(f"FAIL {persona}: not a known persona ({', '.join(sorted(PERSONAS))})")
        return 1

    client = TestClient(app)
    jobs = client.get("/api/jobs").json()["jobs"]
    apps = client.get("/api/applications").json()["applications"]
    stats = client.get("/api/stats").json()
    profile = client.get("/api/profile").json()

    totals = stats["totals"]
    checks = {
        "profile has a name": bool(profile.get("name")),
        "jobs seeded": len(jobs) >= 3,
        "at least one evaluated": totals["evaluated"] >= 1,
        "at least one application": len(apps) >= 1,
        "funnel tracked matches jobs": totals["jobs"] == len(jobs),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAIL {persona}: {', '.join(failed)} | totals={totals}")
        return 1

    print(f"OK   {persona}: jobs={len(jobs)} evaluated={totals['evaluated']} applications={len(apps)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: demo_smoke.py <persona>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
