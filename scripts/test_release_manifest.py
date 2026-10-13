import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from build_release_manifest import create

STAMP = "2026-10-13T23:10:00+00:00"
JSTAMP = "2026-10-13T23:15:00+00:00"
NOW = datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)

class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.members = {}
        for i in range(11):
            self.members[f"X{i}"] = [f"T{i}_{j}" for j in range(16 if i == 10 else 10)]
        common = {"industries": {f"I{i}": [] for i in range(16)}}
        rrg = {
            "generated_at": STAMP,
            "universes": {"stock_members": self.members},
            "timeframes": {
                "1W": {},
                "1D": {**common, "sectors": {x: [] for x in self.members},
                       "benchmark_price": [{"time": "2026-10-13T00:00:00+00:00"}]},
                "4H": common,
                "1H": {},
            },
        }
        breadth = {
            "status": "ok",
            "as_of": "2026-10-13",
            "generated_at": "2026-10-13T23:14:00+00:00",
            "rows": [{"cap": k, "equal": "R" + k} for k in self.members]
        }
        closed = [{"number": i + 1, "exit_date": "2026-10-13"} for i in range(10)]
        journal = {
            "updated_at": JSTAMP,
            "snapshot_kind": "manual_verified_pending_reconciliation",
            "closed_trades": closed,
            "open_trades": [{"number": 9, "symbol": "XYZ"}],
            "curve": [{"equity_sgd": 2500.0}] * 10 + [{"equity_sgd": 2625.0}],
            "current_equity_sgd": 2625.0,
        }
        self.write("data/rrg-core.json", rrg)
        self.write("data/sector-breadth.json", breadth)
        self.write("data/journal-performance.json", journal)
        for sector, members in self.members.items():
            stocks = {"generated_at": STAMP, "members": members,
                      "timeframes": {tf: {"price_context": {t: {} for t in members}}
                                     for tf in ("1D", "4H")}}
            self.write(f"data/stocks/{sector}.json", stocks)

    def write(self, path, payload):
        dst = self.root / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(payload), encoding="utf-8")

    def load(self, path):
        return json.loads((self.root / path).read_text())

    def test_valid_complete_release(self):
        out = create(self.root, NOW)
        self.assertEqual(out["rrg_session"], "2026-10-13")
        self.assertEqual(out["market_coverage"]["stocks"], 116)
        self.assertEqual(out["market_coverage"]["breadth_pairs"], 11)
        self.assertEqual(out["journal_status"], "manual_snapshot")
        self.assertEqual(out["journal_equity_sgd"], 2625.0)
        self.assertEqual(len(out["sha256"]["rrg"]), 64)

    def test_detect_mismatched_sessions(self):
        data = self.load("data/sector-breadth.json")
        data["as_of"] = "2026-10-12"
        self.write("data/sector-breadth.json", data)
        with self.assertRaisesRegex(ValueError, "daily sessions differ"):
            create(self.root, NOW)

    def test_reject_missing_stock(self):
        sector = next(iter(self.members))
        data = self.load(f"data/stocks/{sector}.json")
        del data["timeframes"]["4H"]["price_context"][self.members[sector][0]]
        self.write(f"data/stocks/{sector}.json", data)
        with self.assertRaisesRegex(ValueError, "incomplete absolute price context"):
            create(self.root, NOW)

    def test_reject_build_timestamp_skew(self):
        breadth = self.load("data/sector-breadth.json")
        breadth["generated_at"] = "2026-10-13T20:00:00+00:00"
        self.write("data/sector-breadth.json", breadth)
        with self.assertRaisesRegex(ValueError, "more than 30m"):
            create(self.root, NOW)

    def test_reject_missing_breadth_pair(self):
        breadth = self.load("data/sector-breadth.json")
        breadth["rows"].pop()
        self.write("data/sector-breadth.json", breadth)
        with self.assertRaisesRegex(ValueError, "breadth feed"):
            create(self.root, NOW)

    def test_reject_mismatched_equity(self):
        data = self.load("data/journal-performance.json")
        data["current_equity_sgd"] += 1
        self.write("data/journal-performance.json", data)
        with self.assertRaisesRegex(ValueError, "equity/curve mismatch"):
            create(self.root, NOW)

if __name__ == "__main__":
    unittest.main()
