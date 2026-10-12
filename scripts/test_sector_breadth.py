import unittest
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from build_sector_breadth import PAIRS, compare_snapshot, classify, completed_cutoff

class BreadthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,12,17,tzinfo=timezone.utc)
        dates=pd.bdate_range(end='2026-10-12',periods=160,tz='UTC')
        self.raw={}
        for i,t in enumerate(['SPY','RSP',*PAIRS,*[v[0] for v in PAIRS.values()]]):
            x=np.arange(len(dates)); self.raw[t]=pd.Series(100*np.exp((.0005+i*.00003)*x+.003*np.sin(x/(5+i*.1))),index=dates)
        self.audit={'generated_at':self.now.isoformat(),'prices':{t:[{'time':d.isoformat(),'close':v} for d,v in self.raw[t].items()] for t in ['SPY',*PAIRS]}}
    def test_states(self):
        for c,e,want in [(2,1,'Broad leadership'),(1,-1,'Heavyweight-led'),(-1,1,'Broadening under the surface'),(-2,-1,'Broad weakness'),(.1,2,'Mixed / transition')]:
            self.assertEqual(classify(c,e)[0],want)
    def test_partial_session_excluded(self):
        p=compare_snapshot(self.audit,self.raw,self.raw,self.now)
        self.assertEqual(p['status'],'ok');self.assertEqual(p['as_of'],'2026-10-09');self.assertEqual(len(p['rows']),11)
        self.assertEqual(p['rrg']['equal_vs_SPY']['RSPT'][-1]['time'][:10],'2026-10-09')
    def test_latest_missing_rejected(self):
        self.raw['RSPT']=self.raw['RSPT'].iloc[:-2]
        with self.assertRaisesRegex(ValueError,'RSPT'):compare_snapshot(self.audit,self.raw,self.raw,self.now)
    def test_internal_missing_session_rejected(self):
        self.raw['RSPT']=self.raw['RSPT'].drop(self.raw['RSPT'].index[-10])
        self.assertEqual(compare_snapshot(self.audit,self.raw,self.raw,self.now)['status'],'incomplete')
    def test_stale_snapshot_rejected(self):
        with self.assertRaisesRegex(ValueError,'stale'):compare_snapshot(self.audit,self.raw,self.raw,datetime(2026,10,20,tzinfo=timezone.utc))
    def test_revised_cap_close_rejected(self):
        self.raw['XLK'].iloc[-2]*=1.05
        p=compare_snapshot(self.audit,self.raw,self.raw,self.now)
        self.assertEqual(p['status'],'incomplete');self.assertIn('changed',p['errors'][0])
    def test_window_formula(self):
        p=compare_snapshot(self.audit,self.raw,self.raw,self.now)
        m=p['rows'][0]['metrics']['20'];c=self.raw['XLK'].iloc[:-1];e=self.raw['RSPT'].iloc[:-1]
        want=100*((e.iloc[-1]/e.iloc[-21])/(c.iloc[-1]/c.iloc[-21])-1)
        self.assertAlmostEqual(m['equal_vs_cap'],want,places=3)
    def test_cutoff_dst(self):
        self.assertEqual(str(completed_cutoff(datetime(2026,11,5,21,14,tzinfo=timezone.utc)).date()),'2026-11-04')
        self.assertEqual(str(completed_cutoff(datetime(2026,11,5,21,15,tzinfo=timezone.utc)).date()),'2026-11-05')
if __name__=='__main__':unittest.main()
