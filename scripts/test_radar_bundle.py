"""Radar bundle capture: exact validated bars only, opt-in, never inside _site. Synthetic data."""
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import radar_bundle as rb


def frame(tickers, idx, close_shift=0.0):
    cols = pd.MultiIndex.from_product([tickers, list(rb.FIELDS)])
    data = {}
    for t in tickers:
        for f in rb.FIELDS:
            data[(t, f)] = [100.0 + i + (close_shift if f == "Close" else 0) for i in range(len(idx))]
    return pd.DataFrame(data, index=idx, columns=cols)


class Capture(unittest.TestCase):
    def setUp(self):
        rb._frames.clear(); rb._withheld.clear()
        self.idx = pd.date_range("2026-10-01", periods=5, freq="D", tz="UTC")

    def test_disabled_by_default_changes_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            rb.capture("1D", {"SPY": pd.Series([1.0], index=self.idx[:1])}, {})
        self.assertEqual(rb._frames, {})

    def test_exports_only_validated_bars_from_the_producing_download(self):
        data = frame(["SPY"], self.idx)
        validated = data[("SPY", "Close")].iloc[:4]  # forming last bar removed by the build
        with mock.patch.dict(os.environ, {"RADAR_BUNDLE_OUT": "/tmp/x.json.gz"}):
            rb.capture("1D", {"SPY": validated}, {"SPY": data})
        self.assertEqual(len(rb._frames["1D"]["SPY"]), 4)
        self.assertEqual(rb._frames["1D"]["SPY"][-1][4], float(validated.iloc[-1]))

    def test_close_mismatch_is_withheld_not_patched(self):
        data = frame(["SPY"], self.idx, close_shift=0.5)
        validated = frame(["SPY"], self.idx)[("SPY", "Close")]
        with mock.patch.dict(os.environ, {"RADAR_BUNDLE_OUT": "/tmp/x.json.gz"}):
            rb.capture("1D", {"SPY": validated}, {"SPY": data})
        self.assertNotIn("SPY", rb._frames["1D"])
        self.assertIn("differs", rb._withheld["1D"]["SPY"])

    def test_never_written_inside_site(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"RADAR_BUNDLE_OUT": str(Path(d) / "_site" / "b.json.gz")}):
                with self.assertRaises(RuntimeError):
                    rb.write("2026-10-15", "t", {})

    def test_written_bundle_is_deterministic_and_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "b.json.gz"
            with mock.patch.dict(os.environ, {"RADAR_BUNDLE_OUT": str(out)}):
                rb.write("2026-10-15", "t", {"x": 1}); first = out.read_bytes()
                rb.write("2026-10-15", "t", {"x": 1}); second = out.read_bytes()
            self.assertEqual(first, second)
            self.assertEqual(json.loads(gzip.decompress(first))["session"], "2026-10-15")
            self.assertTrue(Path(str(out) + ".sha256").exists())


if __name__ == "__main__":
    unittest.main()
