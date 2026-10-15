#!/usr/bin/env python3
"""Export realized journal performance from Notion for the PUBLIC Pages views.

Private trade records are read and reconciled in memory only. The file written
to data/journal-performance.json is the allowlisted, percentage-normalized
payload from journal_public.py: no symbols, sizes, prices, fills, fees, FX,
broker results, notes, Notion links/IDs or open positions are ever published.
Logs are public on a public repository, so they carry counts only.
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

from journal_public import build_public, validate_public

DS = os.environ.get("NOTION_TRADES_DS", "bdf1e381-ccd7-820d-b18c-07a3337c985f")
ACCOUNT_ID = os.environ.get("NOTION_SWING_ACCOUNT_ID", "3f41e381ccd781529418f3214d1518f8")
API = "https://api.notion.com/v1"
START_DATE = "2026-09-30"
OUT = Path("data/journal-performance.json")


def start_capital():
    raw = os.environ.get("JOURNAL_START_CAPITAL_SGD", "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if value <= 0:
        raise RuntimeError("JOURNAL_START_CAPITAL_SGD secret missing or invalid; cannot normalize the public equity index")
    return value

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
        # Do not echo the response body: it can contain page/property detail.
        raise RuntimeError(f"Notion HTTP {exc.code}") from exc

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

def read_private_trades():
    """Return (closed, reconciliation_flags, unlinked_rows) held in memory only.

    A trade counts only when its Notion Account relation explicitly includes
    the swing account. Rows with an empty or different relation are excluded
    (there is no implicit "unlinked = swing" exception); a linked trade number
    sequence with gaps then fails loudly instead of silently changing results.
    """
    account=ACCOUNT_ID.replace("-","").lower()
    if not account:
        raise RuntimeError("Swing account identifier is not configured")
    rows=fetch_all()
    closed=[]; seen=set(); flagged=0; unlinked=0; unlinked_numbers=set(); other_status=set()
    for row in rows:
        p=row.get("properties",{})
        status=sel(p.get("Trade Status"))
        number_id=number(p.get("Trade #"))
        if status not in ("Closed","Open"):
            if number_id: other_status.add(int(number_id))
            continue
        if account not in {x.lower() for x in related(p.get("Account"))}:
            unlinked+=1
            if number_id: unlinked_numbers.add(int(number_id))
            continue
        if not text(p.get("Symbol")): raise RuntimeError("A journal trade has no symbol")
        qty=number(p.get("Position Size"))
        if not number_id or number_id in seen: raise RuntimeError("Missing or duplicate trade number in linked account")
        seen.add(number_id)
        if status=="Open":
            continue  # counted for numbering only; never reported or published
        exitdate=date(p.get("Exit Date"))
        net=number(p.get("Broker Net P/L USD"))
        fx=number(p.get("FX USD/SGD"))
        if not exitdate or net is None:
            raise RuntimeError(f"Closed trade #{int(number_id)} has no exit date or net broker P/L")
        if fx is None or fx<=0: raise RuntimeError(f"Missing FX on closed trade #{int(number_id)}")
        # Broker-reported net P/L stays the source of truth. Exit legs and fees
        # are reconciled here but never copied into any output.
        fills=[]
        for n in (1,2):
            q=number(p.get(f"Exit {n} Qty"))
            px=number(p.get(f"Exit {n} Price"))
            if (q is None) != (px is None):
                raise RuntimeError(f"Trade #{int(number_id)} has incomplete exit leg {n}")
            if q is not None:
                if q<=0 or px<=0:
                    raise RuntimeError(f"Trade #{int(number_id)} has invalid exit leg {n}")
                fills.append((q,px))
        if fills and (qty is None or abs(sum(q for q,_ in fills)-qty)>1e-6):
            raise RuntimeError(f"Trade #{int(number_id)} exit lots do not reconcile to position")
        entry_price=number(p.get("Avg Entry")); fees=number(p.get("Fee Charges USD"))
        if fills and entry_price is not None and fees is not None:
            fill_net=sum(q*px for q,px in fills)-qty*entry_price-fees
            if abs(round(net-fill_net,2))>0.01:
                flagged+=1
        closed.append({"number":int(number_id),"exit_date":exitdate,"net_sgd":round(net*fx,2)})
    numbers={int(n) for n in seen}
    missing=sorted(set(range(1,max(numbers,default=0)+1))-numbers)
    if not numbers or missing:
        # Trade numbers alone carry no symbol, size or amount; naming each gap's
        # cause lets the owner fix Notion without exposing detail.
        raise RuntimeError(contiguity_error(missing or [1], unlinked_numbers, other_status))
    return closed, flagged, unlinked


def contiguity_error(missing, unlinked, other_status):
    """Explain each missing trade number by cause, using trade numbers only."""
    groups={"a Closed/Open row that is not linked to the swing account (link it)":[],
            "a row whose Trade Status is neither Closed nor Open (fix the status)":[],
            "no row in the trades database (if it was deleted, renumber the later trades)":[]}
    labels=list(groups)
    for n in missing:
        if n in unlinked: groups[labels[0]].append(n)
        elif n in other_status: groups[labels[1]].append(n)
        else: groups[labels[2]].append(n)
    causes="; ".join(f"#{', #'.join(map(str,ns))}: {why}" for why,ns in groups.items() if ns)
    return f"Journal trade numbers are not contiguous among swing-account trades. Missing {causes}."


def export(now=None, out=None):
    out = OUT if out is None else Path(out)
    closed, flagged, unlinked = read_private_trades()
    if len(closed) < 10:
        raise RuntimeError("Fewer closed trades than the verified history; refusing to publish")
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    public=build_public(closed, start_capital(), START_DATE, stamp, "notion_sync")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(public,indent=2)+"\n",encoding="utf-8")
    print(f"Journal sync: {public['closed_trade_count']} closed trades exported as a percentage index.")
    if unlinked:
        print(f"Journal sync: excluded {unlinked} journal row(s) not linked to the swing account.")
    if flagged:
        print(f"::notice::{flagged} closed trade(s) carry a broker-vs-fill reconciliation difference; broker P/L retained. Review in Notion.")
    return public


def keep_committed_snapshot(reason):
    """Fallback: serve the previously committed PUBLIC snapshot, never private data."""
    if not OUT.exists():
        raise SystemExit(f"Journal unavailable ({reason}) and no public snapshot exists")
    stored=json.loads(OUT.read_text(encoding="utf-8"))
    try:
        validate_public(stored)
    except ValueError as exc:
        raise SystemExit(f"Committed journal snapshot fails the public privacy contract: {exc}") from exc
    if stored["closed_trade_count"] < 10:
        raise SystemExit("Journal fallback snapshot incomplete")
    print(f"::warning::{reason}. Using the previously committed public snapshot; journal data remains stale.")


if __name__=="__main__":
    if "--check" in sys.argv:
        # Pull-request dry run: exercise the real Notion data and every guard,
        # write only to a throwaway temp file, publish nothing.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            try:
                export(out=Path(tmp) / "journal-check.json")
            except RuntimeError as exc:
                print(f"Journal dry run failed: {exc}", file=sys.stderr)
                raise SystemExit(1)
        print("Journal dry run passed: private data reconciled; nothing written or published.")
        raise SystemExit(0)
    try:
        export()
    except RuntimeError as exc:
        # The Rotation Sync integration may not yet be shared with the Trades database.
        if "Notion HTTP 404" in str(exc):
            keep_committed_snapshot("Notion Trades DB is not shared with the sync integration")
        else:
            print(f"Journal sync failed: {exc}", file=sys.stderr)
            raise SystemExit(1)
