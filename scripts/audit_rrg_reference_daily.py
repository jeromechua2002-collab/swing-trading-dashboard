"""Dated comparison of our *public approximation* with supplied EdgeRater screenshots.

Do not use endpoints from a different session or claim exact JdK/EdgeRater
parity. Reference quadrant labels are screen-read observations, not proprietary
numeric coordinates. Every sector, industry and stock trail is still checked.
"""
import json
from datetime import date
from pathlib import Path

REF_DAY = "2026-10-13"
REF_SOURCE = "User EdgeRater daily screenshots dated 2026-10-13; quadrant observations only"
REFERENCE = {
    "sectors": {
        "XLK": "Weakening", "XLE": "Leading", "XLV": "Lagging",
        "XLI": "Lagging", "XLC": "Improving", "XLP": "Improving",
        "XLF": "Improving", "XLB": "Improving", "XLRE": "Improving",
        "XLY": "Improving", "XLU": "Leading",
    },
    "industries": {
        "IGV": "Weakening", "SMH": "Weakening",
        "FDN": "Leading", "XOP": "Leading",
        "IBB": "Lagging", "JETS": "Lagging",
        "KRE": "Lagging", "XRT": "Improving",
    },
}

def quadrant(pt):
    x, y = pt["ratio"], pt["momentum"]
    if x >= 100: return "Leading" if y >= 100 else "Weakening"
    return "Improving" if y >= 100 else "Lagging"

def trail_summary(trail, reference_day):
    if len(trail) != 16: raise ValueError("Expected 16 dated RRG points")
    dates=[pt["time"][:10] for pt in trail]
    if dates != sorted(set(dates)):
        raise ValueError(f"Non-unique or non-increasing tail dates: {dates}")
    for pt in trail:
        if not isinstance(pt["ratio"],(float,int)) or not isinstance(pt["momentum"],(float,int)):
            raise ValueError("Non-numeric RRG coordinate")
    heads=[(p["time"][:10],quadrant(p)) for p in trail]
    latest=trail[-1]
    prior=trail[-2]
    arrow=("N" if latest["momentum"]>prior["momentum"] else "S" if latest["momentum"]<prior["momentum"] else "") + ("E" if latest["ratio"]>prior["ratio"] else "W" if latest["ratio"]<prior["ratio"] else "")
    selected=next((p for p in trail if p["time"][:10]==reference_day),None)
    switches=[{"date":d,"from":heads[i-1][1],"to":q} for i,(d,q) in enumerate(heads) if i and heads[i-1][1]!=q]
    return {
        "latest_date":dates[-1], "latest_quadrant":quadrant(latest),
        "last_step_direction":arrow or "Flat", "crossings":switches,
        "reference_present":selected is not None,
        "reference_quadrant":quadrant(selected) if selected else None,
    }

def audit(base=Path("."), reference_date=REF_DAY, reference=REFERENCE):
    base=Path(base)
    core=json.loads((base/"data/rrg-core.json").read_text())
    benchmark=core["timeframes"]["1D"]["benchmark_price"]
    daily_day=benchmark[-1]["time"][:10]
    today=date.fromisoformat(reference_date)
    if date.fromisoformat(daily_day)>today:
        # Still find the reference point in the 16-bar trails.
        pass
    buckets={}
    for group in ("sectors","industries"):
        trails=core["timeframes"]["1D"][group]
        expected=11 if group=="sectors" else 16
        if len(trails)!=expected:raise ValueError(f"{group} coverage {len(trails)}/{expected}")
        rec={}
        for t,series in trails.items():
            d=trail_summary(series,reference_date)
            if d["latest_date"]!=daily_day:raise ValueError(f"{group}/{t} stale head {d['latest_date']} vs {daily_day}")
            if t in reference[group]:
                d["screenshot_quadrant"]=reference[group][t]
                d["same_date"]=bool(d["reference_present"])
                d["matches_screenshot"]=d["reference_quadrant"]==reference[group][t] if d["same_date"] else None
            rec[t]=d
        buckets[group]=rec
    stock_count=0
    stock_check={}
    sectors=core["universes"]["stock_members"]
    for sector, members in sectors.items():
        file=json.loads((base/f"data/stocks/{sector}.json").read_text())
        stock_check[sector]={}
        if file["generated_at"]!=core["generated_at"] or file["members"]!=members:
            raise ValueError(f"Stock members/generation mismatch: {sector}")
        for tf in ("1D","4H"):
            frame=file["timeframes"][tf]
            benchmark_day=frame["benchmark_price"][-1]["time"][:10]
            for basis in ("vs_SPY",f"vs_{sector}"):
                mapping=frame["stock"][basis]
                if set(mapping)!=set(members):raise ValueError(f"Stock comparison {sector}/{tf}/{basis} incomplete")
                for stock,trail in mapping.items():
                    result=trail_summary(trail,reference_date)
                    if result["latest_date"]!=benchmark_day:
                        raise ValueError(f"Stock {stock}/{tf}/{basis} head {result['latest_date']} != {benchmark_day}")
            stock_check[sector][tf]=benchmark_day
        stock_count+=len(members)
    if stock_count!=116:raise ValueError(f"Stock total {stock_count} != 116")
    sampled={g:{k:{"actual":v["reference_quadrant"],"expected":v["screenshot_quadrant"],"match":v["matches_screenshot"],"crossings":v["crossings"],"direction":v["last_step_direction"]} for k,v in buckets[g].items() if k in reference[g]} for g in reference}
    checked=sum(1 for g in sampled.values() for t in g.values() if t["match"] is not None)
    matches=sum(t["match"] is True for g in sampled.values() for t in g.values())
    mismatches=[{"group":g,"ticker":t,**d} for g,grp in sampled.items() for t,d in grp.items() if d["match"] is False]
    state=("REF_NOT_YET_AVAILABLE" if daily_day<reference_date else "REF_OUTSIDE_TRAIL" if checked==0 else "SAME_DATE_DIVERGENCES" if mismatches else "SAME_DATE_QUADRANTS_AGREE")
    return {"reference_date":reference_date,"reference_source":REF_SOURCE,"source_quality":"screenshot qualitative quadrant only; not exact numeric head or full-tail verification",
            "feed_daily_session":daily_day,"status":state,"compared":checked,"matches":matches,"mismatches":mismatches,
            "market_coverage":{"sectors":len(buckets["sectors"]),"industries":len(buckets["industries"]),"stocks":stock_count},
            "reference_details":sampled,"all_etf_heads":{g:{k:{"quadrant":v["latest_quadrant"],"direction":v["last_step_direction"],"latest_date":v["latest_date"],"crossings":v["crossings"]} for k,v in entries.items()} for g,entries in buckets.items()},
            "stock_sessions":stock_check,
            "interpretation":("Cannot judge indicator lag against EdgeRater October 13 until the October 13 completed daily bar is included." if checked==0 else "Matching date comparison performed; mismatches are flagged and must not be described as validated parity.")}

if __name__=="__main__":
    report=audit()
    path=Path("data/rrg-reference-trajectory-audit.json")
    path.write_text(json.dumps(report,indent=2)+"\n")
    print("REFERENCE TRAJECTORY AUDIT:",report["status"],"daily",report["feed_daily_session"],"reference",report["reference_date"],
          "ETF comparisons",report["compared"],"matches",report["matches"],"disagreements",len(report["mismatches"]),
          "stocks",report["market_coverage"]["stocks"])
    for item in report["mismatches"]:
        print(f"::warning::EdgeRater screenshot divergence {item['group']}/{item['ticker']}: model {item['actual']} vs screenshot {item['expected']} on {report['reference_date']}")
