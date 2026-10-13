import unittest
from audit_rrg_reference_daily import quadrant,trail_summary

class RRGReferenceTests(unittest.TestCase):
    def trail(self,ends=None):
        out=[{"time":f"2026-10-{d:02d}T00:00:00Z","ratio":100.6,"momentum":100.5} for d in range(1,17)]
        if ends:
            for d,ratio,momentum in ends:out[d-1].update({"ratio":ratio,"momentum":momentum})
        return out
    def test_quadrants(self):
        for xy,q in [((101,101),"Leading"),((101,99),"Weakening"),((99,101),"Improving"),((99,99),"Lagging")]:
            self.assertEqual(quadrant({"ratio":xy[0],"momentum":xy[1]}),q)
    def test_quadrant_crossing_is_date_specific(self):
        tail=self.trail([(12,100.8,100.4),(13,100.8,99.9),(14,100.7,99.6)])
        result=trail_summary(tail,"2026-10-13")
        self.assertEqual(result["reference_quadrant"],"Weakening")
        self.assertEqual(result["latest_date"],"2026-10-16")
        self.assertTrue(any(x["date"]=="2026-10-13" for x in result["crossings"]))
    def test_reference_not_available(self):
        t=self.trail()
        out=trail_summary(t,"2026-10-17")
        self.assertFalse(out["reference_present"])
        self.assertIsNone(out["reference_quadrant"])
    def test_duplicate_bar_rejected(self):
        t=self.trail();t[-1]["time"]=t[-2]["time"]
        with self.assertRaisesRegex(ValueError,"Non-unique"):trail_summary(t,"2026-10-13")
    def test_backwards_dates_rejected(self):
        t=self.trail();t[4],t[5]=t[5],t[4]
        with self.assertRaisesRegex(ValueError,"Non-unique"):trail_summary(t,"2026-10-13")
    def test_short_tail_rejected(self):
        with self.assertRaisesRegex(ValueError,"Expected 16"):trail_summary(self.trail()[:13],"2026-10-13")
    def test_tail_direction(self):
        t=self.trail([(15,100,100),(16,100.5,99.6)])
        self.assertEqual(trail_summary(t,"2026-10-13")["last_step_direction"],"SE")
if __name__=="__main__":unittest.main()
