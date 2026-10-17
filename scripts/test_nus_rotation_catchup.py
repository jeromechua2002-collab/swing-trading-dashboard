"""Rotation catch-up planning: key matching, inactive rows, duplicates. Synthetic data."""
import unittest

import nus_rotation_catchup as rc


def chart(series, date, value, page_id=None):
    return {"id": page_id or series, "properties": {
        "Series": {"type": "title", "title": [{"plain_text": series}]},
        "Date": {"type": "date", "date": {"start": date} if date else None},
        "Relative Performance %": {"type": "number", "number": value}}}


FIELDS = ["Series", "Date", "Relative Performance %"]


class Plan(unittest.TestCase):
    def test_counts_create_update_unchanged(self):
        prod = [chart("A|5D|00", "2026-10-14", 1.0), chart("B|5D|00", "2026-10-14", 2.0), chart("C|5D|00", "2026-10-14", 3.0)]
        nus = [chart("A|5D|00", "2026-10-14", 1.0, "n1"), chart("B|5D|00", "2026-10-13", 2.0, "n2")]
        p = rc.plan_role(prod, nus, "Series", FIELDS)
        self.assertEqual((len(p["create"]), len(p["update"]), p["unchanged"], p["nus_only"]), (1, 1, 1, 0))
        self.assertEqual(p["update"][0][0], "n2")

    def test_inactive_rows_counted_and_compared(self):
        prod = [chart("A|20D|00", None, None)]
        nus = [chart("A|20D|00", "2026-10-13", 1.5, "n1")]
        p = rc.plan_role(prod, nus, "Series", FIELDS)
        self.assertEqual((p["inactive_prod"], p["inactive_nus"], len(p["update"])), (1, 0, 1))

    def test_nus_only_keys_reported_never_deleted(self):
        p = rc.plan_role([chart("A|5D|00", "2026-10-14", 1.0)], [chart("A|5D|00", "2026-10-14", 1.0, "n1"),
                                                              chart("Z|5D|00", "2026-10-14", 9.0, "n9")], "Series", FIELDS)
        self.assertEqual((p["nus_only"], len(p["create"]), len(p["update"])), (1, 0, 0))

    def test_duplicate_keys_stop(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate keys"):
            rc.plan_role([chart("A|5D|00", "2026-10-14", 1.0)], [chart("A|5D|00", "2026-10-14", 1.0, "n1"),
                                                              chart("A|5D|00", "2026-10-14", 1.0, "n2")], "Series", FIELDS)

    def test_writable_rejects_unknown_types(self):
        with self.assertRaises(RuntimeError):
            rc.writable({"type": "relation", "relation": []})


if __name__ == "__main__":
    unittest.main()
