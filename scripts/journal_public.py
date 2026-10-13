"""Privacy contract for the PUBLIC journal payload served by GitHub Pages.

The detailed journal (symbols, sizes, prices, fills, fees, FX, broker results,
notes, Notion links/IDs and every open position) stays private in Notion.
Only aggregated, closed-trade, percentage-normalized performance may be
published: an equity index (start = 100), daily realized return and counts.
No monetary amount is published, so starting capital cannot be recovered from
this file alone.
"""
from collections import defaultdict
from datetime import date
import math
import re

SCHEMA = "public-journal-v2"
SOURCE_STATUSES = {"notion_sync", "manual_snapshot"}
BASIS = ("Closed trades only, aggregated by exit date. Equity index starts at 100; "
         "returns are percentages of account equity. No positions, symbols, prices, "
         "sizes, fees or monetary amounts are published.")

TOP_KEYS = {"schema", "updated_at", "source_status", "basis", "closed_trade_count",
            "winning_trades", "losing_trades", "breakeven_trades", "realized_return_pct",
            "last_closed_date", "curve", "calendar"}
CURVE_KEYS = {"date", "index"}
CALENDAR_KEYS = {"return_pct", "closed_trades"}

# Defence in depth for any published journal-like JSON: key names or values
# that indicate private transaction detail. Matching is case-insensitive.
FORBIDDEN_KEY_PARTS = ("symbol", "ticker", "price", "size", "quantity", "qty", "fee",
                       "fill", "url", "note", "broker", "account", "fx", "sgd", "usd",
                       "open", "position", "entry", "exit", "notion", "capital", "equity_",
                       "pnl", "p_l", "cost", "proceeds", "holding")
FORBIDDEN_EXACT_KEYS = {"id", "number", "trades", "page_id", "start"}
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"notion\.(so|com|site)", re.I),
    re.compile(r"\b[0-9a-f]{32}\b", re.I),  # Notion page / data-source IDs
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"S?\$\s?\d"),
)


def _private_key(key):
    k = str(key).lower()
    return k in FORBIDDEN_EXACT_KEYS or any(part in k for part in FORBIDDEN_KEY_PARTS)


