#!/usr/bin/env python3
"""Post-close freshness monitor for the public dashboards and both Notion workspaces.

A system is STALE when its latest session is older than the latest NYSE session that
closed at least GRACE hours ago. Any STALE system exits 1 so the scheduled run fails
visibly (GitHub notifies the owner). Read-only; logs carry dates only.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import exchange_calendars as xcals
import pandas as pd

import nus_notion_preflight as pf

GRACE = timedelta(hours=6)
MANIFEST = "https://jeromechua2002-collab.github.io/swing-trading-dashboard/data/release-manifest.json"


def expected_session(now, calendar):
    """Latest session whose close is at least GRACE before now (ISO date)."""
    closes = calendar.schedule.loc[: now.date().isoformat(), "close"]
    done = closes[closes <= pd.Timestamp(now - GRACE)]
    return done.index[-1].date().isoformat()


def evaluate(expected, observed):
    """observed: {system: latest ISO date or None} -> list of (status, system, date)."""
    return [("OK" if d is not None and d >= expected else "STALE", name, d) for name, d in observed.items()]


def rotation_latest(notion, ds_id, prop):
    return pf.latest_dates(notion.rows(ds_id), [prop])[prop]["latest"]


def main():
    now = datetime.now(timezone.utc)
    expected = expected_session(now, xcals.get_calendar("XNYS"))
    observed = {}
    with urllib.request.urlopen(MANIFEST + "?t=" + str(int(now.timestamp())), timeout=30) as resp:
        manifest = json.load(resp)
    observed["Pages RRG and stock leadership"] = manifest.get("rrg_session")
    observed["Pages sector breadth"] = manifest.get("breadth_session")
    personal_token, nus_token = os.environ.get("NOTION_TOKEN", ""), os.environ.get("NUS_TRADING_SYNC", "")
    if personal_token:
        p = pf.Notion(personal_token)
        observed["Personal rotation chart"] = rotation_latest(p, pf.PERSONAL_IDS["Rotation Chart"], "Date")
        observed["Personal rotation signal"] = rotation_latest(p, pf.PERSONAL_IDS["Rotation Signal"], "Updated")
    if nus_token:
        n = pf.Notion(nus_token)
        ids = {pf.norm(i) for i in pf.PERSONAL_IDS.values()}
        sources = n.searchable_data_sources()
        for role, prop in (("Rotation Chart", "Date"), ("Rotation Signal", "Updated")):
            title = {"Rotation Chart": "Rotation Chart Data v2", "Rotation Signal": "Rotation Signal Snapshot"}[role]
            copies, _ = pf.find_copy(sources, title, ids)
            observed[f"NUS {role.lower()}"] = rotation_latest(n, copies[0]["id"], prop) if len(copies) == 1 else None
    results = evaluate(expected, observed)
    print(f"Expected latest completed session: {expected}")
    for status, name, d in results:
        print(f"{status:5} {name}: {d}")
    return 1 if any(s == "STALE" for s, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
