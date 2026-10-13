import unittest, numpy as np, pandas as pd
from price_context import summarize_closes

class PriceContextTests(unittest.TestCase):
    def setUp(self):
        self.i=pd.date_range("2026-07-01",periods=80,freq="B",tz="UTC")
    def test_uptrend(self):
        s=pd.Series(np.linspace(90,150,80),index=self.i)
        x=summarize_closes(s)
        self.assertEqual(x["state"],"Uptrend")
        self.assertGreater(x["return5_pct"],0)
        self.assertTrue(x["ema10_rising"])
        self.assertGreater(x["close"],x["prior20_close_high"])
        self.assertEqual(x["session"],self.i[-1].date().isoformat())
    def test_downtrend(self):
        x=summarize_closes(pd.Series(np.linspace(160,90,80),index=self.i))
        self.assertEqual(x["state"],"Downtrend")
        self.assertLess(x["return5_pct"],0)
    def test_mixed(self):
        s=pd.Series(np.ones(80)*100,index=self.i)
        self.assertEqual(summarize_closes(s)["state"],"Mixed")
    def test_invalid_values(self):
        s=pd.Series(np.linspace(90,150,80),index=self.i)
        s.iloc[-5]=0
        with self.assertRaises(ValueError):summarize_closes(s)
        s.iloc[-5]=np.inf
        # Infinities must be rejected, not silently discarded as missing values.
        with self.assertRaises(ValueError):summarize_closes(s)
    def test_history_missing(self):
        with self.assertRaises(ValueError):summarize_closes(pd.Series(range(20),index=self.i[:20]))
    def test_duplicate_dates(self):
        s=pd.Series(np.ones(81)*100,index=list(self.i)+[self.i[-1]])
        with self.assertRaises(ValueError):summarize_closes(s)
    def test_only_past_bars_define_prior_high(self):
        s=pd.Series(np.ones(80)*100,index=self.i);s.iloc[-1]=130
        x=summarize_closes(s)
        self.assertEqual(x["prior20_close_high"],100.0)
        self.assertAlmostEqual(x["distance_to_prior20_close_high_pct"],30.0)
if __name__=="__main__":unittest.main()
