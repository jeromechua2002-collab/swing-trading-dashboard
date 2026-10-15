"""Daily Yahoo lagging-bar retry regression: never invent missing market closes."""
import unittest
from unittest.mock import patch

import pandas as pd

from build_rrg_data import refresh_lagging_daily_closes


class DailyVendorRetryTests(unittest.TestCase):
    def setUp(self):
        self.recent = pd.Series([10., 11.], index=pd.to_datetime(["2026-10-13", "2026-10-14"]))
        self.stale = self.recent.iloc[:1]
        self.cfg = {"period": "1y", "interval": "1d"}
        self.clock = pd.Timestamp("2026-10-15T02:00:00Z")

    @patch("build_rrg_data.prepare_series")
    @patch("build_rrg_data.close_series")
    @patch("build_rrg_data.download_prices")
    def test_recovers_only_lagging_symbols(self, download, close, prepare):
        download.return_value = object()
        close.return_value = self.recent
        prepare.return_value = (self.recent, 0)
        out = refresh_lagging_daily_closes(
            {"SPY": self.recent.copy(), "XLC": self.stale.copy(), "XLK": self.recent.copy()},
            self.cfg, self.clock)
        download.assert_called_once_with(["XLC"], self.cfg)
        self.assertEqual(out["XLC"].index[-1], self.recent.index[-1])
        self.assertEqual(out["XLK"].index[-1], self.recent.index[-1])

    @patch("build_rrg_data.prepare_series")
    @patch("build_rrg_data.close_series")
    @patch("build_rrg_data.download_prices")
    def test_stale_vendor_response_keeps_stale_bar_for_fail_closed_gate(self, download, close, prepare):
        download.return_value = object()
        close.return_value = self.stale
        prepare.return_value = (self.stale, 0)
        out = refresh_lagging_daily_closes(
            {"SPY": self.recent.copy(), "XLC": self.stale.copy()},
            self.cfg, self.clock)
        self.assertEqual(out["XLC"].index[-1], self.stale.index[-1])

    @patch("build_rrg_data.download_prices")
    def test_healthy_data_skips_retry(self, download):
        out = refresh_lagging_daily_closes(
            {"SPY": self.recent.copy(), "XLK": self.recent.copy()}, self.cfg, self.clock)
        download.assert_not_called()
        self.assertEqual(len(out), 2)

    @patch("build_rrg_data.download_prices", side_effect=RuntimeError("vendor offline"))
    def test_retry_error_does_not_mask_missing_data(self, download):
        out = refresh_lagging_daily_closes(
            {"SPY": self.recent.copy(), "XLC": self.stale.copy()},
            self.cfg, self.clock)
        self.assertEqual(out["XLC"].index[-1], self.stale.index[-1])


if __name__ == "__main__":
    unittest.main()
