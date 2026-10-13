"""Publication contract tying together RRG, sector breadth and the swing journal.

A successful GitHub Pages upload is not evidence that *all* datasets belong to
the same trading session. Verify cross-file coherence before publishing.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from journal_public import validate_public


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("Missing UTC source timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def create(root=Path("."), now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    files = {
        "rrg": "data/rrg-core.json",
        "breadth": "data/sector-breadth.json",
        "journal": "data/journal-performance.json",
    }
    payloads = {k: json.loads((root / name).read_text(encoding="utf-8"))
                for k, name in files.items()}
    core, breadth, journal = (payloads[k] for k in ("rrg", "breadth", "journal"))
    sectors = core["universes"]["stock_members"]
    sector_set = set(sectors)
    if len(sectors) != 11 or len(set(sum(sectors.values(), []))) != 116:
        raise ValueError("RRG stock universe not 11 sectors / 116 unique stocks")
    if set(core["timeframes"]) != {"1W", "1D", "4H", "1H"}:
        raise ValueError("RRG timeframe coverage incomplete")
    if sector_set != set(core["timeframes"]["1D"]["sectors"]):
        raise ValueError("Sector labels do not match 1D RRG")
    for tf in ("1D", "4H"):
        if len(core["timeframes"][tf]["industries"]) != 16:
            raise ValueError(f"{tf} industry universe incomplete")
    if breadth.get("status") != "ok" or len(breadth.get("rows", [])) != 11:
        raise ValueError("Equal-weight breadth feed is missing or invalid")
    if {x["cap"] for x in breadth["rows"]} != sector_set:
        raise ValueError("Breadth sector pairs do not align with RRG sectors")
    daily_session = core["timeframes"]["1D"]["benchmark_price"][-1]["time"][:10]
    if daily_session != breadth.get("as_of"):
        raise ValueError(f"RRG and equal-weight daily sessions differ: {daily_session} / {breadth.get('as_of')}")
    rrg_stamp, breadth_stamp = parse_time(core["generated_at"]), parse_time(breadth["generated_at"])
    if abs((rrg_stamp - breadth_stamp).total_seconds()) > 1800:
        raise ValueError("RRG and breadth built more than 30m apart")
    if rrg_stamp > now or breadth_stamp > now:
        raise ValueError("Market feed has a future generation timestamp")
    for sector, members in sectors.items():
        file = root / "data" / "stocks" / f"{sector}.json"
        d = json.loads(file.read_text(encoding="utf-8"))
        if d.get("generated_at") != core["generated_at"] or d.get("members") != members:
            raise ValueError(f"{sector}: stock/core snapshot mismatch")
        for tf in ("1D", "4H"):
            frame = d["timeframes"][tf]
            if set(frame.get("price_context", {})) != set(members):
                raise ValueError(f"{sector} {tf}: incomplete absolute price context")
    # The public journal is percentage-only and closed-trade-only by contract.
    validate_public(journal)
    if journal["closed_trade_count"] < 10:
        raise ValueError("Journal equity curve incomplete")
    journal_stamp = parse_time(journal["updated_at"])
    if journal_stamp > now:
        raise ValueError("Future journal timestamp")
    journal_state = journal["source_status"]
    hashes = {key: hashlib.sha256((root / path).read_bytes()).hexdigest()
              for key, path in files.items()}
    return {
        "schema_version": 1,
        "built_at": now.isoformat(),
        "commit": os.environ.get("GITHUB_SHA", "local-build"),
        "workflow_run": os.environ.get("GITHUB_RUN_ID", ""),
        "market_status": "validated_completed_session",
        "rrg_session": daily_session,
        "breadth_session": breadth["as_of"],
        "market_generated_at": core["generated_at"],
        "market_coverage": {
            "sectors": len(sectors),
            "industries": len(core["timeframes"]["1D"]["industries"]),
            "stocks": len(set(sum(sectors.values(), []))),
            "breadth_pairs": len(breadth["rows"]),
            "timeframes": 4,
        },
        "journal_status": journal_state,
        "journal_generated_at": journal["updated_at"],
        "journal_last_closed_trade": journal["last_closed_date"],
        "journal_closed_count": journal["closed_trade_count"],
        "journal_return_pct": journal["realized_return_pct"],
        "sha256": hashes,
        "caveats": [
            "Daily bars are completed sessions; not intraday real-time quotes",
            "RRG is an approximation; 4H bars may differ from TradingView",
            "Journal is closed-trade, percentage-only; detailed records stay private in Notion",
        ]
    }


if __name__ == "__main__":
    out = create()
    path = Path("data/release-manifest.json")
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE CONTRACT OK: {out['rrg_session']}, "
          f"{out['market_coverage']}, journal={out['journal_status']}, "
          f"closed={out['journal_closed_count']}")
