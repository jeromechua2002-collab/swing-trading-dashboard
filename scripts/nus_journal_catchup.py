#!/usr/bin/env python3
"""One-off: copy an explicit allowlist of trades from the production journal to the NUS copy.

Only trade numbers listed in NUS_CATCHUP_TRADES are created or updated. Every other
NUS row is left alone. The Account relation is pointed at the single NUS account
row; uploaded files cannot be re-used across workspaces and are reported, not copied.
Logs carry trade numbers and property names only.
"""
import os
import sys

import nus_notion_preflight as pf

TEXT = ("title", "rich_text")
PLAIN = ("number", "checkbox", "url", "email", "phone_number")


def rich(items):
    out = []
    for item in items or []:
        text = item.get("text") or {"content": item.get("plain_text", "")}
        out.append({"type": "text", "text": {"content": text.get("content", ""), "link": text.get("link")},
                    "annotations": item.get("annotations", {})})
    return out


def writable(prop, account_id):
    """Notion write payload for one property, or None when it must not be copied."""
    kind = prop.get("type")
    raw = prop.get(kind)
    if kind in TEXT:
        return {kind: rich(raw)}
    if kind in PLAIN:
        return {kind: raw}
    if kind in ("select", "status"):
        return {kind: {"name": raw["name"]} if raw else None}
    if kind == "multi_select":
        return {kind: [{"name": o["name"]} for o in raw or []]}
    if kind == "date":
        return {kind: {k: raw.get(k) for k in ("start", "end", "time_zone") if raw.get(k)} if raw else None}
    if kind == "relation":
        return {kind: [{"id": account_id}] if raw else []}
    return None


def build_properties(source_props, relation_name, account_id):
    props, skipped = {}, []
    for name, prop in source_props.items():
        if prop.get("type") in pf.COMPUTED:
            continue
        if prop.get("type") == "relation" and name != relation_name:
            skipped.append(name)
            continue
        payload = writable(prop, account_id)
        if payload is None:
            if prop.get(prop.get("type")):
                skipped.append(name)
            continue
        props[name] = payload
    return props, skipped


def catch_up(personal, nus, wanted, apply=False):
    personal_ids = {pf.norm(i) for i in pf.PERSONAL_IDS.values()}
    sources = nus.searchable_data_sources()
    located = {}
    for role in ("Trades", "Account"):
        copies, linked = pf.find_copy(sources, pf.title_of(personal.data_source(pf.PERSONAL_IDS[role])), personal_ids)
        if linked or len(copies) != 1:
            raise RuntimeError(f"{role}: no single independent NUS copy; run the preflight first")
        located[role] = nus.data_source(copies[0]["id"])

    trades_ds, account_ds = located["Trades"], located["Account"]
    accounts = nus.rows(account_ds["id"])
    if len(accounts) != 1:
        raise RuntimeError(f"NUS Account has {len(accounts)} rows; expected exactly 1")
    relation = [n for n, t in pf.relation_targets(trades_ds).items() if t == pf.norm(account_ds["id"])]
    if len(relation) != 1:
        raise RuntimeError("NUS Trades has no single relation to the NUS Account")

    p_rows = pf.keyed(personal.rows(pf.PERSONAL_IDS["Trades"]), "Trade #")
    n_rows = pf.keyed(nus.rows(trades_ds["id"]), "Trade #")
    for number in wanted:
        if len(p_rows.get(number, [])) != 1:
            raise RuntimeError(f"trade #{int(number)} is not a single production row")
        if len(n_rows.get(number, [])) > 1:
            raise RuntimeError(f"trade #{int(number)} is duplicated in NUS; fix by hand")

    for number in wanted:
        source = p_rows[number][0]
        props, skipped = build_properties(source["properties"], relation[0], accounts[0]["id"])
        action = "update" if number in n_rows else "create"
        note = f"; not copied: {sorted(skipped)}" if skipped else ""
        print(f"{'APPLY' if apply else 'PLAN '} {action} trade #{int(number)} ({len(props)} properties{note})", flush=True)
        if not apply:
            continue
        if action == "create":
            nus.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": trades_ds["id"]},
                                        "properties": props})
        else:
            nus.call("PATCH", f"/pages/{n_rows[number][0]['id']}", {"properties": props})


def main():
    raw = os.environ.get("NUS_CATCHUP_TRADES", "")
    wanted = sorted({float(x) for x in raw.split(",") if x.strip()})
    tokens = os.environ.get("NOTION_TOKEN", "").strip(), os.environ.get("NUS_TRADING_SYNC", "").strip()
    if not wanted or not all(tokens):
        print("FAIL NUS_CATCHUP_TRADES, NOTION_TOKEN and NUS_TRADING_SYNC are required")
        return 1
    try:
        catch_up(pf.Notion(tokens[0]), pf.Notion(tokens[1]), wanted, apply="--apply" in sys.argv)
    except (RuntimeError, PermissionError) as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
