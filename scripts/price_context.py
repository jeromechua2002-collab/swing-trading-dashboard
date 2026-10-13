"""Absolute-close context to supplement, never replace, RRG screening.

Uses the exact same Yahoo raw Close bars already downloaded by build_rrg_data.
The 4H input is the synthetic completed 4H close stream; no OHLC pivot,
volume-confirmation, ATR, earnings or executable order prices are inferred.
"""
import math
import pandas as pd

def summarize_closes(series):
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if len(s) < 35:
        raise ValueError("Insufficient completed bars for EMA10/EMA20 and prior 20-bar range")
    if s.index.has_duplicates or not s.index.is_monotonic_increasing:
        raise ValueError("Duplicate or unsorted absolute-price dates")
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in s):
        raise ValueError("Invalid nonpositive/nonfinite raw closes")
    e10 = s.ewm(span=10, adjust=False).mean()
    e20 = s.ewm(span=20, adjust=False).mean()
    last = float(s.iloc[-1])
    ema10, ema20 = float(e10.iloc[-1]), float(e20.iloc[-1])
    up10 = ema10 > float(e10.iloc[-6])
    dn10 = ema10 < float(e10.iloc[-6])
    if last > ema10 > ema20 and up10:
        state = "Uptrend"
    elif last < ema10 < ema20 and dn10:
        state = "Downtrend"
    else:
        state = "Mixed"
    prev = s.iloc[-21:-1]
    if len(prev) != 20:
        raise ValueError("20 completed comparison bars unavailable")
    def rnd(v): return round(float(v), 4)
    stamp=pd.Timestamp(s.index[-1])
    return {
        "session": stamp.date().isoformat(),
        "close": rnd(last),
        "ema10": rnd(ema10),
        "ema20": rnd(ema20),
        "ema10_rising": bool(up10),
        "ema20_rising": bool(ema20 > float(e20.iloc[-6])),
        "state": state,
        "prior20_close_high": rnd(prev.max()),
        "prior20_close_low": rnd(prev.min()),
        "distance_to_prior20_close_high_pct": rnd(100*(last/float(prev.max())-1)),
        "return5_pct": rnd(100*(last/float(s.iloc[-6])-1)),
        "return20_pct": rnd(100*(last/float(s.iloc[-21])-1)),
        "basis": "Yahoo raw Close; 4H=synthetic completed hourly bars; not OHLC pivots"
    }
