"""Thematic Rotation RRG feed (research display only) -> data/rrg-thematic.json.

Reuses build_rrg_data unchanged: the same rrg_public_approx() formula (our public
approximation, not proprietary JdK), SPY benchmark, per-timeframe download windows,
completed-bar policy and Yahoo retry policy, plus price_context.summarize_closes()
for the absolute-trend check.

Isolated and fail-closed: any data problem writes {"status": "unavailable"} and
exits 0, so the rest of the dashboard still publishes and the page says why.
Not read by Radar V0, the Notion sync or the 10-session evaluation.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import build_rrg_data as B
from price_context import summarize_closes

UNIVERSE = json.loads(Path(__file__).with_name("thematic_universe.json").read_text(encoding="utf-8"))
THEMES = [t["ticker"] for t in UNIVERSE["themes"]]
TICKERS = [B.MARKET_BENCHMARK, *THEMES]
OUT = Path("data/rrg-thematic.json")
TIMEFRAMES = ("1W", "1D", "4H", "1H")
DOWNLOADS = {"1wk": B.CONFIGS["1W"], "1d": B.CONFIGS["1D"], "1h": B.CONFIGS["1H"]}  # 4H is synthetic from 1h


def quadrant(x, y):
    if x >= 100 and y >= 100:
        return "Leading"
    if x >= 100:
        return "Weakening"
    return "Lagging" if y < 100 else "Improving"


def rel_return(s, bench, bars):
    pair = pd.concat([s.rename("a"), bench.rename("b")], axis=1, sort=True).dropna()
    if len(pair) <= bars:
        return None
    r = pair["a"] / pair["b"]
    return round(float(r.iloc[-1] / r.iloc[-1 - bars] - 1) * 100, 2)


def rrg_metrics(s, bench):
    """Production formula; a fund without a full tail is reported, never plotted or estimated."""
    calc = B.rrg_public_approx(s, bench)
    if len(calc) < B.TAIL_POINTS:
        return {"status": "insufficient", "bars": int(len(s)), "rrg_points": int(len(calc)),
                "needed_points": B.TAIL_POINTS, "first_bar": str(s.index[0])[:10] if len(s) else None}
    tail = calc.tail(B.TAIL_POINTS)
    trail = [{"time": B.iso_label(i), "ratio": round(float(r.ratio), 4), "momentum": round(float(r.momentum), 4)}
             for i, r in tail.iterrows()]
    h, p = trail[-1], trail[-2]
    return {"status": "ok", "bars": int(len(s)), "trail": trail, "quadrant": quadrant(h["ratio"], h["momentum"]),
            "distance": round(math.hypot(h["ratio"] - 100, h["momentum"] - 100), 3),
            "heading_deg": round(math.degrees(math.atan2(h["momentum"] - p["momentum"], h["ratio"] - p["ratio"])), 1),
            "rel5_pct": rel_return(s, bench, 5), "last_bar": B.iso_label(s.index[-1])}


def download():
    frames = {}
    for interval, cfg in DOWNLOADS.items():
        data = B.download_prices(TICKERS, cfg)
        close = pd.DataFrame({t: B.close_series(data, t) for t in TICKERS})
        empty = [t for t in TICKERS if close[t].dropna().empty]
        if empty:
            raise RuntimeError(f"{interval}: no vendor data for {empty}")
        vol = pd.DataFrame({t: data[t]["Volume"] for t in TICKERS}) if interval == "1d" else None
        frames[interval] = (close, vol)
    return frames


def build(frames, build_now):
    out = {"status": "ok", "generated_at": datetime.now(timezone.utc).isoformat(), "build_clock": build_now.isoformat(),
           "benchmark": B.MARKET_BENCHMARK, "tail_points": B.TAIL_POINTS,
           "method": {"smooth_wma": B.SMOOTH_WMA, "normalize_window": B.NORMALIZE_WINDOW,
                      "momentum_roc": B.MOMENTUM_ROC, "momentum_wma": B.MOMENTUM_WMA,
                      "label": "public approximation, not proprietary JdK RRG"},
           "timeframes": {}, "absolute": {}, "stale": {}}
    series = {}
    for tf in TIMEFRAMES:
        cfg = B.CONFIGS[tf]
        close = frames[cfg["interval"]][0]
        series[tf] = {t: B.prepare_series(close[t].dropna(), cfg, build_now)[0] for t in TICKERS}
        bench = series[tf][B.MARKET_BENCHMARK]
        if len(bench) < 2 * B.TAIL_POINTS:
            raise ValueError(f"{tf}: benchmark history too short")
        syms = {t: rrg_metrics(series[tf][t], bench) for t in THEMES}
        out["timeframes"][tf] = {"benchmark_last": str(bench.index[-1]), "symbols": syms}
        out["stale"][tf] = [t for t in THEMES if len(series[tf][t]) and series[tf][t].index[-1] != bench.index[-1]]
    for tf in ("1D", "1W"):
        out["absolute"][tf] = {}
        for t in TICKERS:
            try:
                out["absolute"][tf][t] = summarize_closes(series[tf][t])
            except ValueError as exc:
                out["absolute"][tf][t] = {"error": str(exc)}

    daily = pd.DataFrame(series["1D"])
    rets = daily.pct_change(fill_method=None).dropna()  # window all ten funds share (DRAM's life)
    if len(rets) < 60:
        raise ValueError("fewer than 60 common daily sessions for correlation")
    excess = rets[THEMES].sub(rets[B.MARKET_BENCHMARK], axis=0)
    out["correlation"] = {"window": f"{rets.index[0].date()} → {rets.index[-1].date()} ({len(rets)} sessions)",
                          "excess_vs_spy": {a: {b: round(float(excess[a].corr(excess[b])), 2) for b in THEMES} for a in THEMES}}
    spy = rets[B.MARKET_BENCHMARK]
    out["beta_spy"] = {t: round(float(rets[t].cov(spy) / spy.var()), 2) for t in THEMES}
    out["vol_ann_pct"] = {t: round(float(rets[t].std() * np.sqrt(252) * 100), 1) for t in TICKERS}
    close_d, vol_d = frames["1d"]
    dv = (close_d * vol_d).loc[:daily.index[-1]].tail(20).mean()
    out["adv20_usd_m"] = {t: round(float(dv[t]) / 1e6, 1) for t in THEMES}
    out["first_bar"] = {t: str(close_d[t].first_valid_index())[:10] for t in THEMES}

    H = {t: UNIVERSE["holdings"][t]["h"] for t in THEMES}
    out["overlap_topN_min_weight_pct"] = {a: {b: (None if not H[a] or not H[b] else
                                                  round(sum(min(H[a][k], H[b][k]) for k in H[a].keys() & H[b].keys()), 2))
                                              for b in THEMES} for a in THEMES}
    out["concentration"] = {t: {"top3_pct": round(sum(sorted(H[t].values(), reverse=True)[:3]), 1) if H[t] else None}
                            for t in THEMES}
    out["themes"] = [dict(t, sectors=t["gics"]) for t in UNIVERSE["themes"]]
    out["facts"] = UNIVERSE["facts"]
    out["excluded"] = UNIVERSE["excluded"]
    out["checked"] = UNIVERSE["checked"]
    return out


def validate(payload):
    for tf in TIMEFRAMES:
        syms = payload["timeframes"][tf]["symbols"]
        if sorted(syms) != sorted(THEMES):
            raise ValueError(f"{tf}: theme set incomplete")
    ok_daily = [t for t, v in payload["timeframes"]["1D"]["symbols"].items() if v["status"] == "ok"]
    if len(ok_daily) < len(THEMES) - 1:
        raise ValueError(f"1D: only {len(ok_daily)} themes have a full trail")
    json.dumps(payload, allow_nan=False)  # NaN/inf would break the browser's JSON parser


def write(payload, out=OUT):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def main(fetch=download, out=OUT):
    build_now = B.now_utc()
    try:
        payload = build(fetch(), build_now)
        validate(payload)
    except Exception as exc:  # fail closed without blocking the rest of the site
        payload = {"status": "unavailable", "generated_at": datetime.now(timezone.utc).isoformat(),
                   "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(f"::warning title=Thematic RRG unavailable::{payload['error']}")
    write(payload, out)
    print("THEMATIC RRG:", payload["status"], {tf: v["benchmark_last"][:16] for tf, v in payload.get("timeframes", {}).items()})
    return payload


if __name__ == "__main__":
    main()
    sys.exit(0)
