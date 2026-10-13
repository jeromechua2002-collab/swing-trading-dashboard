"""Verify the PUBLIC site no longer serves private journal data or source files.

A green deployment is not proof: this fetches the real public endpoints
(cache-busted) and fails if the journal violates the public contract or if any
previously exposed path still returns content.
"""
import json
import sys
import time

import requests

from journal_public import validate_public

# Paths that were publicly served before the allowlisted _site/ artifact.
MUST_BE_GONE = (
    "equity.svg",
    "scripts/sync_journal_performance.py",
    "scripts/test_journal_snapshot.py",
    "scripts/build_release_manifest.py",
    "README.md",
    "requirements.txt",
    "data/rrg.json",
)


def check(base):
    base = base.rstrip("/") + "/"
    bust = {"exposure-check": str(time.time_ns())}
    problems = []
    r = requests.get(base + "data/journal-performance.json", params=bust, timeout=20,
                     headers={"Cache-Control": "no-cache"})
    if r.status_code != 200:
        problems.append(f"journal endpoint HTTP {r.status_code}")
    else:
        try:
            validate_public(r.json())
        except (ValueError, json.JSONDecodeError) as exc:
            problems.append(f"journal endpoint still violates the public contract: {str(exc)[:160]}")
    r = requests.get(base + "data/release-manifest.json", params=bust, timeout=20)
    if r.status_code == 200:
        manifest = r.json()
        for key in ("journal_equity_sgd", "journal_open_count", "journal_latest_trade"):
            if key in manifest:
                problems.append(f"release manifest still publishes {key}")
    for path in MUST_BE_GONE:
        r = requests.get(base + path, params=bust, timeout=20)
        if r.status_code != 404:
            problems.append(f"{path}: HTTP {r.status_code} (expected 404)")
    return problems


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://jeromechua2002-collab.github.io/swing-trading-dashboard/"
    attempts = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for attempt in range(1, attempts + 1):
        problems = check(url)
        if not problems:
            print(f"PUBLIC EXPOSURE CHECK PASSED: journal obeys the public contract; {len(MUST_BE_GONE)} formerly exposed paths return 404")
            break
        print(f"Exposure check attempt {attempt}/{attempts}:\n  - " + "\n  - ".join(problems), flush=True)
        if attempt == attempts:
            raise SystemExit(1)
        time.sleep(30)  # Pages CDN can serve the previous artifact for a few minutes
