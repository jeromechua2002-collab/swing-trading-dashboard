#!/usr/bin/env python3
"""Read-only preflight for moving the Notion pipelines to the NUS workspace.

Compares the production (personal) data sources with their NUS copies:
Trades, Account, Rotation Chart Data v2 and Rotation Signal Snapshot.
Nothing is written to either workspace and nothing is written to disk.

Logs are public on a public repository, so this prints counts, property
names, trade numbers and market-data dates only: never symbols, sizes,
prices, broker results, FX, notes, Notion IDs or open-position detail.
Exit code 1 when any check FAILs.
"""
import os
import sys
import time
from collections import Counter

import requests

API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"

PERSONAL_IDS = {
    "Trades": os.environ.get("NOTION_TRADES_DS", "bdf1e381-ccd7-820d-b18c-07a3337c985f"),
    "Account": os.environ.get("NOTION_ACCOUNT_DS", "440c247d-ba22-4faa-9e94-b8c6cde988b6"),
    "Rotation Chart": os.environ.get("NOTION_ROTATION_CHART_DS", "485d139e-0f47-45b2-bce8-bbd40f29bf33"),
    "Rotation Signal": os.environ.get("NOTION_ROTATION_SIGNAL_DS", "57786668-c8d4-4604-b009-a1706766cec3"),
}
# Title property and market-data date properties used by sync_notion_rotation.py.
ROTATION_KEYS = {"Rotation Chart": ("Series", ["Date", "Updated"]),
                 "Rotation Signal": ("Ticker", ["Updated"])}
COMPUTED = {"formula", "rollup", "created_time", "last_edited_time", "created_by", "last_edited_by", "unique_id"}
LATEST_TRADES = 3


def norm(value):
    return (value or "").replace("-", "").lower()


class Notion:
    def __init__(self, token, http=None):
        self.token = token
        self.http = http or requests.request

    def call(self, method, path, payload=None):
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION,
                   "Content-Type": "application/json"}
        for attempt in range(6):
            resp = self.http(method, f"{API}{path}", headers=headers, json=payload, timeout=45)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(min(float(resp.headers.get("Retry-After", 2 ** attempt)), 20))
                continue
            if not resp.ok:
                # The body can carry page or property detail, so only the status is kept.
                raise PermissionError(resp.status_code) if resp.status_code in (401, 403, 404) \
                    else RuntimeError(f"Notion HTTP {resp.status_code}")
            return resp.json()
        raise RuntimeError("Notion request failed after retries")

    def paged(self, method, path, payload=None):
        out, cursor = [], None
        while True:
            body = dict(payload or {}, page_size=100)
            if cursor:
                body["start_cursor"] = cursor
            data = self.call(method, path, body)
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                return out
            cursor = data.get("next_cursor")
            if not cursor:
                raise RuntimeError("Notion pagination cursor missing")

    def data_source(self, ds_id):
        return self.call("GET", f"/data_sources/{ds_id}")

    def rows(self, ds_id):
        return self.paged("POST", f"/data_sources/{ds_id}/query")

    def searchable_data_sources(self):
        return self.paged("POST", "/search", {"filter": {"property": "object", "value": "data_source"}})


def title_of(ds):
    return "".join(t.get("plain_text", "") for t in ds.get("title", [])).strip()


def schema(ds):
    return {name: prop.get("type") for name, prop in ds.get("properties", {}).items()}


def schema_diff(personal, nus):
    return {
        "missing": sorted(set(personal) - set(nus)),
        "extra": sorted(set(nus) - set(personal)),
        "type_changed": sorted(n for n in set(personal) & set(nus) if personal[n] != nus[n]),
    }


def relation_targets(ds):
    return {name: norm((prop.get("relation") or {}).get("data_source_id"))
            for name, prop in ds.get("properties", {}).items() if prop.get("type") == "relation"}


def value(prop):
    """Comparable form of one property value; relations and files compare by count only."""
    kind = prop.get("type")
    raw = prop.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in raw or [])
    if kind in ("select", "status"):
        return (raw or {}).get("name")
    if kind == "multi_select":
        return tuple(sorted(o.get("name") for o in raw or []))
    if kind == "date":
        return ((raw or {}).get("start"), (raw or {}).get("end"))
    if kind in ("relation", "files", "people"):
        return len(raw or [])
    if kind == "formula":
        return value({"type": (raw or {}).get("type"), (raw or {}).get("type"): (raw or {}).get((raw or {}).get("type"))})
    if kind == "number" and raw is not None:
        return round(float(raw), 10)
    return raw


