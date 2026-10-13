"""Completed-bar policy: only bars whose END has passed (NYSE calendar) are published.

Frozen-clock, offline tests. Covers the 2026-10-13 13:04 ET build that published
forming 1H/4H/1W points, plus holidays, early closes and DST.
"""
import unittest

import numpy as np
import pandas as pd

from build_rrg_data import (completed_only, daily_bar_end, hourly_bar_end, synthetic_hour_bars,
                            weekly_bar_end)

NY = "America/New_York"


def et(s):
    return pd.Timestamp(s, tz=NY)


def hourly(day, last="15:30"):
    idx = pd.date_range(f"{day} 09:30", f"{day} {last}", freq="1h", tz=NY)
    return pd.Series(np.arange(1, len(idx) + 1, dtype=float), index=idx)


def daily(*days):
    return pd.Series(np.arange(1, len(days) + 1, dtype=float), index=pd.to_datetime(list(days)))


def weekly(*mondays):
    return pd.Series(np.arange(1, len(mondays) + 1, dtype=float), index=pd.to_datetime(list(mondays)))


class HourlyBars(unittest.TestCase):
    def test_observed_defect_forming_bar_dropped(self):
        # Yahoo at 13:04 ET returns 09:30..12:30; the 12:30 bar is still forming.
        raw = hourly("2026-10-13", last="12:30")
        out = completed_only(raw, "1h", et("2026-10-13 13:04:38"))
        self.assertEqual(out.index[-1], et("2026-10-13 11:30"))

    def test_bar_final_exactly_at_its_end(self):
        raw = hourly("2026-10-13")
        self.assertEqual(len(completed_only(raw, "1h", et("2026-10-13 13:29:59"))), 3)
        self.assertEqual(len(completed_only(raw, "1h", et("2026-10-13 13:30"))), 4)

    def test_last_regular_bar_ends_at_close(self):
        self.assertEqual(hourly_bar_end(et("2026-10-13 15:30")), et("2026-10-13 16:00"))

    def test_early_close_day(self):
        # 2026-11-27 (day after Thanksgiving) closes 13:00 ET: the 12:30 bar ends 13:00.
        self.assertEqual(hourly_bar_end(et("2026-11-27 12:30")), et("2026-11-27 13:00"))
        raw = hourly("2026-11-27", last="12:30")
        self.assertEqual(len(completed_only(raw, "1h", et("2026-11-27 13:00"))), 4)

    def test_dst_boundary(self):
        # US DST ended 2026-11-01; 09:30 ET on 2026-11-02 is 14:30 UTC.
        self.assertEqual(hourly_bar_end(pd.Timestamp("2026-11-02 14:30", tz="UTC")), et("2026-11-02 10:30"))


class FourHourBars(unittest.TestCase):
    def test_observed_defect_4h_not_published_mid_bucket(self):
        raw = hourly("2026-10-13", last="12:30")
        self.assertEqual(str(synthetic_hour_bars(raw, 4).index[-1]), "2026-10-13 12:30:00-04:00")  # old behaviour
        fixed = synthetic_hour_bars(completed_only(raw, "1h", et("2026-10-13 13:04:38")), 4)
        self.assertTrue(fixed.empty)

    def test_buckets_publish_only_after_they_end(self):
        raw = hourly("2026-10-13")
        at = lambda t: synthetic_hour_bars(completed_only(raw, "1h", et(t)), 4)
        self.assertEqual(len(at("2026-10-13 13:29")), 0)
        self.assertEqual(len(at("2026-10-13 13:30")), 1)
        self.assertEqual(len(at("2026-10-13 15:59")), 1)   # 13:30-16:00 bucket still forming
        self.assertEqual(len(at("2026-10-13 16:00")), 2)

    def test_early_close_publishes_first_bucket_only(self):
        raw = hourly("2026-11-27", last="12:30")
        out = synthetic_hour_bars(completed_only(raw, "1h", et("2026-11-27 13:00")), 4)
        self.assertEqual(len(out), 1)


class DailyBars(unittest.TestCase):
    def test_regular_close_plus_settle(self):
        self.assertEqual(daily_bar_end("2026-10-13"), et("2026-10-13 16:15"))
        raw = daily("2026-10-12", "2026-10-13")
        self.assertEqual(len(completed_only(raw, "1d", et("2026-10-13 16:14"))), 1)
        self.assertEqual(len(completed_only(raw, "1d", et("2026-10-13 16:15"))), 2)

    def test_early_close_settles_earlier(self):
        self.assertEqual(daily_bar_end("2026-11-27"), et("2026-11-27 13:15"))

    def test_utc_midnight_labels(self):
        self.assertEqual(daily_bar_end(pd.Timestamp("2026-10-12", tz="UTC")), et("2026-10-12 16:15"))

    def test_non_session_label_waits_for_day_end(self):
        self.assertEqual(daily_bar_end("2026-11-26"), et("2026-11-27 00:00"))  # Thanksgiving


class WeeklyBars(unittest.TestCase):
    def test_observed_defect_current_week_dropped(self):
        raw = weekly("2026-10-05", "2026-10-12")
        out = completed_only(raw, "1wk", et("2026-10-13 13:04"))
        self.assertEqual(list(out.index), [pd.Timestamp("2026-10-05")])

    def test_week_final_after_friday_close(self):
        raw = weekly("2026-10-05", "2026-10-12")
        self.assertEqual(len(completed_only(raw, "1wk", et("2026-10-16 16:14"))), 1)
        self.assertEqual(len(completed_only(raw, "1wk", et("2026-10-16 16:15"))), 2)

    def test_thanksgiving_week_ends_on_early_close_friday(self):
        self.assertEqual(weekly_bar_end("2026-11-23"), et("2026-11-27 13:15"))

    def test_good_friday_week_ends_thursday(self):
        self.assertEqual(weekly_bar_end("2027-03-22"), et("2027-03-25 16:15"))  # Good Friday 2027-03-26

    def test_monday_holiday_week(self):
        self.assertEqual(weekly_bar_end("2027-01-18"), et("2027-01-22 16:15"))  # MLK Day Monday

    def test_label_not_on_monday(self):
        self.assertEqual(weekly_bar_end("2027-01-19"), weekly_bar_end("2027-01-18"))


if __name__ == "__main__":
    unittest.main()
