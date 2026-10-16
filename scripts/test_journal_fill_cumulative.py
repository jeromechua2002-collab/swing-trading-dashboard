"""Cumulative P/L fill: running total from the journal, blanks only, no silent overwrite. Synthetic data."""
import unittest

import journal_fill_cumulative as fc


def row(n, net, cum, status="Closed"):
    return {"id": f"p{n}", "properties": {
        "Trade #": {"type": "number", "number": n}, "Trade Status": {"type": "select", "select": {"name": status}},
        "Broker Net P/L USD": {"type": "number", "number": net}, "Cumulative P/L": {"type": "number", "number": cum}}}


class Fill(unittest.TestCase):
    def test_running_total_from_previous_trade(self):
        rows = [row(10, 5.0, 100.0), row(11, 10.5, None), row(12, -20.25, None)]
        self.assertEqual([(n, v, b) for n, _, v, b in fc.plan(rows, [11.0, 12.0])], [(11.0, 110.5, True), (12.0, 90.25, True)])

    def test_matching_existing_value_is_skipped(self):
        rows = [row(10, 5.0, 100.0), row(11, 10.5, 110.5)]
        self.assertEqual(fc.plan(rows, [11.0])[0][3], False)

    def test_conflicting_existing_value_stops(self):
        with self.assertRaisesRegex(RuntimeError, "different cumulative"):
            fc.plan([row(10, 5.0, 100.0), row(11, 10.5, 999.0)], [11.0])

    def test_open_trade_or_missing_predecessor_stops(self):
        with self.assertRaisesRegex(RuntimeError, "not closed"):
            fc.plan([row(10, 5.0, 100.0), row(11, None, None, "Open")], [11.0])
        with self.assertRaisesRegex(RuntimeError, "predecessor"):
            fc.plan([row(11, 10.5, None)], [11.0])


if __name__ == "__main__":
    unittest.main()
