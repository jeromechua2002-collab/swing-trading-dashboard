"""Fail-closed full-universe audit of generated RRG and equal-weight data."""
import json
from pathlib import Path
from build_rrg_data import SECTOR_GROUPS,INDUSTRY_GROUPS,STOCK_GROUPS,EXPECTED_STOCKS

def load(path):
    p=Path(path)
    if not p.exists(): raise ValueError(f"Missing generated asset: {path}")
    return json.loads(p.read_text(encoding="utf-8"))
def check_trail(trail,ticker,tf,label):
    if not isinstance(trail,list) or len(trail)!=16: raise ValueError(f"{tf} {label} {ticker}: expected 16 points")
    dates=[x["time"] for x in trail]
    if dates!=sorted(set(dates)): raise ValueError(f"{tf} {label} {ticker}: duplicate or nonmonotonic dates")
    for p in trail:
        for k in ("ratio","momentum"):
            import math
            if not isinstance(p.get(k),(float,int)) or not math.isfinite(p[k]):
                raise ValueError(f"{tf} {label} {ticker}: invalid {k}")
def main():
    d=load("data/rrg-core.json")
    sectors=set(sum(SECTOR_GROUPS.values(),[]))
    industries=set(sum(INDUSTRY_GROUPS.values(),[]))
    stocks=set(sum(STOCK_GROUPS.values(),[]))
    assert len(sectors)==11 and len(industries)==16 and len(stocks)==len(EXPECTED_STOCKS)
    assert d["universes"]["stock_members"]==STOCK_GROUPS
    import math
    total=0
    price_checks=0
    for tf in ("1W","1D","4H","1H"):
        block=d["timeframes"][tf]
        for group,expected in (("sectors",sectors),("industries",industries)):
            actual=block[group]
            if set(actual)!=expected: raise ValueError(f"{tf}: missing or extra {group}: {expected.symmetric_difference(actual)}")
            for ticker,trail in actual.items():check_trail(trail,ticker,tf,group);total+=1
        for sector,members in STOCK_GROUPS.items():
            doc=load(f"data/stocks/{sector}.json")
            if doc["members"]!=members: raise ValueError(f"{sector}: mismatched stock membership")
            sub=doc["timeframes"][tf]["stock"]
            if tf in ("1D","4H"):
                ctx=doc["timeframes"][tf].get("price_context", {})
                if set(ctx)!=set(members):
                    raise ValueError(f"{tf} {sector} incomplete price context: {set(members)^set(ctx)}")
                expected_session=block["benchmark_price"][-1]["time"][:10]
                for ticker,p in ctx.items():
                    if p["session"]!=expected_session:raise ValueError(f"{tf} {sector} {ticker} mismatched price session")
                    if p["state"] not in ("Uptrend","Downtrend","Mixed"):raise ValueError(f"{ticker} unknown absolute trend")
                    for key in ("close","ema10","ema20","prior20_close_high","prior20_close_low","return5_pct","return20_pct"):
                        if not isinstance(p.get(key),(float,int)) or not math.isfinite(p[key]):raise ValueError(f"{ticker} invalid {key}")
                    if min(p["close"],p["ema10"],p["ema20"])<=0:raise ValueError(f"{ticker} invalid nonpositive price")
                    price_checks+=1
            for basis in ("vs_SPY",f"vs_{sector}"):
                actual=sub.get(basis,{})
                if set(actual)!=set(members): raise ValueError(f"{tf} {sector}: missing/extra {basis}: {set(members)^set(actual)}")
                for ticker,trail in actual.items():check_trail(trail,ticker,tf,basis);total+=1
    b=load("data/sector-breadth.json")
    pairs={"XLK":"RSPT","XLY":"RSPD","XLC":"RSPC","XLU":"RSPU","XLRE":"RSPR","XLP":"RSPS","XLI":"RSPN","XLB":"RSPM","XLF":"RSPF","XLV":"RSPH","XLE":"RSPG"}
    if b.get("status")!="ok" or {x["cap"]:x["equal"] for x in b.get("rows",[])}!=pairs:raise ValueError("Sector breadth does not cover 11 matching pairs")
    from datetime import datetime,timezone
    updated=datetime.fromisoformat(b["generated_at"])
    if updated.tzinfo is None or abs((datetime.now(timezone.utc)-updated).total_seconds())>3600:raise ValueError("Breadth generated timestamp invalid")
    sessions=b["prices"]["SPY"]
    if len(sessions)<100 or sessions[-1]["time"]!=b["as_of"]:raise ValueError("Breadth sessions missing/stale")
    dates=[r["time"] for r in sessions]
    import math
    for t in ("SPY","RSP",*pairs.keys(),*pairs.values()):
        x=b["prices"].get(t,[])
        if [r["time"] for r in x]!=dates or any(not math.isfinite(r["close"]) or r["close"]<=0 for r in x):
            raise ValueError(f"Breadth price history invalid/misaligned: {t}")
    for r in b["rows"]:
        for key in ("5","10","20","60"):
            m=r["metrics"][key]
            if not all(math.isfinite(m[v]) for v in ("cap_vs_spy","equal_vs_spy","equal_vs_cap","equal_vs_rsp","ratio_slope_5d")):raise ValueError(f"{r['cap']}: invalid metrics for {key}")
        for k,t in (("cap_vs_SPY",r["cap"]),("equal_vs_SPY",r["equal"]),("equal_vs_RSP",r["equal"])):
            check_trail(b["rrg"][k][t],t,"1D",k)
            if b["rrg"][k][t][-1]["time"][:10]!=b["as_of"]:raise ValueError("Breadth RRG date mismatch")
    print(f"FULL MARKET AUDIT PASSED: 4 timeframes, 11 sectors, 16 industries, {len(stocks)} unique stocks, {total} RRG trail checks, 11 equal-weight pairs, 23 raw/adjusted price histories and 44 window comparisons, {price_checks} absolute-price/timeframe checks")
if __name__=="__main__":main()
