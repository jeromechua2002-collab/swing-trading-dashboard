# Trading Desk / Market Rotation Lab

A GitHub Pages research dashboard linked to a Notion swing-trading journal.

**Production:** https://jeromechua2002-collab.github.io/swing-trading-dashboard/

## What it does
- **Market regime and yields:** `index.html`, `rates.html`.
- **Sector and industry rotation:** `rrg.html`, `rotation-lab.html`, `sectors.html`, `industries.html`.
- **Equal-weight confirmation:** `sector-breadth.html` (sector/cap-weight proxies vs equal-weight).
- **Stock discovery:** `stock-leadership.html`, with relative vs sector/SPY and independent daily/4H closing-price context.
- **Execution checklist:** `trade-gate.html`, a *manual, self-attested* risk/fees/session-hours tool, not an order system.
- **Realized performance:** `equity.html`, `calendar.html`, synced from Notion when credentials are available.

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

Notion trades + broker-confirmed fills ──> scripts/sync_journal_performance.py
                                               └─> data/journal-performance.json

release validator ──> data/release-manifest.json
                       │
GitHub Actions ──> GitHub Pages site ──> HTML/JS charts and journal
```

**Publishing:** `.github/workflows/pages.yml` is the single production GitHub Pages publisher. Repository Settings → Pages → Source should be **GitHub Actions**, not branch publishing. Separate branch workflows are audits only.

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
python -m http.server 8765
```

Open `http://127.0.0.1:8765/` rather than `file://`. Run the relevant Node and Python tests before submitting changes; see `CLAUDE.md`. In environments with Playwright and Chromium installed, run `scripts/smoke_dashboard_browser.py` to verify actual browser navigation and embedded views.

## Contributing with Claude Code

1. Clone the repository, open its root as the Claude Code project folder and read `CLAUDE.md`.
2. Use the `market-rotation-qa` skill at `.claude/skills/market-rotation-qa/SKILL.md` for any data/chart/UI changes.
3. Start with a **read-only audit**. Then implement narrow improvements in a **feature branch and PR**, preserving all frozen reference checks.
4. No direct production publishing, fabricated trading signals, API secrets or unreviewed RRG retuning.

## Safety and provenance

This is research and journaling software; it does not execute trades or guarantee stop fills. The dashboard may lag a trading session and uses approximate RRG/derived close data rather than native TradingView OHLC pivots. Broker-reported net P/L and fill-arithmetic discrepancies are recorded separately. Never interpret a blue/green UI badge as a substitute for source timestamps, execution-venue checks or an independent broker statement.