def find_private_markers(obj, path="$"):
    """Return a list of JSON paths that look like private transaction data."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}"
            if _private_key(k):
                hits.append(here)
            hits.extend(find_private_markers(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(find_private_markers(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(obj):
                hits.append(f"{path} (value matches {pattern.pattern})")
    return hits


def build_public(closed, start_capital, start_date, updated_at, source_status):
    """Aggregate private closed trades into the public payload.

    ``closed`` items need only ``exit_date`` (YYYY-MM-DD) and ``net_sgd``.
    Nothing else from the private records is read or copied.
    """
    if source_status not in SOURCE_STATUSES:
        raise ValueError("Unknown journal source status")
    if not (isinstance(start_capital, (int, float)) and math.isfinite(start_capital) and start_capital > 0):
        raise ValueError("Starting capital must be a positive number")
    by_day = defaultdict(list)
    for t in closed:
        day = date.fromisoformat(t["exit_date"]).isoformat()
        net = float(t["net_sgd"])
        if not math.isfinite(net):
            raise ValueError("Non-finite realized result")
        by_day[day].append(net)
    if start_date >= min(by_day, default="9999-12-31"):
        raise ValueError("Journal start date must precede the first closed trade")
    equity = float(start_capital)
    curve = [{"date": start_date, "index": 100.0}]
    calendar = {}
    for day in sorted(by_day):
        before = equity
        equity = before + sum(by_day[day])
        if equity <= 0:
            raise ValueError("Account equity index would be non-positive")
        calendar[day] = {"return_pct": round(100.0 * (equity / before - 1.0), 3),
                         "closed_trades": len(by_day[day])}
        curve.append({"date": day, "index": round(100.0 * equity / start_capital, 4)})
    nets = [n for day in by_day.values() for n in day]
    payload = {
        "schema": SCHEMA,
        "updated_at": updated_at,
        "source_status": source_status,
        "basis": BASIS,
        "closed_trade_count": len(nets),
        "winning_trades": sum(1 for n in nets if n > 0),
        "losing_trades": sum(1 for n in nets if n < 0),
        "breakeven_trades": sum(1 for n in nets if n == 0),
        "realized_return_pct": round(100.0 * (equity / start_capital - 1.0), 3),
        "last_closed_date": max(by_day) if by_day else None,
        "curve": curve,
        "calendar": calendar,
    }
    validate_public(payload)
    return payload


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def validate_public(p):
    """Raise ValueError unless ``p`` is exactly the allowlisted public schema."""
    if not isinstance(p, dict) or set(p) != TOP_KEYS:
        extra = sorted(set(p) - TOP_KEYS) if isinstance(p, dict) else []
        raise ValueError(f"Public journal keys must be exactly the allowlist; unexpected: {extra}")
    if p["schema"] != SCHEMA or p["basis"] != BASIS:
        raise ValueError("Unknown public journal schema")
    if p["source_status"] not in SOURCE_STATUSES:
        raise ValueError("Unknown journal source status")
    if not isinstance(p["updated_at"], str) or "T" not in p["updated_at"]:
        raise ValueError("updated_at must be an ISO timestamp")
    counts = ("closed_trade_count", "winning_trades", "losing_trades", "breakeven_trades")
    if not all(_count(p[k]) for k in counts):
        raise ValueError("Trade counts must be non-negative integers")
    if p["winning_trades"] + p["losing_trades"] + p["breakeven_trades"] != p["closed_trade_count"]:
        raise ValueError("Win/loss counts do not sum to closed trades")
    if not _num(p["realized_return_pct"]):
        raise ValueError("realized_return_pct must be finite")
    curve, cal = p["curve"], p["calendar"]
    if not isinstance(curve, list) or not curve or not isinstance(cal, dict):
        raise ValueError("Curve/calendar missing")
    for pt in curve:
        if not isinstance(pt, dict) or set(pt) != CURVE_KEYS or not _num(pt["index"]) or pt["index"] <= 0:
            raise ValueError("Curve points must be {date, index>0} only")
        date.fromisoformat(pt["date"])
    dates = [pt["date"] for pt in curve]
    if dates != sorted(set(dates)) or curve[0]["index"] != 100.0:
        raise ValueError("Curve must start at 100 with strictly increasing dates")
    if dates[1:] != sorted(cal):
        raise ValueError("Curve dates must match calendar dates")
    total = 0
    for day, row in cal.items():
        date.fromisoformat(day)
        if not isinstance(row, dict) or set(row) != CALENDAR_KEYS:
            raise ValueError("Calendar rows must be {return_pct, closed_trades} only")
        if not _num(row["return_pct"]) or not _count(row["closed_trades"]) or row["closed_trades"] < 1:
            raise ValueError("Invalid calendar row")
        total += row["closed_trades"]
    if total != p["closed_trade_count"]:
        raise ValueError("Calendar trade counts do not sum to closed trades")
    for prev, cur in zip(curve, curve[1:]):
        implied = prev["index"] * (1 + cal[cur["date"]]["return_pct"] / 100.0)
        if abs(implied - cur["index"]) > 0.01:
            raise ValueError(f"Equity index does not compound from daily return on {cur['date']}")
    if abs((curve[-1]["index"] - 100.0) - p["realized_return_pct"]) > 0.001:
        raise ValueError("Realized return does not match final equity index")
    if p["last_closed_date"] != (dates[-1] if len(dates) > 1 else None):
        raise ValueError("last_closed_date mismatch")
    hits = [h for h in find_private_markers(p) if not h.startswith("$.basis")]
    if hits:
        raise ValueError("Private markers in public journal: " + ", ".join(hits[:8]))
    return p
