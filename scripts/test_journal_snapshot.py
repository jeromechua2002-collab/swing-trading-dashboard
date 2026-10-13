#!/usr/bin/env python3
"""Offline consistency test for the exact journal snapshot served by both Pages views."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json

def cents(v):
    return int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def main():
    path=Path("data/journal-performance.json")
    d=json.loads(path.read_text(encoding="utf-8"))
    closed=d["closed_trades"]; opened=d["open_trades"]; curve=d["curve"]
    assert len(closed)>=10 and len(opened)>=0, "Incomplete historical journal"
    ids=[t["number"] for t in closed+opened]
    assert len(ids)==len(set(ids)), "Duplicate trade numbers"
    assert set(range(1, max(ids)+1))==set(ids), "Missing historical trade number"
    assert [(t["exit_date"],t["number"]) for t in closed]==sorted((t["exit_date"],t["number"]) for t in closed), "Closed trades not ordered by exit date"
    assert len(curve)==len(closed)+1, "Equity curve must have one point per realized trade"
    assert curve[0]["number"]==0 and cents(curve[0]["equity_sgd"])==cents(d["starting_capital_sgd"]), "Missing starting-capital point"
    equity=cents(d["starting_capital_sgd"]); calendar=defaultdict(list)
    for p,t in zip(curve[1:],closed):
        assert date.fromisoformat(t["exit_date"]), "Invalid trade exit date"
        assert p["number"]==t["number"] and p["symbol"]==t["symbol"] and p["date"]==t["exit_date"], "Mismatched equity event"
        assert cents(t["net_sgd"])==cents(Decimal(str(t["net_usd"]))*Decimal(str(t["fx"]))), "Trade FX mismatch"
        equity+=cents(t["net_sgd"])
        assert cents(p["net_sgd"])==cents(t["net_sgd"]), "Curve event P/L inconsistent"
        assert cents(p["equity_sgd"])==equity, "Equity curve arithmetic error"
        calendar[t["exit_date"]].append(t)
    assert cents(d["current_equity_sgd"])==equity, "Current account equity inconsistent"
    assert cents(d["realized_pnl_sgd"])==equity-cents(d["starting_capital_sgd"]), "Realized profit inconsistent"
    assert set(calendar)==set(d["calendar"]), "Calendar date coverage mismatch"
    for day,rows in calendar.items():
        got=d["calendar"][day]
        assert cents(got["net_sgd"])==sum(cents(t["net_sgd"]) for t in rows), "Calendar daily total incorrect"
        assert {x["number"] for x in got["trades"]}=={t["number"] for t in rows}, "Calendar day trade missing"
        for x in got["trades"]:
            t=next(r for r in rows if r["number"]==x["number"])
            assert cents(x["net_sgd"])==cents(t["net_sgd"]), "Calendar transaction P/L incorrect"
    trade=next((x for x in closed if x["number"]==11),None)
    assert trade and trade["symbol"]=="SOXS" and trade["size"]==100 and trade["exit_date"]=="2026-10-13", "SOXS #11 missing or misclassified"
    assert len(trade["exits"])==2 and sum(int(z["quantity"]) for z in trade["exits"])==100, "SOXS exit lots incorrect"
    assert cents(trade["net_usd"])==7025 and cents(trade["fees_usd"])==726, "SOXS broker result/fees incorrect"
    assert [(x["quantity"],cents(x["price"])) for x in trade["exits"]]==[(50,4009),(50,3954)], "SOXS broker fills mismatched"
    assert cents(trade["broker_reconciliation_difference_usd"])==201, "SOXS broker reconciliation discrepancy not preserved"
    # Historical broker-proven trades remain immutable while future trades and
    # open-position status can change. Do not hardcode today's total equity.
    soxl=next((x for x in closed if x["number"]==10),None)
    assert soxl and soxl["symbol"]=="SOXL" and cents(soxl["net_usd"])==-12052, "Historical SOXL #10 mismatch"
    assert cents(soxl["net_sgd"])+cents(trade["net_sgd"])==-6435, "October 13 historical SOXL/SOXS pair mismatch"
    print(f"JOURNAL AUDIT PASSED: {len(closed)} closed / {len(opened)} open / {len(calendar)} calendar dates / equity S$ {d['current_equity_sgd']:.2f} / historical SOXL/SOXS pair S$ -64.35. SOXS exit lots, broker P/L, fees and reconciliation validated.")

if __name__=="__main__":
    main()
