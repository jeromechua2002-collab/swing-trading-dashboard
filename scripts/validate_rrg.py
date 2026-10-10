#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd

AUDIT = Path("data/rrg-audit.json")
OUT = Path("data/rrg-validation.json")
REFERENCE_DATE = pd.Timestamp("2026-10-09", tz="UTC")

EXACT = {
    "XLK": (101.300, 99.300),
    "SMH": (101.200, 99.100),
}

APPROX = {
    "XLK": (101.300,99.300), "XLE": (100.300,101.401), "XLY": (99.121,101.986),
    "XLC": (98.358,101.253), "XLB": (98.572,100.716), "XLRE": (98.514,100.670),
    "XLP": (98.852,100.725), "XLF": (98.642,100.118), "XLV": (98.601,98.780),
    "XLI": (98.271,98.672), "SMH": (101.200,99.100), "IGV": (101.924,100.028),
    "FDN": (100.534,101.379), "XOP": (100.155,101.343), "TAN": (98.609,101.056),
    "OIH": (98.642,100.710), "XME": (98.740,100.678), "KRE": (98.307,100.085),
    "XRT": (98.851,99.569), "JETS": (97.872,98.834), "ITB": (98.049,98.594),
    "ITA": (98.310,98.486), "IBB": (98.449,98.629),
}

QUADS = {
    "XLK":"Weakening","XLE":"Leading","XLY":"Improving","XLC":"Improving",
    "XLU":"Improving","XLB":"Improving","XLRE":"Improving","XLP":"Improving",
    "XLF":"Improving","XLV":"Lagging","XLI":"Lagging",
    "SMH":"Weakening","IGV":"Leading","FDN":"Leading","XOP":"Leading",
    "TAN":"Improving","OIH":"Improving","XME":"Improving","PBW":"Improving",
    "KRE":"Improving","KIE":"Improving","VNQ":"Improving","XRT":"Lagging",
    "JETS":"Lagging","ITB":"Lagging","ITA":"Lagging","IBB":"Lagging",
}

def wma(s,n):
    if n<=1: return s.copy()
    w=np.arange(1,n+1,dtype=float)
    return s.rolling(n,min_periods=n).apply(lambda x: float(np.dot(x,w)/w.sum()),raw=True)

def z(s,n,ddof=1):
    m=s.rolling(n,min_periods=n).mean()
    sd=s.rolling(n,min_periods=n).std(ddof=ddof).replace(0,np.nan)
    return (s-m)/sd

def pair(asset,bench):
    d=pd.concat([asset.rename("a"),bench.rename("b")],axis=1).dropna()
    return d["a"],d["b"]

def normalized(asset,bench,smooth=10,window=16,roc=5,mom_smooth=4):
    a,b=pair(asset,bench)
    rs=100*a/b
    ratio=100+z(wma(rs,smooth),window,1)
    rate=100*(ratio/ratio.shift(roc)-1)
    mom=100+z(wma(rate,mom_smooth),window,1)
    return pd.DataFrame({"ratio":ratio,"momentum":mom}).dropna()

def roman(asset,bench):
    return normalized(asset,bench,1,14,4,1)

def double_wma14(asset,bench):
    a,b=pair(asset,bench)
    rs=100*a/b
    sm=wma(rs,14)
    ratio=100*sm/wma(sm,14)
    mom=100*ratio/wma(ratio,14)
    return pd.DataFrame({"ratio":ratio,"momentum":mom}).dropna()

def eikon(asset,bench):
    a,b=pair(asset,bench)
    rs=100*a/b
    ratio=100*rs.rolling(10).mean()/rs.rolling(30).mean()
    mom=100*ratio/ratio.rolling(9).mean()
    return pd.DataFrame({"ratio":ratio,"momentum":mom}).dropna()

def forty_ten(asset,bench):
    a,b=pair(asset,bench)
    rs=100*a/b
    ratio=100*rs/rs.rolling(40).mean()
    mom=100*ratio/ratio.shift(10)
    return pd.DataFrame({"ratio":ratio,"momentum":mom}).dropna()