def keyed(rows, key):
    groups = {}
    for row in rows:
        prop = row.get("properties", {}).get(key)
        k = value(prop) if prop else None
        if k is not None and k != "":
            groups.setdefault(k, []).append(row)
    return groups


def compare_rows(p_rows, n_rows, key, compare_names):
    """Match rows by key and name the fields that differ. Values never leave this function."""
    p, n = keyed(p_rows, key), keyed(n_rows, key)
    result = {
        "personal_rows": len(p_rows), "nus_rows": len(n_rows),
        "unkeyed_nus": len(n_rows) - sum(len(v) for v in n.values()),
        "duplicate_keys_nus": sorted(k for k, v in n.items() if len(v) > 1),
        "duplicate_keys_personal": sorted(k for k, v in p.items() if len(v) > 1),
        "missing_in_nus": sorted(set(p) - set(n)), "extra_in_nus": sorted(set(n) - set(p)),
        "mismatched": {},
    }
    for k in sorted(set(p) & set(n)):
        if len(p[k]) != 1 or len(n[k]) != 1:
            continue
        pp, nn = p[k][0]["properties"], n[k][0]["properties"]
        diff = sorted(name for name in compare_names
                      if value(pp.get(name, {"type": None})) != value(nn.get(name, {"type": None})))
        if diff:
            result["mismatched"][k] = diff
    return result


def latest_dates(rows, names):
    out = {}
    for name in names:
        dates = [value(r.get("properties", {}).get(name, {"type": None})) for r in rows]
        starts = sorted(d[0][:10] for d in dates if isinstance(d, tuple) and d[0])
        out[name] = {"latest": starts[-1] if starts else None, "distinct": len(set(starts))}
    return out


class Report:
    def __init__(self):
        self.lines, self.failed = [], False

    def add(self, status, message):
        self.failed |= status == "FAIL"
        self.lines.append(f"{status:4} {message}")
        print(self.lines[-1], flush=True)


def find_copy(nus_sources, wanted_title, personal_ids):
    """NUS data sources with the same title. A linked view would surface the original ID."""
    same = [ds for ds in nus_sources if title_of(ds) == wanted_title]
    return [ds for ds in same if norm(ds.get("id")) not in personal_ids], \
           [ds for ds in same if norm(ds.get("id")) in personal_ids]


