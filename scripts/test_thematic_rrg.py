"""Offline tests for the display-only thematic RRG feed (no network)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import build_rrg_data as B
import build_thematic_rrg as T

BUILD_NOW = datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)  # after the 2026-10-16 close


def synthetic_frames():
    """Random walks on real NYSE sessions; DRAM starts 2026-04-02 like the real fund."""
    rng = np.random.default_rng(11)
    days = pd.DatetimeIndex(B.nyse().sessions_in_range("2023-06-01", "2026-10-16")).tz_localize(None)
    daily = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(days)))) for t in T.TICKERS}, index=days)
    daily.loc[daily.index < "2026-04-02", "DRAM"] = np.nan
    weekly = daily.groupby(daily.index - pd.to_timedelta(daily.index.weekday, unit="D")).last()
    weekly.loc[weekly.index < "2026-03-30", "DRAM"] = np.nan
    hours = []
    for d in days[-40:]:
        start = pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30)
        hours += [start + pd.Timedelta(hours=h) for h in range(7)]
    hourly = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, 0.003, len(hours)))) for t in T.TICKERS},
                          index=pd.DatetimeIndex(hours).tz_convert("UTC"))
    volume = pd.DataFrame(1e6, index=days, columns=T.TICKERS)
    return {"1d": (daily.loc[daily.index >= "2025-10-16"], volume), "1wk": (weekly, None), "1h": (hourly, None)}


class ThematicFeedTest(unittest.TestCase):
    def test_universe_is_the_ten_agreed_themes(self):
        self.assertEqual(T.THEMES, ["DRAM", "AIQ", "DTCR", "GRID", "UFO", "SHLD", "COPX", "REMX", "URA", "CIBR"])
        self.assertEqual({x["ticker"] for x in T.UNIVERSE["excluded"]}, {"NLR", "XAR"})
        fit = {t["ticker"]: t["fit"] for t in T.UNIVERSE["themes"]}
        self.assertIn("≈54%", fit["DTCR"])
        self.assertIn("≈42%", fit["SHLD"])

    def test_reuses_production_formula(self):
        self.assertIs(T.B, B)
        self.assertEqual(T.DOWNLOADS["1d"], B.CONFIGS["1D"])
        self.assertEqual(T.DOWNLOADS["1wk"], B.CONFIGS["1W"])

    def test_builds_and_new_fund_is_insufficient_on_weekly(self):
        payload = T.build(synthetic_frames(), BUILD_NOW)
        T.validate(payload)
        dram_w = payload["timeframes"]["1W"]["symbols"]["DRAM"]
        self.assertEqual(dram_w["status"], "insufficient")
        self.assertNotIn("trail", dram_w)
        self.assertEqual(payload["timeframes"]["1D"]["symbols"]["DRAM"]["status"], "ok")
        self.assertTrue(payload["timeframes"]["1D"]["benchmark_last"].startswith("2026-10-16"))
        self.assertIn("not proprietary JdK", payload["method"]["label"])
        json.dumps(payload, allow_nan=False)

    def test_vendor_failure_fails_closed_without_raising(self):
        def broken():
            raise RuntimeError("Yahoo download failed after 3 attempts")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rrg-thematic.json"
            payload = T.main(fetch=broken, out=out)
            self.assertEqual(payload["status"], "unavailable")
            self.assertEqual(json.loads(out.read_text())["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
