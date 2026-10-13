"""Privacy regression tests: public journal contract, publication allowlist, sync output.

All fixtures are synthetic. No real trade records belong in this public repository.
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_site
import journal_public as jp
import sync_journal_performance as sync

CLOSED = [
    {"exit_date": "2026-10-02", "net_sgd": 40.0},
    {"exit_date": "2026-10-02", "net_sgd": -10.0},
    {"exit_date": "2026-10-05", "net_sgd": -25.5},
    {"exit_date": "2026-10-07", "net_sgd": 0.0},
]


def public(**overrides):
    p = jp.build_public(CLOSED, 2000.0, "2026-09-30", "2026-10-08T00:00:00+00:00", "notion_sync")
    p.update(overrides)
    return p


class PublicJournalContract(unittest.TestCase):
    def test_aggregates_by_day_and_compounds(self):
        p = public()
        self.assertEqual([c["date"] for c in p["curve"]], ["2026-09-30", "2026-10-02", "2026-10-05", "2026-10-07"])
        self.assertEqual(p["calendar"]["2026-10-02"], {"return_pct": 1.5, "closed_trades": 2})
        self.assertEqual(p["curve"][1]["index"], 101.5)
        self.assertEqual((p["winning_trades"], p["losing_trades"], p["breakeven_trades"]), (1, 2, 1))
        self.assertAlmostEqual(p["realized_return_pct"], 100 * (4.5 / 2000), places=3)

    def test_no_money_or_identity_in_payload(self):
        data = {k: v for k, v in public().items() if k != "basis"}  # basis is fixed disclosure text
        text = json.dumps(data)
        for marker in ("2000", "net_sgd", "symbol", "open", "S$", "notion."):
            self.assertNotIn(marker, text)

    def test_rejects_any_extra_or_private_field(self):
        for key, value in [("open_trades", []), ("symbol", "XYZ"), ("current_equity_sgd", 1.0),
                           ("starting_capital_sgd", 2000), ("notes", "x")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                jp.validate_public(public(**{key: value}))

    def test_rejects_private_detail_nested_in_rows(self):
        p = public()
        p["calendar"]["2026-10-02"]["trades"] = [{"symbol": "XYZ"}]
        with self.assertRaises(ValueError):
            jp.validate_public(p)
        p = public()
        p["curve"][1]["equity_sgd"] = 2030
        with self.assertRaises(ValueError):
            jp.validate_public(p)

    def test_rejects_inconsistent_arithmetic(self):
        p = public()
        p["curve"][2]["index"] += 0.5
        with self.assertRaises(ValueError):
            jp.validate_public(p)
        with self.assertRaises(ValueError):
            jp.validate_public(public(closed_trade_count=5))

    def test_marker_scan_detects_links_ids_and_money(self):
        for value in ("https://app.notion.com/p/abc", "0a1b2c3d4e5f60718293a4b5c6d7e8f9",
                      "0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9", "S$1,234.56"):
            with self.subTest(value=value):
                self.assertTrue(jp.find_private_markers({"basis_text": value}))

    def test_legacy_private_schema_is_rejected(self):
        legacy = {"updated_at": "2026-10-13T00:00:00Z", "starting_capital_sgd": 1000,
                  "closed_trades": [{"number": 1, "symbol": "XYZ", "size": 10, "entry_price": 1.0}],
                  "open_trades": [{"number": 2, "symbol": "ABC"}], "curve": [], "calendar": {}}
        with self.assertRaises(ValueError):
            jp.validate_public(legacy)
        self.assertTrue(jp.find_private_markers(legacy))

    def test_committed_snapshot_obeys_contract(self):
        snapshot = Path(__file__).resolve().parents[1] / "data/journal-performance.json"
        jp.validate_public(json.loads(snapshot.read_text(encoding="utf-8")))


class PublicationAllowlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        for name in build_site.ALLOWED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<!doctype html><title>x</title>" if name.endswith(".html") else "{}", encoding="utf-8")
        (self.root / "data/journal-performance.json").write_text(json.dumps(public()), encoding="utf-8")
        (self.root / "data/release-manifest.json").write_text(json.dumps({"schema_version": 1, "journal_return_pct": 0.2}), encoding="utf-8")
        for extra in ("scripts/sync_journal_performance.py", "equity.svg", "README.md", "CLAUDE.md",
                      ".github/workflows/pages.yml", "data/rrg.json"):
            path = self.root / extra
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private", encoding="utf-8")
        self.out = Path(self.tmp.name) / "_site"

    def build(self, environ=None):
        with mock.patch.dict(os.environ, environ or {}, clear=False):
            return build_site.build(self.root, self.out)

    def test_only_allowlisted_files_are_copied(self):
        found = self.build()
        self.assertEqual(sorted(found), sorted(build_site.ALLOWED))
        for leaked in ("scripts", "equity.svg", "README.md", "CLAUDE.md", ".github", "data/rrg.json"):
            self.assertFalse((self.out / leaked).exists(), leaked)

    def test_unexpected_file_fails_audit(self):
        self.build()
        (self.out / "scripts").mkdir()
        (self.out / "scripts/test_journal_snapshot.py").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "unexpected files"):
            build_site.audit(self.out, environ={})

    def test_private_journal_fails_audit(self):
        legacy = {"closed_trades": [{"symbol": "XYZ", "url": "https://www.notion.so/x"}], "open_trades": []}
        (self.root / "data/journal-performance.json").write_text(json.dumps(legacy), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "journal privacy contract"):
            self.build()

    def test_notion_link_in_page_fails_audit(self):
        (self.root / "index.html").write_text('<a href="https://app.notion.com/p/f9e8d7c6b5a4938271605f4e3d2c1b0a">x</a>', encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "Notion link"):
            self.build()

    def test_secret_patterns_fail_audit(self):
        for secret in ("ntn_" + "A" * 40, "ghp_" + "b" * 36, "-----BEGIN RSA PRIVATE KEY-----"):
            with self.subTest(secret=secret[:6]):
                (self.root / "rrg.html").write_text("const k='" + secret + "'", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "secret-like"):
                    self.build()

    def test_ci_secret_value_fails_audit(self):
        (self.root / "rates.html").write_text("token=plain-value-123456", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "value of a CI secret"):
            self.build({"NOTION_TOKEN": "plain-value-123456"})

    def test_manifest_private_keys_fail_audit(self):
        (self.root / "data/release-manifest.json").write_text(json.dumps({"journal_equity_sgd": 5100.0, "journal_open_count": 1}), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "release manifest"):
            self.build()


def notion_row(number, status, exit_date=None, net=None, fx=1.3, qty=10, entry=5.0, exits=(), fees=None, account=None):
    def num(v): return {"number": v}
    props = {
        "Trade Status": {"select": {"name": status}},
        "Symbol": {"title": [{"plain_text": "SYM%d" % number}]},
        "Account": {"relation": [{"id": sync.ACCOUNT_ID if account is None else account}] if account != "" else []},
        "Trade #": num(number), "Position Size": num(qty), "Avg Entry": num(entry),
        "Notes": {"rich_text": [{"plain_text": "private reasoning"}]},
        "Exit Date": {"date": {"start": exit_date}} if exit_date else {"date": None},
        "Broker Net P/L USD": num(net), "FX USD/SGD": num(fx), "Fee Charges USD": num(fees),
    }
    for i, (q, px) in enumerate(exits, start=1):
        props[f"Exit {i} Qty"], props[f"Exit {i} Price"] = num(q), num(px)
    return {"id": "0" * 32, "url": "https://www.notion.so/private", "properties": props}


class SyncPublishesOnlyPublicData(unittest.TestCase):
    def rows(self):
        rows = [notion_row(n, "Closed", "2026-10-%02d" % (n + 1), net=(-1) ** n * 5.0) for n in range(1, 11)]
        rows[0] = notion_row(1, "Closed", "2026-10-02", net=9.0, exits=((5, 6.0), (5, 6.2)), fees=1.0)  # reconciliation diff
        rows.append(notion_row(11, "Open"))
        return rows

    def run_export(self, rows, env):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "data/journal-performance.json"
        with mock.patch.object(sync, "fetch_all", return_value=rows), mock.patch.object(sync, "OUT", out), \
                mock.patch.dict(os.environ, env, clear=False):
            sync.export()
        return out.read_text(encoding="utf-8")

    def test_output_is_public_contract_only(self):
        text = self.run_export(self.rows(), {"JOURNAL_START_CAPITAL_SGD": "1000"})
        payload = jp.validate_public(json.loads(text))
        self.assertEqual(payload["closed_trade_count"], 10)
        text = json.dumps({k: v for k, v in payload.items() if k != "basis"})
        for marker in ("SYM", "private", "notion.", "1000", "open_trades", "url", "fx", "0" * 32):
            self.assertNotIn(marker, text)

    def test_unlinked_or_other_account_rows_are_excluded(self):
        rows = self.rows()
        rows.append(notion_row(12, "Closed", "2026-10-20", net=900.0, account=""))         # empty relation
        rows.append(notion_row(13, "Closed", "2026-10-21", net=-900.0, account="f" * 32))  # other account
        baseline = json.loads(self.run_export(self.rows(), {"JOURNAL_START_CAPITAL_SGD": "1000"}))
        payload = json.loads(self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"}))
        self.assertEqual(payload["closed_trade_count"], 10)
        self.assertEqual(payload["curve"], baseline["curve"])

    def test_unlinked_trade_inside_sequence_fails_loudly(self):
        rows = self.rows()
        rows[3] = notion_row(4, "Closed", "2026-10-05", net=5.0, account="")
        with self.assertRaisesRegex(RuntimeError, "contiguous"):
            self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"})

    def test_logs_disclose_no_open_position_information(self):
        import contextlib, io
        for rows in (self.rows(), [r for r in self.rows() if r["properties"]["Trade Status"]["select"]["name"] != "Open"]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"})
            self.assertNotIn("open", buf.getvalue().lower())
            self.assertNotIn("SYM", buf.getvalue())

    def test_missing_start_capital_refuses_to_publish(self):
        env = {k: v for k, v in os.environ.items() if k != "JOURNAL_START_CAPITAL_SGD"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sync, "fetch_all", return_value=self.rows()):
            with self.assertRaisesRegex(RuntimeError, "JOURNAL_START_CAPITAL_SGD"):
                sync.export()

    def test_gap_in_trade_numbers_fails(self):
        rows = [r for r in self.rows() if r["properties"]["Trade #"]["number"] != 4]
        with self.assertRaisesRegex(RuntimeError, "contiguous"):
            self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"})

    def test_unreconciled_exit_lots_fail(self):
        rows = self.rows()
        rows[1] = notion_row(2, "Closed", "2026-10-03", net=1.0, qty=10, exits=((4, 6.0),))
        with self.assertRaisesRegex(RuntimeError, "do not reconcile"):
            self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"})

    def test_errors_do_not_leak_symbols(self):
        rows = self.rows()
        rows[2] = notion_row(3, "Closed", None, net=None)
        with self.assertRaises(RuntimeError) as ctx:
            self.run_export(rows, {"JOURNAL_START_CAPITAL_SGD": "1000"})
        self.assertNotIn("SYM", str(ctx.exception))

    def test_fallback_rejects_private_snapshot(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "journal.json"
        out.write_text(json.dumps({"closed_trades": [{"symbol": "XYZ"}]}), encoding="utf-8")
        with mock.patch.object(sync, "OUT", out), self.assertRaisesRegex(SystemExit, "privacy contract"):
            sync.keep_committed_snapshot("test")


if __name__ == "__main__":
    unittest.main()
