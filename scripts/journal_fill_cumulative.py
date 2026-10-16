#!/usr/bin/env python3
"""One-off: fill blank 'Cumulative P/L' (USD) for an allowlist of closed trades in the production journal.

Each value is the previous trade's Cumulative P/L plus this trade's Broker Net P/L USD,
read from the journal itself. Only blank fields are written; an existing value that
disagrees stops the run. Logs carry trade numbers only.
"""
import os
import sys

import nus_notion_preflight as pf

FIELD, NET = "Cumulative P/L", "Broker Net P/L USD"


def plan(rows, wanted):
    by_number = pf.keyed(rows, "Trade #")
    for n in wanted:
        if len(by_number.get(n, [])) != 1 or len(by_number.get(n - 1, [])) != 1:
            raise RuntimeError(f"trade #{int(n)} or its predecessor is not a single journal row")
    out, carry = [], None
    for n in wanted:
        row, prev = by_number[n][0], by_number[n - 1][0]
        props = row["properties"]
        if pf.value(props.get("Trade Status", {"type": None})) != "Closed":
            raise RuntimeError(f"trade #{int(n)} is not closed")
        net = pf.value(props.get(NET, {"type": None}))
        base = carry if carry is not None else pf.value(prev["properties"].get(FIELD, {"type": None}))
        if net is None or base is None:
            raise RuntimeError(f"trade #{int(n)} lacks a broker net or a previous cumulative total")
        new = round(base + net, 2)
        existing = pf.value(props.get(FIELD, {"type": None}))
        if existing is not None and abs(existing - new) > 0.005:
            raise RuntimeError(f"trade #{int(n)} already has a different cumulative total; not overwriting")
        out.append((n, row["id"], new, existing is None))
        carry = new
    return out


def main():
    wanted = sorted({float(x) for x in os.environ.get("FILL_TRADES", "").split(",") if x.strip()})
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not wanted or not token:
        print("FAIL FILL_TRADES and NOTION_TOKEN are required")
        return 1
    notion = pf.Notion(token)
    try:
        steps = plan(notion.rows(pf.PERSONAL_IDS["Trades"]), wanted)
        for n, page_id, new, blank in steps:
            if not blank:
                print(f"SKIP trade #{int(n)} (already correct)")
                continue
            if "--apply" in sys.argv:
                notion.call("PATCH", f"/pages/{page_id}", {"properties": {FIELD: {"number": new}}})
            print(f"{'SET ' if '--apply' in sys.argv else 'PLAN'} trade #{int(n)}")
    except (RuntimeError, PermissionError) as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
