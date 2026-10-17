#!/usr/bin/env python3
"""Rotation-only catch-up and strict parity check: production -> NUS.

Only Rotation Chart Data v2 (key: Series) and Rotation Signal Snapshot (key: Ticker)
are read or written; no journal, account or other data source is reachable from here.
Rows are matched by key; differing rows are updated, missing keys created, and nothing
is deleted. Without --apply nothing is written and the exit code is the strict parity
result: 0 only when keys, values, active/inactive state and latest dates all match.
Logs carry counts and dates only.
"""
import sys

import nus_notion_preflight as pf

ROLES = {"Rotation Chart": "Series", "Rotation Signal": "Ticker"}


def rich(items):
    return [{"type": "text", "text": {"content": (i.get("text") or {}).get("content", i.get("plain_text", "")),
                                     "link": (i.get("text") or {}).get("link")},
             "annotations": i.get("annotations", {})} for i in items or []]


def writable(prop):
    kind, raw = prop.get("type"), prop.get(prop.get("type"))
    if kind in ("title", "rich_text"):
        return {kind: rich(raw)}
    if kind == "number":
        return {kind: raw}
    if kind == "select":
        return {kind: {"name": raw["name"]} if raw else None}
    if kind == "multi_select":
        return {kind: [{"name": o["name"]} for o in raw or []]}
    if kind == "date":
        return {kind: {k: raw.get(k) for k in ("start", "end", "time_zone") if raw.get(k)} if raw else None}
    raise RuntimeError(f"unsupported property type {kind}")


def same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9
    return a == b


def inactive(props):
    date = pf.value(props.get("Date", {"type": None}))
    return "Date" in props and (date is None or date == (None, None)) \
        and pf.value(props.get("Relative Performance %", {"type": None})) is None


def plan_role(p_rows, n_rows, key, fields):
    p, n = pf.keyed(p_rows, key), pf.keyed(n_rows, key)
    dup_p = [k for k, v in p.items() if len(v) > 1]
    dup_n = [k for k, v in n.items() if len(v) > 1]
    if dup_p or dup_n:
        raise RuntimeError(f"duplicate keys: production={len(dup_p)} nus={len(dup_n)}")
    create, update, unchanged = [], [], 0
    for k, (row,) in p.items():
        props = row["properties"]
        if k not in n:
            create.append(props)
            continue
        target = n[k][0]
        if all(same(pf.value(props.get(f, {"type": None})), pf.value(target["properties"].get(f, {"type": None}))) for f in fields):
            unchanged += 1
        else:
            update.append((target.get("id"), props))
    return {"create": create, "update": update, "unchanged": unchanged, "nus_only": len(set(n) - set(p)),
            "inactive_prod": sum(inactive(r["properties"]) for r in p_rows),
            "inactive_nus": sum(inactive(r["properties"]) for r in n_rows)}


def main():
    import os
    apply = "--apply" in sys.argv
    tokens = os.environ.get("NOTION_TOKEN", "").strip(), os.environ.get("NUS_TRADING_SYNC", "").strip()
    if not all(tokens):
        print("FAIL NOTION_TOKEN and NUS_TRADING_SYNC are required")
        return 1
    personal, nus = pf.Notion(tokens[0]), pf.Notion(tokens[1])
    ids = {pf.norm(i) for i in pf.PERSONAL_IDS.values()}
    sources, parity = nus.searchable_data_sources(), True
    for role, key in ROLES.items():
        p_ds = personal.data_source(pf.PERSONAL_IDS[role])
        copies, linked = pf.find_copy(sources, pf.title_of(p_ds), ids)
        if linked or len(copies) != 1:
            print(f"FAIL {role}: no single independent NUS copy")
            return 1
        n_ds = nus.data_source(copies[0]["id"])
        if pf.schema_diff(pf.schema(p_ds), pf.schema(n_ds)) != {"missing": [], "extra": [], "type_changed": []}:
            print(f"FAIL {role}: schemas differ")
            return 1
        fields = [f for f, t in pf.schema(p_ds).items() if t not in pf.COMPUTED]
        p_rows, n_rows = personal.rows(p_ds["id"]), nus.rows(n_ds["id"])
        try:
            plan = plan_role(p_rows, n_rows, key, fields)
        except RuntimeError as exc:
            print(f"FAIL {role}: {exc}")
            return 1
        dates = [f for f in ("Date", "Updated") if f in fields]
        latest_p, latest_n = pf.latest_dates(p_rows, dates), pf.latest_dates(n_rows, dates)
        print(f"{'APPLY' if apply else 'PLAN '} {role}: create={len(plan['create'])} update={len(plan['update'])} "
              f"unchanged={plan['unchanged']} nus_only={plan['nus_only']} | rows production={len(p_rows)} nus={len(n_rows)} "
              f"| inactive production={plan['inactive_prod']} nus={plan['inactive_nus']} | "
              + " ".join(f"latest {d} production={latest_p[d]['latest']} nus={latest_n[d]['latest']}" for d in dates), flush=True)
        role_ok = not plan["create"] and not plan["update"] and not plan["nus_only"] \
            and all(latest_p[d]["latest"] == latest_n[d]["latest"] for d in dates)
        parity &= role_ok
        if apply:
            for props in plan["create"]:
                nus.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": n_ds["id"]},
                                            "properties": {f: writable(props[f]) for f in fields if f in props}})
            for page_id, props in plan["update"]:
                nus.call("PATCH", f"/pages/{page_id}", {"properties": {f: writable(props[f]) for f in fields if f in props}})
    if not apply:
        print("PARITY", "PASS" if parity else "FAIL (differences listed above)")
        return 0 if parity else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