def quadrant(x,y):
    if x>=100 and y>=100:return "Leading"
    if x>=100 and y<100:return "Weakening"
    if x<100 and y>=100:return "Improving"
    return "Lagging"

def load_prices():
    p=json.loads(AUDIT.read_text())
    out={}
    for t,rows in p["prices"].items():
        s=pd.Series({pd.Timestamp(r["time"]):float(r["close"]) for r in rows},dtype=float).sort_index()
        out[t]=s[s.index<=REFERENCE_DATE]
    return out

def score(name,fn,prices):
    bench=prices["SPY"]; heads={}
    for t in QUADS:
        if t not in prices: continue
        c=fn(prices[t],bench)
        if c.empty: continue
        x,y=map(float,c.iloc[-1]); heads[t]=(x,y,quadrant(x,y))
    q=sum(heads.get(t,(0,0,None))[2]==q for t,q in QUADS.items())
    errs=[]
    for t,(rx,ry) in APPROX.items():
        if t in heads:
            x,y,_=heads[t]; errs += [abs(x-rx),abs(y-ry)]
    exact=[]
    for t,(rx,ry) in EXACT.items():
        if t in heads:
            x,y,_=heads[t]; exact += [abs(x-rx),abs(y-ry)]
    return {
        "name":name,
        "quadrant_matches":q,
        "quadrant_total":len(QUADS),
        "quadrant_accuracy_pct":round(100*q/len(QUADS),2),
        "approx_coordinate_mae":round(float(np.mean(errs)),4),
        "exact_tooltip_mae":round(float(np.mean(exact)),4),
        "heads":{t:{"ratio":round(v[0],4),"momentum":round(v[1],4),"quadrant":v[2]} for t,v in heads.items()},
    }

def main():
    prices=load_prices()
    candidates=[
        ("LIVE normalized WMA 10/16/5/4",lambda a,b:normalized(a,b,10,16,5,4)),
        ("Normalized WMA 11/15/5/5",lambda a,b:normalized(a,b,11,15,5,5)),
        ("Normalized WMA 8/18/4/4",lambda a,b:normalized(a,b,8,18,4,4)),
        ("Roman public z-score 14/4",roman),
        ("Double WMA 14",double_wma14),
        ("Community Eikon 10/30/9",eikon),
        ("40-period / 10-lag",forty_ten),
    ]
    reports=[score(n,f,prices) for n,f in candidates]
    ranked=sorted(reports,key=lambda r:(-r["quadrant_matches"],r["approx_coordinate_mae"],r["exact_tooltip_mae"]))
    out={
        "reference_date":"2026-10-09",
        "benchmark":"SPY",
        "reference_source":"User-provided EdgeRater Daily screenshots",
        "live_formula":"LIVE normalized WMA 10/16/5/4",
        "limitations":[
            "Exact EdgeRater/JdK internals are proprietary.",
            "Only XLK and SMH have exact tooltip coordinates.",
            "Other coordinates are approximate screenshot-derived readings.",
            "This validates heads/quadrants; full tail validation needs more dated snapshots."
        ],
        "ranking":[{k:r[k] for k in ("name","quadrant_matches","quadrant_total","quadrant_accuracy_pct","approx_coordinate_mae","exact_tooltip_mae")} for r in ranked],
        "candidates":reports,
    }
    OUT.write_text(json.dumps(out,indent=2))
    for r in ranked:
        print(f'{r["name"]}: quadrants {r["quadrant_matches"]}/{r["quadrant_total"]}; approx MAE {r["approx_coordinate_mae"]:.4f}; exact MAE {r["exact_tooltip_mae"]:.4f}')
    live=next(r for r in reports if r["name"]==out["live_formula"])
    failures=[]
    if live["quadrant_matches"]<25: failures.append(f'quadrants {live["quadrant_matches"]}/27')
    if live["approx_coordinate_mae"]>0.35: failures.append(f'approx MAE {live["approx_coordinate_mae"]}')
    if live["exact_tooltip_mae"]>0.30: failures.append(f'exact MAE {live["exact_tooltip_mae"]}')
    if failures:
        raise SystemExit("RRG validation FAILED: "+"; ".join(failures))
    print("RRG validation PASSED")

if __name__=="__main__":
    main()