def run(personal, nus, report=None):
    report = report or Report()
    personal_ids = {norm(i) for i in PERSONAL_IDS.values()}
    nus_sources = nus.searchable_data_sources()
    report.add("INFO", f"NUS integration can see {len(nus_sources)} data source(s)")
    found = {}

    for role, p_id in PERSONAL_IDS.items():
        p_ds = personal.data_source(p_id)
        wanted = title_of(p_ds)
        copies, linked = find_copy(nus_sources, wanted, personal_ids)
        if linked:
            report.add("FAIL", f"{role}: NUS sees the ORIGINAL personal data source (linked view, not a copy)")
        if len(copies) != 1:
            report.add("FAIL", f"{role}: expected exactly 1 independent NUS copy titled like production, found {len(copies)}"
                       + ("; share the copied database with the NUS integration" if not copies else "; remove or rename duplicates"))
            continue
        n_ds = nus.data_source(copies[0]["id"])
        found[role] = (p_ds, n_ds)
        try:
            nus.data_source(p_id)
            report.add("WARN", f"{role}: NUS token can also read the personal original; confirm the workspaces are separate")
        except PermissionError:
            report.add("PASS", f"{role}: independent copy found; NUS token cannot read the personal original")

        diff = schema_diff(schema(p_ds), schema(n_ds))
        if any(diff.values()):
            report.add("FAIL", f"{role}: schema differs: missing={diff['missing']} extra={diff['extra']} type_changed={diff['type_changed']}")
        else:
            report.add("PASS", f"{role}: schema identical ({len(schema(p_ds))} properties)")

    # Relations in NUS copies must point at NUS data sources, never back at personal ones.
    nus_ids = {norm(n["id"]) for _, n in found.values()}
    for role, (_, n_ds) in found.items():
        for name, target in relation_targets(n_ds).items():
            if target in personal_ids:
                report.add("FAIL", f"{role}: relation '{name}' still targets a personal database")
            elif target not in nus_ids:
                report.add("WARN", f"{role}: relation '{name}' targets a data source outside the four checked")
            else:
                report.add("PASS", f"{role}: relation '{name}' targets the NUS copy")

    if "Trades" in found:
        p_ds, n_ds = found["Trades"]
        fields = [n for n, t in schema(p_ds).items() if t not in COMPUTED and n != "Trade #"]
        p_rows, n_rows = personal.rows(p_ds["id"]), nus.rows(n_ds["id"])
        cmp = compare_rows(p_rows, n_rows, "Trade #", fields)
        report.add("PASS" if cmp["personal_rows"] == cmp["nus_rows"] else "FAIL",
                   f"Trades: rows personal={cmp['personal_rows']} nus={cmp['nus_rows']}")
        for label in ("duplicate_keys_nus", "missing_in_nus", "extra_in_nus"):
            if cmp[label]:
                report.add("FAIL", f"Trades: {label.replace('_', ' ')}: trade #{', #'.join(str(int(k)) for k in cmp[label])}")
        if cmp["unkeyed_nus"]:
            report.add("FAIL", f"Trades: {cmp['unkeyed_nus']} NUS row(s) without a trade number")
        for k, names in cmp["mismatched"].items():
            report.add("FAIL", f"Trades: trade #{int(k)} differs in {names}")
        latest = sorted(k for k in keyed(p_rows, "Trade #"))[-LATEST_TRADES:]
        ok = [k for k in latest if k in keyed(n_rows, "Trade #") and k not in cmp["mismatched"]
              and k not in cmp["duplicate_keys_nus"]]
        report.add("PASS" if len(ok) == len(latest) else "FAIL",
                   f"Trades: latest {len(latest)} production trades present once and identical in NUS: {len(ok)}/{len(latest)}")
        computed = [n for n, t in schema(p_ds).items() if t == "formula"]
        formula_cmp = compare_rows(p_rows, n_rows, "Trade #", computed)
        if formula_cmp["mismatched"]:
            report.add("FAIL", f"Trades: formula results differ for {len(formula_cmp['mismatched'])} trade(s); check relations and formulas")
        else:
            report.add("PASS", f"Trades: all {len(computed)} formula results match")

    if "Account" in found:
        p_ds, n_ds = found["Account"]
        p_n, n_n = len(personal.rows(p_ds["id"])), len(nus.rows(n_ds["id"]))
        report.add("PASS" if p_n == n_n else "FAIL", f"Account: rows personal={p_n} nus={n_n}")

    # Rotation must match exactly: keys, every stored value, active/inactive rows and latest dates.
    # (Earlier versions only reported rotation differences, which let a stale NUS copy PASS.)
    from nus_rotation_catchup import plan_role
    for role, (key, date_props) in ROTATION_KEYS.items():
        if role not in found:
            continue
        p_ds, n_ds = found[role]
        p_rows, n_rows = personal.rows(p_ds["id"]), nus.rows(n_ds["id"])
        fields = [f for f, t in schema(p_ds).items() if t not in COMPUTED]
        try:
            plan = plan_role(p_rows, n_rows, key, fields)
        except RuntimeError as exc:
            report.add("FAIL", f"{role}: {exc}")
            continue
        p_dates, n_dates = latest_dates(p_rows, date_props), latest_dates(n_rows, date_props)
        lagging = [d for d in date_props if p_dates[d]["latest"] != n_dates[d]["latest"]]
        diffs = len(plan["create"]) + len(plan["update"]) + plan["nus_only"]
        detail = (f"rows personal={len(p_rows)} nus={len(n_rows)}; missing={len(plan['create'])} differing={len(plan['update'])} "
                  f"nus_only={plan['nus_only']}; inactive {plan['inactive_prod']}/{plan['inactive_nus']}; "
                  + " ".join(f"latest {d} {p_dates[d]['latest']}/{n_dates[d]['latest']}" for d in date_props))
        report.add("FAIL" if diffs or lagging else "PASS", f"{role}: {detail}")
    return report


def main():
    personal_token = os.environ.get("NOTION_TOKEN", "").strip()
    nus_token = (os.environ.get("NUS_TRADING_SYNC") or os.environ.get("NOTION_NUS_TOKEN") or "").strip()
    if not personal_token or not nus_token:
        print("FAIL both NOTION_TOKEN and the NUS integration token (NUS_TRADING_SYNC) are required")
        return 1
    try:
        report = run(Notion(personal_token), Notion(nus_token))
    except PermissionError as exc:
        print(f"FAIL Notion access denied (HTTP {exc}); share each database with the integration")
        return 1
    print("RESULT", "FAIL" if report.failed else "PASS")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
