"""Experimental daily sector comparison, derived from the dashboard audit snapshot.

Raw-close RRGs reuse the live formula. Return comparisons use adjusted closes.
Never infer constituent breadth or dealer positioning from ETF ratios alone.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from build_rrg_data import download_prices, close_series, trail_payload, SECTOR_GROUPS

PAIRS = {
    "XLK": ("RSPT", "Technology"), "XLY": ("RSPD", "Consumer Discretionary"),
    "XLC": ("RSPC", "Communication Services"), "XLU": ("RSPU", "Utilities"),
    "XLRE": ("RSPR", "Real Estate"), "XLP": ("RSPS", "Consumer Staples"),
    "XLI": ("RSPN", "Industrials"), "XLB": ("RSPM", "Materials"),
    "XLF": ("RSPF", "Financials"), "XLV": ("RSPH", "Health Care"),
    "XLE": ("RSPG", "Energy"),
}
WINDOWS = (5, 10, 20, 60)
OUT = Path("data/sector-breadth.json")


def daily(s, cutoff=None):
    s = s.sort_index().copy()
    s.index = pd.DatetimeIndex([pd.Timestamp(str(t)[:10], tz="UTC") for t in s.index])
    # Yahoo can append a NaN/zero PARTIAL bar for today's trading day.
    # Remove unfinished sessions before checking the already closed history;
    # invalid values in any completed bar still fail the feed.
    if cutoff is not None:
        s = s.loc[:cutoff]
    if s.empty or not np.isfinite(s).all() or (s <= 0).any():
        raise ValueError("invalid or empty COMPLETED daily prices")
    if s.index.duplicated().any():
        raise ValueError("duplicate daily sessions")
    return s


def completed_cutoff(now):
    et = now.astimezone(ZoneInfo("America/New_York"))
    day = et.date() if (et.hour, et.minute) >= (16, 15) else et.date() - timedelta(days=1)
    return pd.Timestamp(day, tz="UTC")


def quadrant(p):
    x, y = p["ratio"], p["momentum"]
    return ("Leading" if y >= 100 else "Weakening") if x >= 100 else ("Improving" if y >= 100 else "Lagging")


def classify(cap, equal):
    # Benchmark-adjusted relative returns, with a transparent neutral band.
    band = 0.25
    if cap > band and equal > band:
        return "Broad leadership", "Both beat SPY; check the industry and entry structure."
    if cap > band and equal < -band:
        return "Heavyweight-led", "Cap-weight strength lacks equal-weight confirmation; inspect individual leaders."
    if equal > band and cap < -band:
        return "Broadening under the surface", "Equal weight leads; inspect smaller sector members and industry breadth."
    if cap < -band and equal < -band:
        return "Broad weakness", "Both trail SPY; relative weakness still needs a price trigger for a short."
    return "Mixed / transition", "One or both legs are near neutral; wait for clearer agreement."


def compare_snapshot(audit, raw, adjusted, now):
    source_time = datetime.fromisoformat(audit["generated_at"])
    if source_time.tzinfo is None:
        raise ValueError("source timestamp must include timezone")
    source_age = (now - source_time).total_seconds()
    if source_age < -300 or source_age > 72 * 3600:
        raise ValueError("source build timestamp is stale or in the future")
    cutoff = completed_cutoff(now)
    caps = {t: daily(pd.Series([r["close"] for r in rows], index=[r["time"] for r in rows], dtype=float), cutoff)
            for t, rows in audit["prices"].items()}
    spy = caps["SPY"].loc[:cutoff]
    if spy.empty:
        raise ValueError("Dashboard SPY snapshot has no completed daily bars")
    asof = spy.index[-1]
    if (cutoff - asof).days > 4:
        raise ValueError("Dashboard snapshot is stale")
    rows, errors = [], []
    equal_spy, equal_rsp, cap_spy, prices = {}, {}, {}, {}
    raw = {t: daily(s, cutoff) for t, s in raw.items()}
    if raw["SPY"].index[-1] != asof:
        raise ValueError("dashboard session is stale relative to refreshed SPY")
    raw = {t: s.loc[:asof] for t, s in raw.items()}
    adjusted = {t: daily(s, asof) for t, s in adjusted.items()}
    for ticker in ["SPY", "RSP", *PAIRS, *[v[0] for v in PAIRS.values()]]:
        s = adjusted.get(ticker)
        if s is None or s.empty or s.index[-1] != asof or len(s) < 100:
            raise ValueError(f"{ticker}: incomplete or stale adjusted history at {asof.date()}")
        if (s <= 0).any() or not np.isfinite(s).all():
            raise ValueError(f"{ticker}: invalid price")
        prices[ticker] = [{"time": str(d.date()), "close": round(float(v), 6)} for d, v in s.tail(180).items()]
    for cap, (ew, name) in PAIRS.items():
        try:
            raw_cap, raw_ew = caps[cap].loc[:asof], raw[ew]
            if raw_cap.index[-1] != asof or raw_ew.index[-1] != asof or raw["RSP"].index[-1] != asof:
                raise ValueError("raw close dates do not match dashboard")
            # Refuse a silently revised cap leg from the separate adjusted-price fetch.
            for symbol, series in [(cap, raw_cap), ("SPY", spy), (ew, raw_ew), ("RSP", raw["RSP"])]:
                reference = spy.tail(min(len(series), len(spy)))
                if len(reference) < 100 or not series.index.equals(reference.index):
                    raise ValueError(f"{symbol}: missing raw daily sessions")
            for symbol, series in [(cap, raw_cap), ("SPY", spy)]:
                recent = series.tail(100)
                downloaded = raw[symbol].reindex(recent.index)
                if downloaded.isna().any() or ((downloaded / recent - 1).abs() > 0.0001).any():
                    raise ValueError(f"{symbol}: raw history changed between dashboard and comparison fetch")
            frame = pd.concat({t: adjusted[t] for t in [cap, ew, "SPY", "RSP"]}, axis=1).dropna()
            if len(frame) < 100 or not frame.index.equals(spy.tail(len(frame)).index):
                raise ValueError("missing common daily sessions")
            cap_spy[cap] = trail_payload(raw_cap, spy)
            equal_spy[ew] = trail_payload(raw_ew, spy)
            equal_rsp[ew] = trail_payload(raw_ew, raw["RSP"])
            trails = [cap_spy[cap], equal_spy[ew], equal_rsp[ew]]
            if any(len(a) != 16 or a[-1]["time"][:10] != str(asof.date()) for a in trails):
                raise ValueError("RRG trail incomplete or dated differently")
            metrics = {}
            for n in WINDOWS:
                start, end = frame.iloc[-n-1], frame.iloc[-1]
                factors = end / start
                cr = 100 * (factors[cap] / factors["SPY"] - 1)
                er = 100 * (factors[ew] / factors["SPY"] - 1)
                ratio = 100 * (factors[ew] / factors[cap] - 1)
                state, implication = classify(cr, er)
                rel = 100 * ((frame[ew] / frame[cap]).iloc[-6:] / (frame[ew] / frame[cap]).iloc[-6] - 1)
                slope = float(np.polyfit(np.arange(6), rel.iloc[-6:], 1)[0])
                metrics[str(n)] = {"cap_vs_spy": round(cr, 3), "equal_vs_spy": round(er, 3),
                    "equal_vs_cap": round(ratio, 3), "equal_vs_rsp": round(100 * (factors[ew] / factors["RSP"] - 1), 3),
                    "ratio_slope_5d": round(slope, 4), "state": state, "implication": implication}
            rows.append({"cap": cap, "equal": ew, "name": name,
                "bundle": next(g for g, ts in SECTOR_GROUPS.items() if cap in ts),
                "cap_quadrant": quadrant(cap_spy[cap][-1]), "equal_quadrant": quadrant(equal_spy[ew][-1]),
                "equal_rsp_quadrant": quadrant(equal_rsp[ew][-1]), "metrics": metrics,
                "proxy_note": "Plus index may add S&P MidCap 400 members to meet a 22-company minimum." if cap in ("XLC", "XLE") else "Equal-weight ETF proxy; fund fees and rebalancing can affect the spread."})
        except (KeyError, ValueError, IndexError) as exc:
            errors.append(f"{cap}/{ew}: {exc}")
    return {"generated_at": now.isoformat(), "as_of": str(asof.date()), "status": "ok" if len(rows) == 11 and not errors else "incomplete",
        "errors": errors, "source_generated_at": audit["generated_at"], "source": "data/rrg-audit.json + Yahoo equal-weight and adjusted daily histories",
        "price_basis": "Raw-close RRG; adjusted-close return comparisons", "rows": rows, "prices": prices,
        "rrg": {"cap_vs_SPY": cap_spy, "equal_vs_SPY": equal_spy, "equal_vs_RSP": equal_rsp},
        "benchmarks": {"SPY": [{"time": str(d.date()), "close": float(v)} for d, v in spy.tail(80).items()],
            "RSP": [{"time": str(d.date()), "close": float(v)} for d, v in raw["RSP"].tail(80).items()]},
        "groups": {g: [PAIRS[t][0] for t in ts] for g, ts in SECTOR_GROUPS.items()}}


def main():
    now = datetime.now(timezone.utc)
    try:
        audit = json.loads(Path("data/rrg-audit.json").read_text())
        tickers = ["SPY", "RSP", *PAIRS, *[v[0] for v in PAIRS.values()]]
        data = download_prices(tickers, {"period": "1y", "interval": "1d"})
        raw = {t: close_series(data, t) for t in tickers}
        adjusted = {t: data[t]["Adj Close"] for t in tickers}
        payload = compare_snapshot(audit, raw, adjusted, now)
    except Exception as exc:
        payload = {"generated_at": now.isoformat(), "status": "unavailable", "errors": [str(exc)], "rows": []}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Sector Breadth Lab: {payload['status']} · {len(payload['rows'])}/11 pairs")
    for error in payload.get("errors", []):
        print(error)


if __name__ == "__main__":
    main()
