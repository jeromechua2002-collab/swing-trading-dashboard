#!/usr/bin/env python3
import json
from itertools import product
from pathlib import Path

from validate_rrg import EXACT, APPROX, QUADS, load_prices, normalized, score

OUT = Path("data/rrg-sensitivity.json")
LIVE = (10, 16, 5, 4)

SMOOTH_RANGE = range(8, 13)
WINDOW_RANGE = range(14, 21)
ROC_RANGE = range(4, 7)
MOM_SMOOTH_RANGE = range(3, 6)


def main():
    prices = load_prices()
    reports = []

    for smooth, window, roc, mom_smooth in product(
        SMOOTH_RANGE, WINDOW_RANGE, ROC_RANGE, MOM_SMOOTH_RANGE
    ):
        name = f"WMA {smooth}/{window}/{roc}/{mom_smooth}"
        report = score(
            name,
            lambda a, b, s=smooth, w=window, r=roc, m=mom_smooth:
                normalized(a, b, s, w, r, m),
            prices,
        )
        report["params"] = {
            "smooth_wma": smooth,
            "normalize_window": window,
            "momentum_roc": roc,
            "momentum_wma": mom_smooth,
        }
        reports.append(report)

    ranked = sorted(
        reports,
        key=lambda r: (
            -r["quadrant_matches"],
            r["approx_coordinate_mae"],
            r["exact_tooltip_mae"],
        ),
    )

    passing = [
        r for r in reports
        if r["quadrant_matches"] >= 25
        and r["approx_coordinate_mae"] <= 0.35
        and r["exact_tooltip_mae"] <= 0.30
    ]

    live = next(
        r for r in reports
        if (
            r["params"]["smooth_wma"],
            r["params"]["normalize_window"],
            r["params"]["momentum_roc"],
            r["params"]["momentum_wma"],
        ) == LIVE
    )
    live_rank = ranked.index(live) + 1

    def compact(r):
        return {
            "params": r["params"],
            "quadrant_matches": r["quadrant_matches"],
            "quadrant_total": r["quadrant_total"],
            "approx_coordinate_mae": r["approx_coordinate_mae"],
            "exact_tooltip_mae": r["exact_tooltip_mae"],
        }

    pass_ranges = {}
    if passing:
        for key in ("smooth_wma", "normalize_window", "momentum_roc", "momentum_wma"):
            vals = sorted({r["params"][key] for r in passing})
            pass_ranges[key] = vals

    out = {
        "reference": "EdgeRater Daily screenshot, 2026-10-09",
        "note": (
            "Single-date sensitivity analysis only. A large passing region means "
            "the parameterization is not uniquely identified by this reference."
        ),
        "tested_formulas": len(reports),
        "passing_formulas": len(passing),
        "live_params": {
            "smooth_wma": LIVE[0],
            "normalize_window": LIVE[1],
            "momentum_roc": LIVE[2],
            "momentum_wma": LIVE[3],
        },
        "live_rank": live_rank,
        "live_result": compact(live),
        "passing_parameter_values": pass_ranges,
        "top_20": [compact(r) for r in ranked[:20]],
    }

    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(
        f"RRG sensitivity: tested={len(reports)}, passing={len(passing)}, "
        f"live_rank={live_rank}/{len(reports)}"
    )
    print(
        "Live 10/16/5/4: "
        f"quadrants={live['quadrant_matches']}/{live['quadrant_total']}, "
        f"approx_MAE={live['approx_coordinate_mae']:.4f}, "
        f"exact_MAE={live['exact_tooltip_mae']:.4f}"
    )
    best = ranked[0]
    p = best["params"]
    print(
        "Best lexicographic candidate: "
        f"{p['smooth_wma']}/{p['normalize_window']}/{p['momentum_roc']}/{p['momentum_wma']} "
        f"quadrants={best['quadrant_matches']}/{best['quadrant_total']}, "
        f"approx_MAE={best['approx_coordinate_mae']:.4f}, "
        f"exact_MAE={best['exact_tooltip_mae']:.4f}"
    )


if __name__ == "__main__":
    main()
