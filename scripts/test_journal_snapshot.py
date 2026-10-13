#!/usr/bin/env python3
"""Audit the PUBLIC journal snapshot served by the equity and calendar views.

Detailed trade reconciliation (fills, fees, broker P/L, FX) runs inside
sync_journal_performance.py against private Notion data and is covered with
synthetic fixtures in test_publication_privacy.py. Real trade facts must never
be hard-coded in this public repository.
"""
from pathlib import Path
import json

from journal_public import validate_public


def main():
    d = json.loads(Path("data/journal-performance.json").read_text(encoding="utf-8"))
    validate_public(d)
    assert d["closed_trade_count"] >= 10, "Published history is shorter than the verified closed-trade record"
    assert d["curve"][0]["index"] == 100.0, "Equity index must start at 100"
    print(f"JOURNAL AUDIT PASSED: public contract, {d['closed_trade_count']} closed trades, "
          f"{len(d['calendar'])} calendar dates, index compounding and win/loss counts consistent; "
          f"no positions, symbols, prices, sizes or amounts published ({d['source_status']}).")


if __name__ == "__main__":
    main()
