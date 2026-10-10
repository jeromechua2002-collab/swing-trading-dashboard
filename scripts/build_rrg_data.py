import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BENCHMARK = "SPY"

UNIVERSES = {
    "sectors": {
        "Growth": ["XLK", "XLY", "XLC"],
        "Defensive": ["XLU", "XLRE", "XLP"],
        "Value": ["XLI", "XLB", "XLF"],
        "Wild Cards": ["XLV", "XLE"],
    },
    "industries": {
        "Technology": ["SOXX", "IGV"],
        "Cyclicals": ["XRT", "ITB", "ITA"],
        "Financial / Health": ["KRE", "XBI"],
        "Energy Industries": ["XOP", "OIH"],
    },
}

CONFIGS = {
    "1D": {"period": "1y", "interval": "1d", "smooth": 10, "norm": 26, "mom_lookback": 5, "tail": 15},
    "1H": {"period": "60d", "interval": "1h", "smooth": 8, "norm": 32, "mom_lookback": 4, "tail": 15},
}


def zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=max(8, window // 2)).mean()
    std = s.rolling(window, min_periods=max(8, window // 2)).std(ddof=0)
    std = std.replace(0, np.nan)
    return (s - mean) / std


def rrg_approx(asset: pd.Series, benchmark: pd.Series, cfg: dict) -> pd.DataFrame:
    pair = pd.concat([asset.rename("asset"), benchmark.rename("benchmark")], axis=1).dropna()
    pair = pair[(pair["asset"] > 0) & (pair["benchmark"] > 0)]
    raw_rs = np.log(pair["asset"] / pair["benchmark"])
    smoothed_rs = raw_rs.ewm(span=cfg["smooth"], adjust=False).mean()

    # Public-methodology approximation: relative price ratio -> smoothing ->
    # rolling normalization around 100 -> normalized momentum around 100.
    ratio_z = zscore(smoothed_rs, cfg["norm"]).clip(-3, 3)
    rs_ratio = 100.0 + 3.0 * ratio_z

    momentum_raw = rs_ratio.diff(cfg["mom_lookback"])
    momentum_z = zscore(momentum_raw, cfg["norm"]).clip(-3, 3)
    rs_momentum = 100.0 + 3.0 * momentum_z

    out = pd.DataFrame({"ratio": rs_ratio, "momentum": rs_momentum}).dropna()
    return out


def close_series(downloaded: pd.DataFrame, ticker: str) -> pd.Series:
    if isinstance(downloaded.columns, pd.MultiIndex):
        # yfinance may return either (Ticker, Field) or (Field, Ticker).
        if ticker in downloaded.columns.get_level_values(0):
            block = downloaded[ticker]
            return block["Close"] if "Close" in block.columns else block.iloc[:, 0]
        if ticker in downloaded.columns.get_level_values(1):
            return downloaded["Close"][ticker]
    if ticker == BENCHMARK and "Close" in downloaded.columns:
        return downloaded["Close"]
    raise KeyError(f"Could not locate close data for {ticker}")


def iso_label(ts) -> str:
    try:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return t.isoformat()
    except Exception:
        return str(ts)


def build_timeframe(label: str, cfg: dict, tickers: list[str]) -> dict:
    data = yf.download(
        tickers=tickers,
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )
    bench = close_series(data, BENCHMARK)

    output = {}
    for ticker in tickers:
        if ticker == BENCHMARK:
            continue
        try:
            asset = close_series(data, ticker)
            calc = rrg_approx(asset, bench, cfg).tail(cfg["tail"])
            if len(calc) < 4:
                continue
            output[ticker] = [
                {
                    "time": iso_label(idx),
                    "ratio": round(float(row["ratio"]), 4),
                    "momentum": round(float(row["momentum"]), 4),
                }
                for idx, row in calc.iterrows()
            ]
        except Exception as exc:
            print(f"{label} {ticker}: {exc}")
    return output


def main() -> None:
    all_tickers = sorted(
        {BENCHMARK}
        | {t for universe in UNIVERSES.values() for members in universe.values() for t in members}
    )

    timeframes = {}
    for label, cfg in CONFIGS.items():
        timeframes[label] = build_timeframe(label, cfg, all_tickers)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": BENCHMARK,
        "method": "RRG-style approximation; not official JdK RS-Ratio / RS-Momentum",
        "universes": UNIVERSES,
        "timeframes": timeframes,
    }

    Path("data").mkdir(exist_ok=True)
    Path("data/rrg.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    counts = {tf: len(symbols) for tf, symbols in timeframes.items()}
    print("Generated data/rrg.json", counts)


if __name__ == "__main__":
    main()
