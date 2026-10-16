"""NUS Notion preflight: independence, schema, relation, duplicate and privacy checks.

Offline, with fake Notion clients. All fixtures are synthetic.
"""
import contextlib
import copy
import io
import unittest

import nus_notion_preflight as pf

P = pf.PERSONAL_IDS
NUS = {"Trades": "aaaa0000-0000-0000-0000-000000000001", "Account": "aaaa0000-0000-0000-0000-000000000002",
       "Rotation Chart": "aaaa0000-0000-0000-0000-000000000003", "Rotation Signal": "aaaa0000-0000-0000-0000-000000000004"}
TITLES = {"Trades": "Trades", "Account": "Swing Account", "Rotation Chart": "Rotation Chart Data v2",
          "Rotation Signal": "Rotation Signal Snapshot"}
SECRET_SYMBOL, SECRET_AMOUNT = "ZZQX", 98765.43


def rt(s):
    return [{"plain_text": s}]


def ds(role, ds_id, account_target):
    props = {
        "Trades": {"Symbol": {"type": "title"}, "Trade #": {"type": "number"}, "Broker Net P/L USD": {"type": "number"},
                   "Trade Status": {"type": "select"}, "Net P/L": {"type": "formula"},
                   "Account": {"type": "relation", "relation": {"data_source_id": account_target}}},
        "Account": {"Name": {"type": "title"}},
        "Rotation Chart": {"Series": {"type": "title"}, "Date": {"type": "date"}, "Updated": {"type": "date"}},
        "Rotation Signal": {"Ticker": {"type": "title"}, "Updated": {"type": "date"}},
    }[role]
    return {"id": ds_id, "title": rt(TITLES[role]), "properties": copy.deepcopy(props)}


def trade(n, symbol="ABC", net=10.0, status="Closed"):
    return {"properties": {
        "Symbol": {"type": "title", "title": rt(symbol)}, "Trade #": {"type": "number", "number": n},
        "Broker Net P/L USD": {"type": "number", "number": net}, "Trade Status": {"type": "select", "select": {"name": status}},
        "Net P/L": {"type": "formula", "formula": {"type": "number", "number": net}},
        "Account": {"type": "relation", "relation": [{"id": "x"}]}}}


def chart(key, day):
    return {"properties": {"Series": {"type": "title", "title": rt(key)},
                           "Date": {"type": "date", "date": {"start": day}}, "Updated": {"type": "date", "date": {"start": day}}}}


def signal(t, day):
    return {"properties": {"Ticker": {"type": "title", "title": rt(t)}, "Updated": {"type": "date", "date": {"start": day}}}}


class Fake:
    def __init__(self, sources, rows, searchable=None, readable_foreign=False):
        self.sources, self._rows = sources, rows
        self.searchable = searchable if searchable is not None else list(sources.values())
        self.readable_foreign = readable_foreign

    def data_source(self, ds_id):
        if ds_id not in self.sources:
            if self.readable_foreign:
                return {"id": ds_id}
            raise PermissionError(404)
        return self.sources[ds_id]

    def rows(self, ds_id):
        return copy.deepcopy(self._rows[ds_id])

    def searchable_data_sources(self):
        return self.searchable


def trades_rows():
    return [trade(1), trade(2, net=-5.0), trade(3, SECRET_SYMBOL, SECRET_AMOUNT), trade(4, status="Open")]


def world(nus_trades=None, nus_account_target=None, searchable=None, nus_day="2026-10-14"):
    personal = Fake({P[r]: ds(r, P[r], P["Account"]) for r in P},
                    {P["Trades"]: trades_rows(), P["Account"]: [{"properties": {}}],
                     P["Rotation Chart"]: [chart("SMH|5D|05", "2026-10-14")],
                     P["Rotation Signal"]: [signal("XLK", "2026-10-14")]})
    nus = Fake({NUS[r]: ds(r, NUS[r], nus_account_target or NUS["Account"]) for r in NUS},
               {NUS["Trades"]: nus_trades if nus_trades is not None else trades_rows(), NUS["Account"]: [{"properties": {}}],
                NUS["Rotation Chart"]: [chart("SMH|5D|05", nus_day)],
                NUS["Rotation Signal"]: [signal("XLK", nus_day)]}, searchable=searchable)
    return personal, nus


