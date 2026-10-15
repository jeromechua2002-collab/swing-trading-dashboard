"""NUS journal catch-up: allowlist-only writes, dry run by default, relation remapped. Synthetic data."""
import contextlib
import io
import unittest

import nus_journal_catchup as cu
import test_nus_notion_preflight as t


class Recording(t.Fake):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.writes = []

    def call(self, method, path, payload=None):
        self.writes.append((method, path, payload))
        return {}


def nus_world(nus_trades):
    personal, nus = t.world(nus_trades=nus_trades)
    nus_rec = Recording(nus.sources, nus._rows)
    nus_rec._rows[t.NUS["Account"]] = [{"id": "nus-account-row", "properties": {}}]
    for i, row in enumerate(nus_rec._rows[t.NUS["Trades"]]):
        row["id"] = f"nus-trade-{i}"
    return personal, nus_rec


def run(personal, nus, wanted, apply):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cu.catch_up(personal, nus, wanted, apply=apply)
    return out.getvalue()


class CatchUp(unittest.TestCase):
    def setUp(self):
        rows = t.trades_rows()[:3]
        rows[2]["properties"]["Broker Net P/L USD"]["number"] = 1.0
        self.personal, self.nus = nus_world(rows)

    def test_dry_run_writes_nothing(self):
        out = run(self.personal, self.nus, [3.0, 4.0], apply=False)
        self.assertEqual(self.nus.writes, [])
        self.assertIn("PLAN  update trade #3", out)
        self.assertIn("PLAN  create trade #4", out)

    def test_apply_touches_only_allowlisted_trades_and_remaps_account(self):
        run(self.personal, self.nus, [3.0, 4.0], apply=True)
        self.assertEqual([(m, p) for m, p, _ in self.nus.writes], [("PATCH", "/pages/nus-trade-2"), ("POST", "/pages")])
        patch, create = self.nus.writes[0][2]["properties"], self.nus.writes[1][2]
        self.assertEqual(patch["Broker Net P/L USD"], {"number": t.SECRET_AMOUNT})
        self.assertEqual(patch["Account"], {"relation": [{"id": "nus-account-row"}]})
        self.assertNotIn("Net P/L", patch)
        self.assertEqual(create["parent"], {"type": "data_source_id", "data_source_id": t.NUS["Trades"]})
        self.assertEqual(create["properties"]["Trade Status"], {"select": {"name": "Open"}})

    def test_output_has_no_values(self):
        out = run(self.personal, self.nus, [3.0, 4.0], apply=True)
        for secret in (t.SECRET_SYMBOL, str(t.SECRET_AMOUNT), "Open", *t.NUS.values()):
            self.assertNotIn(secret, out)

    def test_missing_production_trade_refuses(self):
        with self.assertRaisesRegex(RuntimeError, "trade #9 is not a single production row"):
            run(self.personal, self.nus, [9.0], apply=True)
        self.assertEqual(self.nus.writes, [])


if __name__ == "__main__":
    unittest.main()
