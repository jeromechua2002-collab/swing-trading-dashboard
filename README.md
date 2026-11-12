# Trading Desk / Market Rotation Lab

A GitHub Pages research dashboard linked to a Notion swing-trading journal.

**Production:** https://jeromechua2002-collab.github.io/swing-trading-dashboard/

## What it does
- **Market regime and yields:** `index.html`, `rates.html`.
- **Sector and industry rotation:** `rrg.html`, `rotation-lab.html`, `sectors.html`, `industries.html`.
- **Equal-weight confirmation:** `sector-breadth.html` (sector/cap-weight proxies vs equal-weight).
- **Stock discovery:** `stock-leadership.html`, with relative vs sector/SPY and independent daily/4H closing-price context.
- **Execution checklist:** `trade-gate.html`, a *manual, self-attested* risk/fees/session-hours tool, not an order system.
- **Realized performance:** `equity.html`, `calendar.html` show a **percent-only** view of closed trades (equity index from 100, daily realized return %, win/loss counts), synced from Notion when credentials are available. No amounts, symbols, sizes or open positions are published.

Coverage as configured: **11 sectors, 16 industries and 116 curated stocks**. RRG timeframes: **1W, 1D, 4H, 1H**. The public indicator is a **calibrated approximation**, not mathematically identical to proprietary EdgeRater/JdK. Always check each chart's *market-bar as-of date*. A build timestamp is not the market close.

## Architecture

```text
yfinance / public price data ──> scripts/build_rrg_data.py
                                       ├─> data/rrg-core.json
                                       └─> data/stocks/{sector}.json
                              └─> scripts/validate_rrg.py
                              └─> scripts/audit_rrg_reference_daily.py

data/rrg-audit.json ──> scripts/build_sector_breadth.py
                            └─> data/sector-breadth.json

Notion trades + broker-confirmed fills ──> scripts/sync_journal_performance.py   (private, in memory)
                                               └─ scripts/journal_public.py (public contract)
                                                    └─> data/journal-performance.json  (public-journal-v2, percent-only)

release validator ──> data/release-manifest.json
                       │
scripts/build_site.py ──> _site/  (explicit allowlist + privacy audit)
                       │
GitHub Actions (pages.yml) ──> GitHub Pages ──> scripts/check_public_exposure.py (post-deploy)
```

**Publishing:** `.github/workflows/pages.yml` is the single production GitHub Pages publisher and uploads only `_site/`, which `scripts/build_site.py` assembles from an explicit allowlist. Source code, workflows, docs and fixtures are never published; a new page or data file must be added to the allowlist. Repository Settings → Pages → Source should be **GitHub Actions**, not branch publishing. `.github/workflows/pr-checks.yml` runs the same gates on pull requests without deploying. Separate branch workflows are audits only.

**Journal privacy:** the starting capital lives only in the `JOURNAL_START_CAPITAL_SGD` secret, and the Notion token in `NOTION_TOKEN`. Tests use synthetic journal values.

**Do not confuse generated data with source:** source files may exist without a current generated JSON snapshot. Market builds require network access; Notion sync needs a GitHub Secret. If an input is unavailable, mark the validation blocked.

## Developer setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_rrg_data.py
python scripts/validate_rrg.py
python scripts/audit_rrg_reference_daily.py
python scripts/build_sector_breadth.py
python scripts/audit_market_universe.py
python scripts/build_release_manifest.py
python scripts/build_site.py _site
python -m http.server 8765 --directory _site
```

Open `http://127.0.0.1:8765/` rather than `file://`; this serves exactly what Pages publishes. Run the relevant Node and Python tests before submitting changes; see `CLAUDE.md`. In environments with Playwright and Chromium installed, run `scripts/smoke_dashboard_browser.py` to verify actual browser navigation and embedded views.

## Contributing with Claude Code

1. Clone the repository, open its root as the Claude Code project folder and read `CLAUDE.md`.
2. Use the `market-rotation-qa` skill at `.claude/skills/market-rotation-qa/SKILL.md` for any data/chart/UI changes.
3. Start with a **read-only audit**. Then implement narrow improvements in a **feature branch and PR**, preserving all frozen reference checks.
4. No direct production publishing, fabricated trading signals, API secrets or unreviewed RRG retuning.

## Safety and provenance

This is research and journaling software; it does not execute trades or guarantee stop fills. The dashboard may lag a trading session and uses approximate RRG/derived close data rather than native TradingView OHLC pivots. Broker-reported net P/L and fill-arithmetic discrepancies are reconciled privately and never published. Never interpret a blue/green UI badge as a substitute for source timestamps, execution-venue checks or an independent broker statement.