def run(personal, nus):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        report = pf.run(personal, nus)
    return report, out.getvalue()


class Preflight(unittest.TestCase):
    def test_identical_independent_copy_passes(self):
        report, out = run(*world())
        self.assertFalse(report.failed, out)
        self.assertIn("latest 3 production trades present once and identical in NUS: 3/3", out)
        self.assertIn("Rotation Chart: rows personal=1 nus=1; missing=0 differing=0", out)

    def test_stale_nus_rotation_fails(self):
        report, out = run(*world(nus_day="2026-10-13"))
        self.assertTrue(report.failed)
        self.assertIn("FAIL Rotation Chart", out)
        self.assertIn("latest Date 2026-10-14/2026-10-13", out)

    def test_missing_rotation_rows_fail(self):
        personal, nus = world()
        nus._rows[NUS["Rotation Signal"]] = []
        report, out = run(personal, nus)
        self.assertTrue(report.failed)
        self.assertIn("FAIL Rotation Signal", out)

    def test_linked_view_of_original_fails(self):
        personal, nus = world()
        nus.searchable = [personal.sources[P["Trades"]]] + [s for i, s in nus.sources.items() if i != NUS["Trades"]]
        report, out = run(personal, nus)
        self.assertTrue(report.failed)
        self.assertIn("Trades: NUS sees the ORIGINAL personal data source", out)

    def test_relation_back_to_personal_account_fails(self):
        report, out = run(*world(nus_account_target=P["Account"]))
        self.assertTrue(report.failed)
        self.assertIn("relation 'Account' still targets a personal database", out)

    def test_duplicate_and_missing_trades_fail(self):
        rows = trades_rows()[:3] + [trades_rows()[2]]
        report, out = run(*world(nus_trades=rows))
        self.assertTrue(report.failed)
        self.assertIn("duplicate keys nus: trade #3", out)
        self.assertIn("missing in nus: trade #4", out)
        self.assertIn("latest 3 production trades present once and identical in NUS: 1/3", out)

    def test_changed_value_names_field_only(self):
        rows = trades_rows()
        rows[1]["properties"]["Broker Net P/L USD"]["number"] = -5.01
        report, out = run(*world(nus_trades=rows))
        self.assertTrue(report.failed)
        self.assertIn("trade #2 differs in ['Broker Net P/L USD']", out)
        self.assertNotIn("-5.01", out)

    def test_missing_copy_fails_with_share_hint(self):
        personal, nus = world()
        nus.searchable = [s for i, s in nus.sources.items() if i != NUS["Account"]]
        report, out = run(personal, nus)
        self.assertTrue(report.failed)
        self.assertIn("Account: expected exactly 1 independent NUS copy", out)
        self.assertIn("share the copied database", out)

    def test_schema_drift_fails(self):
        personal, nus = world()
        nus.sources[NUS["Trades"]]["properties"]["Trade Status"]["type"] = "status"
        report, out = run(personal, nus)
        self.assertTrue(report.failed)
        self.assertIn("type_changed=['Trade Status']", out)

    def test_output_never_contains_private_values_or_ids(self):
        rows = trades_rows()
        rows[2]["properties"]["Broker Net P/L USD"]["number"] = 1.0
        _, out = run(*world(nus_trades=rows))
        for secret in (SECRET_SYMBOL, str(SECRET_AMOUNT), "Open", *P.values(), *NUS.values()):
            self.assertNotIn(secret, out)


if __name__ == "__main__":
    unittest.main()
