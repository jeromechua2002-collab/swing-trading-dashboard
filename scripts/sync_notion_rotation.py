import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

NOTION_VERSION = "2025-09-03"
CHART_DATA_SOURCE_ID = os.getenv(
    "NOTION_ROTATION_CHART_DS", "485d139e-0f47-45b2-bce8-bbd40f29bf33"
)
SIGNAL_DATA_SOURCE_ID = os.getenv(
    "NOTION_ROTATION_SIGNAL_DS", "57786668-c8d4-4604-b009-a1706766cec3"
)

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

# Model benchmark is intentionally peer-aware. The chart itself remains SPY-relative
# so different industries are still visually comparable in one view.
INDUSTRY_BENCHMARK = {
    "SMH": "XLK", "IGV": "XLK", "FDN": "XLK",
    "XOP": "XLE", "OIH": "XLE", "XME": "XLB", "TAN": "SPY", "PBW": "SPY",
    "KRE": "XLF", "KIE": "XLF", "VNQ": "XLRE",
    "XRT": "XLY", "ITB": "XLY", "ITA": "XLI", "JETS": "XLI",
    "IBB": "XLV",
}

WINDOWS = {
    "5D": 5,
    "10D": 10,
    "20D": 20,
    "60D": 60,
    "MTD": "MTD",
    "YTD": "YTD",
}

# Keep the Notion chart light enough to read and to sync reliably.
WINDOW_SAMPLES = {
    "5D": 6,
    "10D": 8,
    "20D": 11,
    "60D": 13,
    "MTD": 11,
    "YTD": 16,
}

ALL_SECTORS = [t for members in SECTOR_GROUPS.values() for t in members]
ALL_INDUSTRIES = [t for members in INDUSTRY_GROUPS.values() for t in members]
ALL_TICKERS = sorted(set(["SPY", *ALL_SECTORS, *ALL_INDUSTRIES]))


def notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_request(method, url, token, **kwargs):
    headers = notion_headers(token)
    for attempt in range(7):
        resp = requests.request(method, url, headers=headers, timeout=45, **kwargs)
        if resp.status_code == 429:
            delay = float(resp.headers.get("Retry-After", "1.5"))
            time.sleep(max(delay, 1.0))
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(min(2 ** attempt, 20))
            continue
        if not resp.ok:
            body = resp.text[:1200]
            raise RuntimeError(
                f"Notion API {resp.status_code} for {method} {url}: {body}"
            )
        if resp.content:
            return resp.json()
        return {}
    raise RuntimeError(f"Notion request failed after retries: {method} {url}")


def probe_notion_access(token):
    me = notion_request("GET", "https://api.notion.com/v1/users/me", token)
    print(
        "Notion token valid for integration:",
        me.get("name") or me.get("id") or "unknown"
    )
    for label, data_source_id in [
        ("Rotation Chart Data v2", CHART_DATA_SOURCE_ID),
        ("Rotation Signal Snapshot", SIGNAL_DATA_SOURCE_ID),
    ]:
        try:
            ds = notion_request(
                "GET",
                f"https://api.notion.com/v1/data_sources/{data_source_id}",
                token,
            )
            print(f"Access OK: {label} -> {ds.get('id', data_source_id)}")
        except Exception as exc:
            raise RuntimeError(
                f"Notion integration cannot access '{label}' "
                f"(data source {data_source_id}). Open that exact database in Notion "
                f"and add the integration under ••• > Connections. Details: {exc}"
            ) from exc


def query_all_pages(data_source_id, token):
    url = f"https://api.notion.com/v1/data_sources/{data_source_id}/query"
    results = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = notion_request("POST", url, token, json=payload)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def extract_title(page, prop_name):
    prop = page.get("properties", {}).get(prop_name, {})
    return "".join(x.get("plain_text", "") for x in prop.get("title", []))


def prop_title(value):
    return {"title": [{"type": "text", "text": {"content": str(value)}}]}


def prop_text(value):
    if value is None:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": str(value)[:1900]}}]}


def prop_select(value):
    return {"select": None if value is None else {"name": str(value)}}


def prop_multi(values):
    return {"multi_select": [{"name": str(v)} for v in values]}


