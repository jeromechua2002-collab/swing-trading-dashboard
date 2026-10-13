---
name: market-rotation-qa
description: Verify Market Rotation Lab, RRG parity, sector breadth, stock leadership, journal reconciliation, and GitHub Pages browser quality before making or publishing trading-dashboard changes.
---

# Market Rotation Lab QA skill

Use this skill whenever asked to review, improve, validate, or deploy the trading dashboard.

## 1 — Establish source truth first
Read `CLAUDE.md`, current `README.md`, `scripts/build_rrg_data.py`, `scripts/validate_rrg.py`, `scripts/audit_rrg_reference_daily.py`, `scripts/build_sector_breadth.py`, and the production workflow. Identify the commit, source data's last **completed trading session**, the build timestamp, benchmark, and RRG timeframe. Report unavailable inputs.

## 2 — Classify an observed problem
Classify issues separately as:
- **Display/UX:** blank dropdown, stale iframe, clutter, label collision, poor screen-reader/mobile usability.
- **Asset/feed:** 404, stale cache, missing JSON, inconsistent generated timestamp, wrong URL or publisher.
- **Market-data:** partial daily candles, split-adjustment anomalies, missing peers, FX/calendar gaps.
- **RRG model:** path shape, quadrant timing, smoothing, normalization, benchmark or tail length.
- **Journal/broker:** unclosed or duplicated lots, realized P/L, fees, order session protections.

Do not “fix” model differences with CSS or change indicator parameters to hide data problems.

## 3 — Reproduce on actual surfaces
Load the failing public GitHub Pages URL and locally served source. For Notion, reproduce in an iframe as well as direct link. Capture console errors, network failures, source dates and screenshots. Check desktop **and mobile** layout. Verify all 11 sectors, 16 industries and every configured stock, not just screenshots of XLK or XLE.

## 4 — Date-matched RRG reference protocol
For each EdgeRater screenshot/reference, record ticker, ETF vs stock scope, benchmark, market-close date, timeframe, quadrant, last head, tail direction and user-provided screenshot provenance.
- Never call a one-session difference an indicator delay.
- Confirm the model includes that exact market date; otherwise mark **NOT COMPARABLE**.
- Compare quadrant transitions and previous-to-current direction across multiple dates.
- Separate numeric coordinate differences, crossing-date differences, trajectory-shape differences, and changes in the constituent universe.
- Do not assert exact JdK or EdgeRater formula equivalence. Keep the original frozen reference baseline; treat tuning as a separate proposed experiment requiring approval.

## 5 — Trading decision pipeline
Produce stock → relevant industry → parent sector → market benchmark confirmation, with dated daily and 4H readings plus **absolute price trend** and broad equal-weight participation.
- A Leading stock can be cooling; an Improving stock can still fall in absolute price.
- Show specific conflicts rather than a blanket “confirmed leader.”
- Screening is **not execution**. For trade planning, separately check fresh 4H/1H/15m structure, real first supply/support, event/earnings, underlying and actual leveraged product, after-fee first-target R:R, broker stop-session eligibility and size. Never invent or place orders.

## 6 — Regression and release gates
Run the focused unit tests and all-page HTML/JS integrity checks from `CLAUDE.md`. Build market data only if permitted and providers work; validate all 116 curated names plus 11 equal-weight pairs and 1W/1D/4H/1H RRG views. Use `scripts/smoke_dashboard_browser.py` to confirm working controls and iframe loading. Reconcile the journal with Notion/broker facts and note any unresolved mismatch. After a release, verify the actual public file hashes, counts and dates.

For each audit issue record: **severity, reproduction instructions, affected files, expected vs actual, data as-of, supporting evidence, fix/test, unresolved risks**.

## 7 — Work safely with GitHub/Claude
Make a feature branch, commit minimal changes, run tests and open a PR for human review. Never directly overwrite validated model baselines or production history. Don't log secrets. If the browser, connector, Notion sync or market data fails, surface the dependency and mark checks blocked, not passed. One production publisher only.
