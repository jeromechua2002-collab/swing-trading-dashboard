#!/usr/bin/env python3
"""Export verified closed trades from Notion for the Pages equity/calendar views."""
import json, os, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DS = os.environ.get("NOTION_TRADES_DS", "bdf1e381-ccd7-820d-b18c-07a3337c985f")
ACCOUNT_ID = os.environ.get("NOTION_SWING_ACCOUNT_ID", "3f41e381ccd781529418f3214d1518f8")
API = "https://api.notion.com/v1"
START_CAPITAL = 5000.0

def api(method, url, payload=None):
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN absent; cannot publish current journal data")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Notion HTTP {exc.code}: {exc.read(450).decode(errors='replace')}") from exc

def text(prop):
    if not prop: return ""
    return "".join(x.get("plain_text","") for x in prop.get("title",prop.get("rich_text",[])))

def number(prop):
    return prop.get("number") if prop else None

def date(prop):
    return (prop.get("date") or {}).get("start","")[:10] if prop else ""

def sel(prop):
    return (prop.get("select") or {}).get("name","") if prop else ""

def related(prop):
    return {r.get("id","").replace("-","") for r in prop.get("relation",[])} if prop else set()

def fetch_all():
    rows=[]; cursor=None
    while True:
        payload={"page_size":100}
        if cursor: payload["start_cursor"]=cursor
        obj=api("POST", f"{API}/data_sources/{DS}/query",payload)
        rows.extend(obj.get("results",[]))
        if not obj.get("has_more"): break
        cursor=obj.get("next_cursor")
        if not cursor: raise RuntimeError("Notion pagination cursor missing")
    return rows

def export():
    rows=fetch_all()
    trades=[]; opened=[]; seen=set()
    for row in rows:
        p=row.get("properties",{})
        status=sel(p.get("Trade Status"))
        if status not in ("Closed","Open"): continue
        symbol=text(p.get("Symbol"))
        if not symbol: raise RuntimeError("Trade with no symbol")
        linked=related(p.get("Account"))
        # Ignore unlinked, provisional and archived entries.
        if ACCOUNT_ID.replace("-","") not in linked: continue
        entry=date(p.get("Entry Date"))
        qty=number(p.get("Position Size"))
        number_id=number(p.get("Trade #"))
        if not number_id or number_id in seen: raise RuntimeError("Missing or duplicate trade number in linked account")
        seen.add(number_id)
        item={"id":row["id"],"number":int(number_id),"symbol":symbol,
              "status":status,"entry_date":entry,"size":qty,
              "entry_price":number(p.get("Avg Entry")),
              "url":row.get("url","")}
        if status=="Open":
            opened.append(item)
            continue
        exitdate=date(p.get("Exit Date"))
        net=number(p.get("Broker Net P/L USD"))
        fx=number(p.get("FX USD/SGD"))
        if not exitdate or net is None:
            raise RuntimeError(f"Closed trade #{number_id} {symbol} has no exit date or net broker P/L")
        if fx is None or fx<=0: raise RuntimeError(f"Missing FX on closed trade #{number_id}")
        item.update({"exit_date":exitdate,"net_usd":round(net,2),
                     "fx":fx,"net_sgd":round(net*fx,2)})
        trades.append(item)
    if len(trades)<7: raise RuntimeError("Fewer than seven historical closed trades; refusing to publish incomplete account history")
    trades.sort(key=lambda x:(x["exit_date"],x["number"]))
    opened.sort(key=lambda x:x["number"])
    equity=START_CAPITAL
    points=[{"date":"2026-09-30","equity_sgd":equity,"number":0,"symbol":"Start","net_sgd":0}]
    for t in trades:
        equity=round(equity+t["net_sgd"],2)
        points.append({"date":t["exit_date"],"equity_sgd":equity,"number":t["number"],"symbol":t["symbol"],"net_sgd":t["net_sgd"]})
    daily=defaultdict(lambda:{"net_sgd":0,"trades":[]})
    for t in trades:
        d=daily[t["exit_date"]]
        d["net_sgd"]=round(d["net_sgd"]+t["net_sgd"],2)
        d["trades"].append({"symbol":t["symbol"],"net_sgd":t["net_sgd"],"number":t["number"]})
    out={"updated_at":datetime.now(timezone.utc).isoformat(),
         "source":"Notion Swing Journal closed trades; USD converted using journal FX field",
         "starting_capital_sgd":START_CAPITAL,"current_equity_sgd":round(equity,2),
         "realized_pnl_sgd":round(equity-START_CAPITAL,2),
         "return_pct":round((equity/START_CAPITAL-1)*100,2),
         "closed_trades":trades,"open_trades":opened,"curve":points,
         "calendar":dict(sorted(daily.items()))}
    Path("data").mkdir(exist_ok=True)
    Path("data/journal-performance.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(f"Journal sync: {len(trades)} closed, {len(opened)} open, realized SGD {out['realized_pnl_sgd']:.2f}, equity SGD {equity:.2f}")

if __name__=="__main__":
    export()