def prop_number(value):
    if value is None or not np.isfinite(value):
        return {"number": None}
    return {"number": float(value)}


def prop_date(value):
    return {"date": None if value is None else {"start": str(value)}}


def create_page(data_source_id, properties, token):
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }
    return notion_request("POST", "https://api.notion.com/v1/pages", token, json=payload)


def update_page(page_id, properties, token):
    payload = {"properties": properties}
    return notion_request(
        "PATCH", f"https://api.notion.com/v1/pages/{page_id}", token, json=payload
    )


def deactivate_chart_page(page_id, token):
    return update_page(
        page_id,
        {
            "Date": prop_date(None),
            "Relative Performance %": prop_number(None),
            "Updated": prop_date(datetime.now(timezone.utc).date().isoformat()),
        },
        token,
    )


def close_series(downloaded, ticker):
    if isinstance(downloaded.columns, pd.MultiIndex):
        lv0 = downloaded.columns.get_level_values(0)
        lv1 = downloaded.columns.get_level_values(1)
        if ticker in lv0:
            block = downloaded[ticker]
            if "Close" in block.columns:
                return block["Close"].dropna()
            return block.iloc[:, 0].dropna()
        if ticker in lv1 and "Close" in lv0:
            return downloaded["Close"][ticker].dropna()
    if ticker == "SPY" and "Close" in downloaded.columns:
        return downloaded["Close"].dropna()
    raise KeyError(f"Close data unavailable for {ticker}")


def align(asset, benchmark):
    df = pd.concat([asset.rename("asset"), benchmark.rename("bench")], axis=1).dropna()
    return df[(df["asset"] > 0) & (df["bench"] > 0)]


def relative_curve(asset, benchmark, window):
    pair = align(asset, benchmark)
    if isinstance(window, int):
        pair = pair.tail(window + 1)
    elif window == "MTD":
        if pair.empty:
            return pd.Series(dtype=float)
        last = pair.index[-1]
        pair = pair[(pair.index.year == last.year) & (pair.index.month == last.month)]
    elif window == "YTD":
        if pair.empty:
            return pd.Series(dtype=float)
        last = pair.index[-1]
        pair = pair[pair.index.year == last.year]
    if len(pair) < 2:
        return pd.Series(dtype=float)
    return 100.0 * (
        pair["asset"] / pair["asset"].iloc[0] - pair["bench"] / pair["bench"].iloc[0]
    )


def sample_series(series, points):
    series = series.dropna()
    if len(series) <= points:
        return series
    idx = np.unique(np.round(np.linspace(0, len(series) - 1, points)).astype(int))
    return series.iloc[idx]


