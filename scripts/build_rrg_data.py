import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from price_context import summarize_closes
from pathlib import Path

import exchange_calendars as xcals

import radar_bundle
import numpy as np
import pandas as pd
import yfinance as yf

MARKET_BENCHMARK = "SPY"

SECTOR_GROUPS = {
    "Growth": ["XLK", "XLY", "XLC"],
    "Defensive": ["XLU", "XLRE", "XLP"],
    "Value": ["XLI", "XLB", "XLF"],
    "Wild Cards": ["XLV", "XLE"],
}

INDUSTRY_GROUPS = {
    "Technology / Internet": ["SMH", "IGV", "FDN"],
    "Energy / Materials": ["XOP", "OIH", "XME", "TAN", "PBW"],
    "Financial / Real Estate": ["KRE", "KIE", "VNQ"],
    "Consumer / Industrials": ["XRT", "ITB", "ITA", "JETS"],
    "Health": ["IBB"],
}

# First stock drill-down universe. The UI keeps these behind the Stocks layer,
# so the weekly sector/industry RRGs stay clean.
STOCK_GROUPS = {
    "XLK": ["NVDA", "AAPL", "MSFT", "AVGO", "ORCL", "AMD", "MU", "PANW", "CRWD", "CSCO", "IBM", "INTC", "QCOM", "CRM", "ADBE"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW", "TJX", "NKE", "SBUX", "ORLY"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "TMUS", "DIS", "T", "VZ", "APP", "TTWO", "CHTR"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "C"],
    "XLI": ["GE", "CAT", "RTX", "UBER", "DE", "HON", "UNP", "ETN", "UPS", "BA"],
    "XLB": ["LIN", "SHW", "APD", "FCX", "ECL", "NEM", "NUE", "DOW", "MLM", "VMC"],
    "XLV": ["LLY", "JNJ", "ABBV", "MRK", "UNH", "TMO", "ABT", "ISRG", "AMGN", "GILD"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "KMI"],
    "XLP": ["WMT", "COST", "PG", "KO", "PM", "PEP", "MDLZ", "MO", "CL", "KMB"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "VST", "AEP", "SRE", "EXC", "XEL", "ED"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "SPG", "PSA", "O", "CCI", "VICI", "CBRE"],
}

# Same bar-count parameters for Daily and 1H. This follows the public
# EdgeRater description that the timeframe itself defines the horizon.
CONFIGS = {
    "1W": {"period": "3y", "interval": "1wk"},
    "1D": {"period": "1y", "interval": "1d"},
    "4H": {"period": "60d", "interval": "1h", "synthetic_hours": 4},
    "1H": {"period": "60d", "interval": "1h"},
}
# ── Completed-bar policy ─────────────────────────────────────────────────────
# Yahoo labels 1h bars by their START time, 1wk bars by the week's first day and
# 1d bars by the session date, and returns the still-forming bar for each. Only
# bars whose END has passed (by the NYSE calendar, incl. holidays and early
# closes) may be published. All timeframes are judged against one build clock.
NY = ZoneInfo("America/New_York")
DAILY_SETTLE = pd.Timedelta(minutes=15)  # grace after the close for final prints
_NYSE = None


def nyse():
    global _NYSE
    if _NYSE is None:
        _NYSE = xcals.get_calendar("XNYS")
    return _NYSE


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert(NY)


def _naive_day(label) -> pd.Timestamp:
    """Calendar date a bar label refers to (UTC date for tz-aware daily/weekly labels)."""
    t = pd.Timestamp(label)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.normalize()


def _session_close(day: pd.Timestamp) -> pd.Timestamp | None:
    return nyse().session_close(day).tz_convert(NY) if nyse().is_session(day) else None


def daily_bar_end(label) -> pd.Timestamp:
    """Daily bar is final once its session close (+settle) has passed."""
    day = _naive_day(label)
    close = _session_close(day)
    if close is None:  # not a session (vendor anomaly): final only after that calendar day
        return (day + pd.Timedelta(days=1)).tz_localize(NY)
    return close + DAILY_SETTLE


def hourly_bar_end(label) -> pd.Timestamp:
    """1h bar starting at `label` ends one hour later, or at an (early) close."""
    start = _ny(label)
    close = _session_close(start.tz_localize(None).normalize())
    end = start + pd.Timedelta(hours=1)
    return min(end, close) if close is not None else end


def weekly_bar_end(label) -> pd.Timestamp:
    """Weekly bar is final after the last NYSE session of that week has closed."""
    first = _naive_day(label)
    monday = first - pd.Timedelta(days=first.weekday())
    sessions = nyse().sessions_in_range(monday, monday + pd.Timedelta(days=4))
    if len(sessions) == 0:
        return (monday + pd.Timedelta(days=7)).tz_localize(NY)
    return nyse().session_close(sessions[-1]).tz_convert(NY) + DAILY_SETTLE


BAR_END = {"1d": daily_bar_end, "1h": hourly_bar_end, "1wk": weekly_bar_end}


def completed_only(series: pd.Series, interval: str, build_now) -> pd.Series:
    """Drop every bar whose end is after the build clock. Apply to RAW vendor
    bars, before any synthetic aggregation."""
    if series.empty:
        return series
    now = _ny(build_now)
    end = BAR_END[interval]
    return series.loc[[end(t) <= now for t in series.index]]


SMOOTH_WMA = 10
NORMALIZE_WINDOW = 16
MOMENTUM_ROC = 5
MOMENTUM_WMA = 4
NORMALIZE_SCALE = 1.0
TAIL_POINTS = 16

EXPECTED_SECTORS = sorted({t for group in SECTOR_GROUPS.values() for t in group})
EXPECTED_INDUSTRIES = sorted({t for group in INDUSTRY_GROUPS.values() for t in group})
EXPECTED_STOCKS = sorted({t for members in STOCK_GROUPS.values() for t in members})
CORE_TICKERS = [MARKET_BENCHMARK, *EXPECTED_SECTORS, *EXPECTED_INDUSTRIES]


def rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std(ddof=1).replace(0, np.nan)
    out = (s - mean) / std
    return out.replace([np.inf, -np.inf], np.nan)


def wma(s: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return s.copy()
    weights = np.arange(1, window + 1, dtype=float)
    denom = weights.sum()
    return s.rolling(window, min_periods=window).apply(
        lambda x: float(np.dot(x, weights) / denom), raw=True
    )


def rrg_public_approx(asset: pd.Series, benchmark: pd.Series) -> pd.DataFrame:
    pair = pd.concat(
        [asset.rename("asset"), benchmark.rename("benchmark")], axis=1
    ).dropna()
    pair = pair[(pair["asset"] > 0) & (pair["benchmark"] > 0)]

    # EdgeRater-calibrated public approximation:
    # 1) price-relative series = 100 * asset close / benchmark close
    # 2) smooth the relative-strength series with a trailing WMA
    # 3) normalize that smoothed series around 100 over a trailing window
    # 4) calculate ROC of RS-Ratio
    # 5) smooth the ROC and normalize it around 100 using the same window
    #
    # This matches EdgeRater's published methodology family. The exact
    # proprietary JdK/EdgeRater implementation remains undisclosed.
    rs = 100.0 * pair["asset"] / pair["benchmark"]

    smoothed_rs = wma(rs, SMOOTH_WMA)
    ratio_z = rolling_zscore(smoothed_rs, NORMALIZE_WINDOW)
    rs_ratio = 100.0 + NORMALIZE_SCALE * ratio_z

    roc = 100.0 * (
        rs_ratio / rs_ratio.shift(MOMENTUM_ROC) - 1.0
    )
    smoothed_roc = wma(roc, MOMENTUM_WMA)
    momentum_z = rolling_zscore(smoothed_roc, NORMALIZE_WINDOW)
    rs_momentum = 100.0 + NORMALIZE_SCALE * momentum_z

    return pd.DataFrame(
        {"ratio": rs_ratio, "momentum": rs_momentum}
    ).replace([np.inf, -np.inf], np.nan).dropna()


def close_series(downloaded: pd.DataFrame, ticker: str) -> pd.Series:
    if isinstance(downloaded.columns, pd.MultiIndex):
        lv0 = downloaded.columns.get_level_values(0)
        lv1 = downloaded.columns.get_level_values(1)
        if ticker in lv0:
            block = downloaded[ticker]
            if "Close" in block.columns:
                return block["Close"]
            return block.iloc[:, 0]
        if ticker in lv1 and "Close" in lv0:
            return downloaded["Close"][ticker]
    if "Close" in downloaded.columns:
        return downloaded["Close"]
    raise KeyError(f"Could not locate close data for {ticker}")


def iso_label(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.isoformat()


def synthetic_hour_bars(s: pd.Series, hours: int) -> pd.Series:
    """Aggregate consistently anchored US session hours into completed N-hour bars.

    A missing quote must not shift every later N-hour bucket for one ticker.
    For 4H on the 6.5-hour US cash session, the final 2.5-hour bucket is
    treated as completed only after the session's normal final bar exists.
    """
    s = s.dropna().sort_index()
    if s.empty or hours <= 1:
        return s
    local = s.copy()
    if local.index.tz is None:
        local.index = local.index.tz_localize("UTC")
    local.index = local.index.tz_convert("America/New_York")
    parts = []
    for _, day in local.groupby(local.index.date):
        day = day.sort_index()
        start = day.index[0].normalize() + pd.Timedelta(hours=9, minutes=30)
        offsets = (day.index - start).total_seconds() / 3600.0
        # A fixed market-open anchor prevents missing hourly candles from
        # changing which 4-hour bucket a quote belongs to.
        buckets = np.floor(np.maximum(offsets, 0) / hours).astype(int)
        for bucket in sorted(set(buckets)):
            block = day.iloc[np.where(buckets == bucket)[0]]
            if block.empty:
                continue
            # Timestamp by the market schedule, not the ticker's last tick.
            # A partial bar only at the current edge is left out below.
            if bucket == 0:
                stamp = start + pd.Timedelta(hours=hours - 1)
                expected = hours
            else:
                stamp = start + pd.Timedelta(hours=6)
                expected = 3  # final US session hour samples: 13:30, 14:30, 15:30
            if len(block) < expected:
                continue
            parts.append((stamp, float(block.iloc[-1])))
    if not parts:
        return s.iloc[:0]
    out = pd.Series([v for _, v in parts], index=pd.DatetimeIndex([t for t, _ in parts]))
    return out.sort_index()



def trail_payload(asset: pd.Series, benchmark: pd.Series) -> list[dict]:
    calc = rrg_public_approx(asset, benchmark).tail(TAIL_POINTS)
    return [
        {
            "time": iso_label(idx),
            "ratio": round(float(row["ratio"]), 4),
            "momentum": round(float(row["momentum"]), 4),
        }
        for idx, row in calc.iterrows()
    ]


def benchmark_payload(s: pd.Series, points: int = 80) -> list[dict]:
    s = s.dropna().tail(points)
    return [
        {"time": iso_label(idx), "close": round(float(value), 4)}
        for idx, value in s.items()
    ]


def download_prices(tickers: list[str], cfg: dict) -> pd.DataFrame:
    last_exc = None
    for attempt in range(1, 4):
        try:
            data = yf.download(
                tickers=tickers,
                period=cfg["period"],
                interval=cfg["interval"],
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="ticker",
            )
            if data is not None and not data.empty:
                return data
            last_exc = RuntimeError("Yahoo returned an empty dataframe")
        except Exception as exc:
            last_exc = exc
        if attempt < 3:
            print(f"Yahoo download attempt {attempt}/3 failed; retrying in {attempt * 2}s")
            time.sleep(attempt * 2)
    raise RuntimeError(f"Yahoo download failed after 3 attempts: {last_exc}")


def refresh_lagging_daily_closes(closes: dict, cfg: dict, build_now, sources: dict | None = None) -> dict:
    """Retry lagging vendor daily bars but never invent or forward-fill closes."""
    bench = closes.get(MARKET_BENCHMARK)
    if bench is None or bench.dropna().empty:
        return closes
    expected = bench.dropna().index[-1]
    lagging = sorted(ticker for ticker, series in closes.items()
                     if ticker != MARKET_BENCHMARK and not series.dropna().empty
                     and series.dropna().index[-1] != expected)
    if not lagging:
        return closes
    print(f"1D: refreshing {len(lagging)} lagging Yahoo tickers at benchmark session {expected}")
    try:
        refreshed = download_prices(lagging, cfg)
    except Exception as exc:
        print(f"1D: refresh unavailable ({type(exc).__name__}); integrity gate remains active")
        return closes
    recovered = 0
    for ticker in lagging:
        try:
            series, _ = prepare_series(close_series(refreshed, ticker), cfg, build_now)
            if not series.dropna().empty and series.dropna().index[-1] == expected:
                closes[ticker] = series
                if sources is not None:
                    sources[ticker] = refreshed
                recovered += 1
        except Exception:
            pass
    print(f"1D: recovered {recovered}/{len(lagging)}; outstanding gaps must fail validation")
    return closes


def validate_timeframe_output(label: str, closes: dict, sectors: dict, industries: dict, stocks: dict) -> None:
    missing_core = sorted(set(CORE_TICKERS) - set(closes))
    missing_stocks = sorted(set(EXPECTED_STOCKS) - set(closes))
    errors = []

    if missing_core:
        errors.append("missing core closes: " + ", ".join(missing_core))
    if missing_stocks:
        errors.append("missing stock closes: " + ", ".join(missing_stocks))

    if MARKET_BENCHMARK in closes:
        bench = closes[MARKET_BENCHMARK].dropna().sort_index()
        if bench.empty:
            errors.append("SPY close series is empty")
        else:
            latest = bench.index[-1]
            for ticker in [*CORE_TICKERS, *EXPECTED_STOCKS]:
                if ticker not in closes:
                    continue
                s = closes[ticker].dropna().sort_index()
                if s.empty:
                    errors.append(f"{ticker}: empty close series")
                elif s.index[-1] != latest:
                    errors.append(
                        f"{ticker}: latest bar {s.index[-1]} != SPY {latest}"
                    )

    if set(sectors) != set(EXPECTED_SECTORS):
        errors.append(
            f"sector coverage {len(sectors)}/{len(EXPECTED_SECTORS)}"
        )
    if set(industries) != set(EXPECTED_INDUSTRIES):
        errors.append(
            f"industry coverage {len(industries)}/{len(EXPECTED_INDUSTRIES)}"
        )

    for ticker, trail in sectors.items():
        if len(trail) != TAIL_POINTS:
            errors.append(f"{ticker}: sector tail has {len(trail)}/{TAIL_POINTS} points")
    for ticker, trail in industries.items():
        if len(trail) != TAIL_POINTS:
            errors.append(f"{ticker}: industry tail has {len(trail)}/{TAIL_POINTS} points")

    stock_seen = set()
    for sector, members in STOCK_GROUPS.items():
        block = stocks.get(sector, {})
        vs_spy = block.get("vs_SPY", {})
        vs_sector = block.get(f"vs_{sector}", {})
        expected = set(members)
        stock_seen.update(vs_spy)
        if set(vs_spy) != expected:
            errors.append(
                f"{sector}: stock vs SPY coverage {len(vs_spy)}/{len(expected)}"
            )
        if set(vs_sector) != expected:
            errors.append(
                f"{sector}: stock vs sector coverage {len(vs_sector)}/{len(expected)}"
            )
        for ticker in expected:
            if ticker in vs_spy and len(vs_spy[ticker]) != TAIL_POINTS:
                errors.append(
                    f"{ticker}: vs SPY tail has {len(vs_spy[ticker])}/{TAIL_POINTS} points"
                )
            if ticker in vs_sector and len(vs_sector[ticker]) != TAIL_POINTS:
                errors.append(
                    f"{ticker}: vs {sector} tail has {len(vs_sector[ticker])}/{TAIL_POINTS} points"
                )

    if stock_seen != set(EXPECTED_STOCKS):
        errors.append(
            f"stock coverage {len(stock_seen)}/{len(EXPECTED_STOCKS)}"
        )

    if errors:
        raise RuntimeError(f"{label} RRG integrity check failed: " + "; ".join(errors))

    print(
        f"{label} integrity OK: sectors={len(sectors)}/{len(EXPECTED_SECTORS)}, "
        f"industries={len(industries)}/{len(EXPECTED_INDUSTRIES)}, "
        f"stocks={len(stock_seen)}/{len(EXPECTED_STOCKS)}, tails={TAIL_POINTS}"
    )


def prepare_series(raw: pd.Series, cfg: dict, build_now) -> tuple[pd.Series, int]:
    """Completed vendor bars only, then (for 4H) synthetic aggregation."""
    series = completed_only(raw, cfg["interval"], build_now)
    dropped = int(raw.notna().sum() - series.notna().sum())
    if cfg.get("synthetic_hours"):
        series = synthetic_hour_bars(series, int(cfg["synthetic_hours"]))
    return series, dropped


def build_timeframe(label: str, cfg: dict, tickers: list[str], build_now: datetime | None = None) -> dict:
    build_now = build_now or now_utc()
    data = download_prices(tickers, cfg)
    closes = {}
    sources = {}  # download that produced each validated series (radar bundle only)
    dropped_forming = 0
    for ticker in tickers:
        try:
            series, dropped = prepare_series(close_series(data, ticker), cfg, build_now)
            dropped_forming += dropped
            closes[ticker] = series
            sources[ticker] = data
        except Exception as exc:
            print(f"{label} batch missing {ticker}: {exc}")

    # Yahoo occasionally returns a non-empty batch with one or two symbols
    # missing. Retry only those symbols individually before failing closed.
    missing = [ticker for ticker in tickers if ticker not in closes or closes[ticker].dropna().empty]
    if missing:
        print(f"{label}: retrying {len(missing)} missing/empty symbols individually")
    for ticker in missing:
        try:
            one = download_prices([ticker], cfg)
            raw = close_series(one, ticker)
            if raw.dropna().empty:
                raise ValueError(f"{ticker}: retry returned empty close series")
            series, dropped = prepare_series(raw, cfg, build_now)
            dropped_forming += dropped
            closes[ticker] = series
            sources[ticker] = one
            print(f"{label}: recovered {ticker} on individual retry")
        except Exception as exc:
            print(f"{label} individual retry failed {ticker}: {exc}")

    if MARKET_BENCHMARK not in closes:
        raise RuntimeError(f"{label}: benchmark {MARKET_BENCHMARK} unavailable")

    if label == "1D":
        closes = refresh_lagging_daily_closes(closes, cfg, build_now, sources)

    if dropped_forming:
        print(f"{label}: removed {dropped_forming} still-forming vendor bars (bar end after build clock {build_now.isoformat()})")

    # A symbol can still lag the others by a completed bar (missing vendor
    # candle). Compare all instruments on the same common completed bar,
    # rather than silently comparing different timestamps.
    if label in ("1H", "4H"):
        last = {t: v.dropna().index[-1] for t, v in closes.items() if not v.dropna().empty}
        if last:
            cutoff = min(last.values())
            newest = max(last.values())
            allowed = pd.Timedelta(hours=5 if label == "4H" else 2)
            if newest - cutoff > allowed:
                raise RuntimeError(f"{label}: recent bar freshness gap exceeds {allowed}: {newest} vs {cutoff}")
            if cutoff != newest:
                print(f"{label}: aligning {len(closes)} symbols to common completed timestamp {cutoff}; newest {newest} not yet available for every symbol")
            closes = {t: v.loc[v.index <= cutoff] for t, v in closes.items()}

    radar_bundle.capture(label, closes, sources)
    spy = closes[MARKET_BENCHMARK]

    sectors = {}
    for ticker in sorted({t for g in SECTOR_GROUPS.values() for t in g}):
        if ticker in closes:
            try:
                sectors[ticker] = trail_payload(closes[ticker], spy)
            except Exception as exc:
                print(f"{label} sector {ticker}: {exc}")

    industries = {}
    for ticker in sorted({t for g in INDUSTRY_GROUPS.values() for t in g}):
        if ticker in closes:
            try:
                industries[ticker] = trail_payload(closes[ticker], spy)
            except Exception as exc:
                print(f"{label} industry {ticker}: {exc}")

    stocks = {}
    for sector, members in STOCK_GROUPS.items():
        sector_bench = closes.get(sector)
        vs_spy = {}
        vs_sector = {}
        for ticker in members:
            if ticker not in closes:
                continue
            try:
                vs_spy[ticker] = trail_payload(closes[ticker], spy)
            except Exception as exc:
                print(f"{label} stock {ticker} vs SPY: {exc}")
            if sector_bench is not None:
                try:
                    vs_sector[ticker] = trail_payload(closes[ticker], sector_bench)
                except Exception as exc:
                    print(f"{label} stock {ticker} vs {sector}: {exc}")
        stocks[sector] = {
            "vs_SPY": vs_spy,
            f"vs_{sector}": vs_sector,
            "sector_price": benchmark_payload(sector_bench) if sector_bench is not None else [],
        }

    validate_timeframe_output(label, closes, sectors, industries, stocks)

    # Daily and synthetic 4H absolute-price context is independent of the
    # relative-strength RRG. It is NOT an OHLC pivot or an execution signal.
    price_context = {}
    if label in ("1D", "4H"):
        for ticker in EXPECTED_STOCKS:
            try:
                price_context[ticker] = summarize_closes(closes[ticker])
            except Exception as exc:
                raise RuntimeError(f"{label} {ticker}: price context integrity failed: {exc}") from exc
        print(f"{label}: absolute-price trend context {len(price_context)}/{len(EXPECTED_STOCKS)} complete")

    return {
        "sectors": sectors,
        "industries": industries,
        "stocks": stocks,
        "price_context": price_context,
        "benchmark_price": benchmark_payload(spy),
    }


def main() -> None:
    # One clock for the whole build: every timeframe is cut at the same instant.
    build_now = now_utc()
    tickers = {
        MARKET_BENCHMARK,
        *[t for group in SECTOR_GROUPS.values() for t in group],
        *[t for group in INDUSTRY_GROUPS.values() for t in group],
        *[t for members in STOCK_GROUPS.values() for t in members],
    }

    timeframes = {}
    for label, cfg in CONFIGS.items():
        timeframes[label] = build_timeframe(label, cfg, sorted(tickers), build_now)

    Path("data/stocks").mkdir(parents=True, exist_ok=True)

    # Calibration/audit snapshot: recent daily closes for SPY + sector ETFs.
    # This lets us independently reproduce and compare candidate RRG formulas.
    audit_cfg = CONFIGS["1D"]
    audit_tickers = sorted({
        MARKET_BENCHMARK,
        *[t for group in SECTOR_GROUPS.values() for t in group],
        *[t for group in INDUSTRY_GROUPS.values() for t in group],
    })
    audit_data = download_prices(audit_tickers, audit_cfg)
    audit_prices = {}
    for ticker in audit_tickers:
        try:
            # Same completed-bar rule as 1D: the Rotation Lab page reads these
            # closes directly, so a still-forming session must not appear here.
            series = completed_only(close_series(audit_data, ticker).dropna(), "1d", build_now).tail(320)
            audit_prices[ticker] = [
                {"time": iso_label(idx), "close": round(float(value), 6)}
                for idx, value in series.items()
            ]
        except Exception as exc:
            print(f"audit missing {ticker}: {exc}")
    Path("data/rrg-audit.json").write_text(
        json.dumps({
            "generated_at": build_now.isoformat(),
            "completed_bars_only": True,
            "benchmark": MARKET_BENCHMARK,
            "timeframe": "1D",
            "prices": audit_prices,
        }, indent=2),
        encoding="utf-8",
    )

    health = {}
    for tf, block in timeframes.items():
        latest_bar = None
        bp = block.get("benchmark_price", [])
        if bp:
            latest_bar = bp[-1]["time"]
        sector_cov = len(block.get("sectors", {}))
        industry_cov = len(block.get("industries", {}))
        stock_cov = sum(
            len(v.get("vs_SPY", {}))
            for v in block.get("stocks", {}).values()
        )
        latest_bar_end = BAR_END[CONFIGS[tf]["interval"]](latest_bar) if latest_bar else None
        if latest_bar_end is not None and latest_bar_end > _ny(build_now):
            raise RuntimeError(f"{tf}: latest bar {latest_bar} ends {latest_bar_end} after build clock {build_now}")
        health[tf] = {
            "latest_bar": latest_bar,
            "latest_bar_end": latest_bar_end.isoformat() if latest_bar_end is not None else None,
            "completed_bars_only": True,
            "sector_coverage": sector_cov,
            "sector_expected": len(EXPECTED_SECTORS),
            "industry_coverage": industry_cov,
            "industry_expected": len(EXPECTED_INDUSTRIES),
            "stock_coverage": stock_cov,
            "stock_expected": len(EXPECTED_STOCKS),
            "complete": (
                sector_cov == len(EXPECTED_SECTORS)
                and industry_cov == len(EXPECTED_INDUSTRIES)
                and stock_cov == len(EXPECTED_STOCKS)
            ),
        }

    core_payload = {
        "generated_at": build_now.isoformat(),
        "health": health,
        "benchmark": MARKET_BENCHMARK,
        "method": "EdgeRater-calibrated normalized public RRG approximation; not proprietary JdK indicators",
        "price_basis": "raw close",
        "absolute_price_context_note": "Raw Yahoo daily/synthetic 4H closes, EMA10/20 and prior completed 20-bar CLOSE extremes; not high/low swing pivots, not adjusted for splits, not live execution prices.",
        "data_source": "Yahoo Finance via yfinance",
        "stock_universe_note": "Curated liquid stock drilldown list; not an automatically synchronized ETF holdings file.",
        "stock_universe_reviewed": "2026-10-11",
        "validation": {
            "reference_date": "2026-10-09",
            "sector_quadrants_matched": "11/11",
            "industry_quadrants_matched": "15/16",
            "note": "Calibrated against user-provided EdgeRater daily reference screenshots. Exact EdgeRater/JdK formula and internal window defaults are undisclosed; use as a close public approximation, not an exact clone."
        },
        "params": {
            "smooth_wma": SMOOTH_WMA,
            "normalize_window": NORMALIZE_WINDOW,
            "momentum_roc": MOMENTUM_ROC,
            "momentum_wma": MOMENTUM_WMA,
            "normalize_scale": NORMALIZE_SCALE,
            "max_tail": TAIL_POINTS,
        },
        "universes": {
            "sectors": SECTOR_GROUPS,
            "industries": INDUSTRY_GROUPS,
            "stock_sectors": list(STOCK_GROUPS.keys()),
            "stock_members": STOCK_GROUPS,
        },
        "timeframes": {
            tf: {
                "sectors": block["sectors"],
                "industries": block["industries"],
                "benchmark_price": block["benchmark_price"],
            }
            for tf, block in timeframes.items()
        },
    }
    Path("data/rrg-core.json").write_text(
        json.dumps(core_payload, indent=2), encoding="utf-8"
    )

    for sector, members in STOCK_GROUPS.items():
        stock_payload = {
            "generated_at": core_payload["generated_at"],
            "benchmark": MARKET_BENCHMARK,
            "sector": sector,
            "members": members,
            "timeframes": {
                tf: {
                    "stock": block["stocks"].get(sector, {}),
                    "price_context": {t: block.get("price_context", {})[t] for t in members} if tf in ("1D", "4H") else {},
                    "benchmark_price": block["benchmark_price"],
                }
                for tf, block in timeframes.items()
            },
        }
        Path(f"data/stocks/{sector}.json").write_text(
            json.dumps(stock_payload, indent=2), encoding="utf-8"
        )

    # Keep the older combined file for compatibility while the UI migrates.
    legacy_payload = {
        **core_payload,
        "universes": {
            "sectors": SECTOR_GROUPS,
            "industries": INDUSTRY_GROUPS,
            "stocks": STOCK_GROUPS,
        },
        "timeframes": timeframes,
    }
    Path("data/rrg.json").write_text(
        json.dumps(legacy_payload, indent=2), encoding="utf-8"
    )

    if radar_bundle.enabled():
        session = core_payload["timeframes"]["1D"]["benchmark_price"][-1]["time"][:10]
        stock_payloads = {s: json.loads(Path(f"data/stocks/{s}.json").read_text()) for s in STOCK_GROUPS}
        radar_bundle.write(session, core_payload["generated_at"],
                           {"rrg_core": core_payload, "rrg_stocks": stock_payloads})

    for tf, block in timeframes.items():
        stock_count = sum(
            len(v.get("vs_SPY", {})) for v in block.get("stocks", {}).values()
        )
        print(
            f"{tf}: sectors={len(block['sectors'])}, "
            f"industries={len(block['industries'])}, stocks={stock_count}"
        )
    print("Generated lightweight rrg-core.json and lazy stock files")


if __name__ == "__main__":
    main()
