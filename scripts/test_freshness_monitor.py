"""Freshness monitor: expected session with a post-close grace period. Offline."""
import unittest
from datetime import datetime, timezone

import exchange_calendars as xcals

import freshness_monitor as fm

NYSE = xcals.get_calendar("XNYS")


class Expected(unittest.TestCase):
    def test_before_grace_expects_previous_session(self):
        # Thu 15 Oct 2026 closes 20:00 UTC; at 23:00 UTC the grace has not passed.
        self.assertEqual(fm.expected_session(datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc), NYSE), "2026-10-14")

    def test_after_grace_expects_that_session(self):
        self.assertEqual(fm.expected_session(datetime(2026, 10, 16, 2, 30, tzinfo=timezone.utc), NYSE), "2026-10-15")

    def test_weekend_expects_friday(self):
        self.assertEqual(fm.expected_session(datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc), NYSE), "2026-10-16")

    def test_stale_and_missing_systems_flagged(self):
        r = dict((n, s) for s, n, _ in fm.evaluate("2026-10-15", {"a": "2026-10-15", "b": "2026-10-14", "c": None}))
        self.assertEqual(r, {"a": "OK", "b": "STALE", "c": "STALE"})


if __name__ == "__main__":
    unittest.main()