def regression_stats(values):
    s = pd.Series(values, dtype=float).dropna()
    if len(s) < 2:
        return {"slope": 0.0, "r2": 0.0, "rmse": 0.0}
    x = np.arange(len(s), dtype=float)
    y = s.to_numpy(dtype=float)
    coeff = np.polyfit(x, y, 1)
    pred = coeff[0] * x + coeff[1]
    resid = y - pred
    sse = float(np.sum(resid ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    return {"slope": float(coeff[0]), "r2": float(r2), "rmse": rmse}


def percentile_rank(values, current):
    s = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty or not np.isfinite(current):
        return 50.0
    return float((s <= current).mean() * 100.0)


def rolling_relative_20d(asset, benchmark):
    pair = align(asset, benchmark)
    a = pair["asset"]
    b = pair["bench"]
    out = 100.0 * ((a / a.shift(20) - 1.0) - (b / b.shift(20) - 1.0))
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def model_metrics(ticker, asset, benchmark):
    curve = relative_curve(asset, benchmark, 20)
    if len(curve) < 10:
        raise RuntimeError(f"{ticker}: insufficient 20D observations")
    slow = regression_stats(curve.tail(20))
    fast = regression_stats(curve.tail(5))
    prior = regression_stats(curve.iloc[-10:-5]) if len(curve) >= 10 else slow
    acceleration = fast["slope"] - prior["slope"]
    rel20 = float(curve.iloc[-1])
    hist = rolling_relative_20d(asset, benchmark).tail(252)
    self_pct = percentile_rank(hist, rel20)
    return {
        "rel20": rel20,
        "fast": fast["slope"],
        "slow": slow["slope"],
        "accel": acceleration,
        "r2": slow["r2"],
        "rmse": slow["rmse"],
        "self_pct": self_pct,
    }


def classify(metric):
    level = metric["rel20"]
    fast = metric["fast"]
    accel = metric["accel"]

    if level > 0 and fast > 0 and accel >= 0:
        state = "Accelerating Leader"
    elif level > 0 and fast < 0 and accel < 0:
        state = "Fading Leader"
    elif level < 0 and fast > 0 and accel > 0:
        state = "Improving Laggard"
    elif level < 0 and fast < 0 and accel < 0:
        state = "Weak Laggard"
    else:
        state = "Transition"

    r2 = metric["r2"]
    confidence = "High" if r2 >= 0.65 else "Medium" if r2 >= 0.40 else "Low"

    pct = metric["self_pct"]
    slow = metric["slow"]
    if (level > 0 and slow > 0 and pct >= 70) or (level < 0 and slow < 0 and pct <= 30):
        persistence = "High"
    elif (level > 0 and slow < 0) or (level < 0 and slow > 0):
        persistence = "Low"
    else:
        persistence = "Normal"

    return state, confidence, persistence


def build_chart_rows(closes):
    spy = closes["SPY"]
    rows = []
    asof = spy.index[-1].date().isoformat()

    ticker_group = {}
    for group, members in SECTOR_GROUPS.items():
        for ticker in members:
            ticker_group[ticker] = ("Sector", group)
    for group, members in INDUSTRY_GROUPS.items():
        for ticker in members:
            ticker_group[ticker] = ("Industry", group)

    for ticker in [*ALL_SECTORS, *ALL_INDUSTRIES]:
        if ticker not in closes:
            continue
        universe, group = ticker_group[ticker]
        for window_name, window in WINDOWS.items():
            curve = relative_curve(closes[ticker], spy, window)
            sampled = sample_series(curve, WINDOW_SAMPLES[window_name])
            for slot, (idx, value) in enumerate(sampled.items()):
                rows.append(
                    {
                        "key": f"{ticker}|{window_name}|{slot:02d}",
                        "date": pd.Timestamp(idx).date().isoformat(),
                        "ticker": ticker,
                        "universe": universe,
                        "group": group,
                        "lens": [universe, group],
                        "window": window_name,
                        "value": float(value),
                        "benchmark": "SPY",
                        "updated": asof,
                    }
                )
    return rows


def build_signal_rows(closes):
    raw = []
    asof = closes["SPY"].index[-1].date().isoformat()

    ticker_group = {}
    for group, members in SECTOR_GROUPS.items():
        for ticker in members:
            ticker_group[ticker] = ("Sector", group)
    for group, members in INDUSTRY_GROUPS.items():
        for ticker in members:
            ticker_group[ticker] = ("Industry", group)

    for ticker in [*ALL_SECTORS, *ALL_INDUSTRIES]:
        if ticker not in closes:
            continue
        universe, group = ticker_group[ticker]
        benchmark_ticker = "SPY" if universe == "Sector" else INDUSTRY_BENCHMARK[ticker]
        if benchmark_ticker not in closes:
            continue
        metric = model_metrics(ticker, closes[ticker], closes[benchmark_ticker])
        raw.append(
            {
                "ticker": ticker,
                "universe": universe,
                "group": group,
                "benchmark": benchmark_ticker,
                **metric,
            }
        )

    # Cross-sectional rank is sector-wide for sectors and peer-group-specific for industries.
    for row in raw:
        if row["universe"] == "Sector":
            peers = [x["rel20"] for x in raw if x["universe"] == "Sector"]
        else:
            peers = [x["rel20"] for x in raw if x["group"] == row["group"]]
        row["peer_rank"] = percentile_rank(peers, row["rel20"])
        state, confidence, persistence = classify(row)
        row["state"] = state
        row["confidence"] = confidence
        row["persistence"] = persistence
        row["updated"] = asof
        row["note"] = (
            f"{state}: 20D relative level {row['rel20']:.2f}%, "
            f"fast slope {row['fast']:.3f}/day, slow slope {row['slow']:.3f}/day, "
            f"acceleration {row['accel']:.3f}, R² {row['r2']:.2f}. "
            f"Model benchmark: {row['benchmark']}; self-history percentile: {row['self_pct']:.0f}%."
        )
    return raw


def chart_properties(row):
    return {
        "Series": prop_title(row["key"]),
        "Date": prop_date(row["date"]),
        "Ticker": prop_select(row["ticker"]),
        "Universe": prop_select(row["universe"]),
        "Group": prop_select(row["group"]),
        "Lens": prop_multi(row["lens"]),
        "Window": prop_select(row["window"]),
        "Relative Performance %": prop_number(row["value"]),
        "Benchmark": prop_select(row["benchmark"]),
        "Updated": prop_date(row["updated"]),
    }


def signal_properties(row):
    return {
        "Ticker": prop_title(row["ticker"]),
        "Universe": prop_select(row["universe"]),
        "Group": prop_select(row["group"]),
        "State": prop_select(row["state"]),
        "Confidence": prop_select(row["confidence"]),
        "Rel 20D %": prop_number(row["rel20"]),
        "Fast Slope 5D": prop_number(row["fast"]),
        "Slow Slope 20D": prop_number(row["slow"]),
        "Acceleration": prop_number(row["accel"]),
        "Trend R2": prop_number(row["r2"]),
        "RMSE": prop_number(row["rmse"]),
        "Peer Rank %": prop_number(row["peer_rank"]),
        "Self Percentile %": prop_number(row["self_pct"]),
        "Persistence": prop_select(row["persistence"]),
        "Benchmark": prop_select(row["benchmark"]),
        "Signal Note": prop_text(row["note"]),
        "Updated": prop_date(row["updated"]),
    }


def upsert_chart(rows, token):
    existing_pages = query_all_pages(CHART_DATA_SOURCE_ID, token)
    existing = {extract_title(p, "Series"): p for p in existing_pages if extract_title(p, "Series")}
    target_keys = {r["key"] for r in rows}

    created = updated = deactivated = 0
    for row in rows:
        props = chart_properties(row)
        page = existing.get(row["key"])
        if page:
            update_page(page["id"], props, token)
            updated += 1
        else:
            create_page(CHART_DATA_SOURCE_ID, props, token)
            created += 1
        time.sleep(0.34)

    # Deactivate prototype rows and any no-longer-used slots without deleting anything.
    for key, page in existing.items():
        if key not in target_keys:
            deactivate_chart_page(page["id"], token)
            deactivated += 1
            time.sleep(0.34)

    print(f"Chart sync: created={created}, updated={updated}, deactivated={deactivated}")


def upsert_signals(rows, token):
    existing_pages = query_all_pages(SIGNAL_DATA_SOURCE_ID, token)
    existing = {extract_title(p, "Ticker"): p for p in existing_pages if extract_title(p, "Ticker")}

    created = updated = 0
    for row in rows:
        props = signal_properties(row)
        page = existing.get(row["ticker"])
        if page:
            update_page(page["id"], props, token)
            updated += 1
        else:
            create_page(SIGNAL_DATA_SOURCE_ID, props, token)
            created += 1
        time.sleep(0.34)

    print(f"Signal sync: created={created}, updated={updated}")


def main():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN is required")

    probe_notion_access(token)

    downloaded = yf.download(
        tickers=ALL_TICKERS,
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="ticker",
    )

    closes = {}
    for ticker in ALL_TICKERS:
        try:
            closes[ticker] = close_series(downloaded, ticker)
        except Exception as exc:
            print(f"Missing {ticker}: {exc}")

    if "SPY" not in closes:
        raise RuntimeError("SPY close data unavailable")

    chart_rows = build_chart_rows(closes)
    signal_rows = build_signal_rows(closes)

    print(
        f"Prepared {len(chart_rows)} chart rows and {len(signal_rows)} signal rows "
        f"for close {closes['SPY'].index[-1]}"
    )

    upsert_chart(chart_rows, token)
    upsert_signals(signal_rows, token)
    print("Notion rotation sync completed")


if __name__ == "__main__":
    main()
