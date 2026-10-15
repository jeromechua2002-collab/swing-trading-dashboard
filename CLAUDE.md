# Trading Desk — Claude Code Project Instructions

## Mission and working agreement
Maintain and improve the **existing** GitHub Pages swing-trading research dashboard. Help the operator move from market regime → sector breadth → industry rotation → stock relative strength → price confirmation → manually reviewed execution → journal analysis.

This is a **decision-support** project, not a brokerage execution bot, investment adviser, or proprietary EdgeRater clone. Do not promise profitable signals or fabricate technical levels, results, confidence, catalysts, fees, or orders.

**First task in a new session:** inspect the live repository and existing tests; provide a referenced architecture audit and prioritized implementation plan. Ask for approval before substantive formula or data-provider changes. Implement ordinary bug fixes on a dedicated branch and open a PR; never assume an earlier conversation reflects the current branch.

## Existing structure (inspect current code before relying on this map)
- `index.html`, `desk-home.css`, `dashboard.css`, `desk-health.js`: market/journal cockpit, source-aware health.
- `rrg.html`, `rotation-lab.html`: sector, industry, stock RRG and discovery views.
- `stock-leadership.html`, `stock-leadership.js`: curated stock vs SPY/parent-sector leadership, daily/4H and close-only price context.
- `sector-breadth.html`, `breadth-*.js`: cap-weight versus equal-weight sector comparison.
- `equity.html`, `calendar.html`: realized journal views. They render the **percent-only** public journal (equity index starting at 100, daily realized return %, win/loss counts), never money amounts.
- `trade-gate.html`, `trade-gate.js`: **manual/self-attested** entry/stop/first-target, broker-hours, fees and R:R checks.
- `scripts/build_rrg_data.py`: downloads price inputs and emits `data/rrg-core.json` plus `data/stocks/{sector}.json`.
- `scripts/validate_rrg.py`, `scripts/rrg_sensitivity.py`: frozen reference calibration and sensitivity.
- `scripts/audit_rrg_reference_daily.py`: dated comparison to supplied EdgeRater **qualitative screenshot quadrants**. A dated quadrant match is not trajectory/formula equivalence.
- `scripts/build_sector_breadth.py`, `scripts/audit_market_universe.py`: sector breadth and stock/timeframe integrity.
- `scripts/sync_journal_performance.py`: reads private Notion trades in memory, reconciles them, and writes only the public payload `data/journal-performance.json` (`schema: public-journal-v2`). Starting capital comes from the `JOURNAL_START_CAPITAL_SGD` secret; `--check` is a read-only dry run.
- `scripts/journal_public.py`: the public journal contract (`build_public`, `validate_public`, `find_private_markers`). `scripts/test_publication_privacy.py` and `scripts/test_journal_snapshot.py` enforce it.
- `scripts/build_release_manifest.py`, `scripts/check_live_dashboard.py`: session/hash coherency and actual Pages artifact verification.
- `scripts/build_site.py`: assembles the Pages artifact `_site/` from an explicit allowlist of pages, assets and data files, then audits it for unexpected files, secrets, Notion links/IDs and private journal fields. A new page or data file is not published until it is added to the allowlist.
- `scripts/check_public_exposure.py`: runs after deploy against the live site; fails if the journal breaks the public contract or a formerly exposed path is still served.
- `scripts/test_completed_bars.py`: completed-bar policy on every RRG timeframe (NYSE calendar, holidays, early closes, DST).
- `scripts/test_all_dashboards.cjs`, `scripts/smoke_dashboard_browser.py`: HTML/JS integrity and real Chromium/iframe smoke testing.
- `.github/workflows/pages.yml`: **sole production publisher**; uploads `_site/` only. Pages source must be **GitHub Actions**, never simultaneous branch-publishing. `.github/workflows/pr-checks.yml` runs the same gates on pull requests without deploying. Other workflows may be audits only.

## Non-negotiable data and trading invariants
1. **Every conclusion carries an as-of date, timeframe and benchmark.** A workflow build timestamp is not a market-session timestamp. Do not compare Oct 13 EdgeRater heads against Oct 12 RRG heads as if contemporaneous.
2. **Do not silently retune the RRG formula.** Current model is a calibrated public approximation, NOT verified proprietary JdK/EdgeRater. Distinguish absolute price trend, SPY-relative trend, within-sector trend, and model/horizon disagreements. For parameter changes, prepare a reproducible, multi-date, multi-ticker comparison, frozen holdout, sensitivity analysis, tradeoffs and explicit human approval.
3. **Universe integrity:** currently 11 SPDR sectors, 16 industry ETFs, 116 *curated* stock tickers across four RRG timeframes (1W/1D/4H/1H). Verify these numbers in code; don't claim 116 is the full S&P 500. Test every member, not one sample ticker.
4. **No unfinished daily candle** may be represented as a completed daily signal. Follow the existing New York session cutoffs and DST regression tests. Synthetic 4H close bars can differ from TradingView 4H OHLC bars.
5. **Equal weight and cap weight** may diverge without a bug; disclose numerator, comparison benchmark, basket membership, timeframe and return/normalization basis. An industry proxy such as IBB or KRE does not represent its entire parent sector.
6. **Journal is real money:** Notion and broker confirmations are the source of truth; realized and unrealized P/L must remain distinct. Avoid deducting broker-reported net fees twice. Preserve any known broker-versus-fill reconciliation discrepancy until independently resolved; never rewrite transaction fills to hide it. FX provenance, fills and fees stay in the private Notion record; reconciliation happens in memory and only percentages are published.
7. **Trade execution is NEVER authorized** by RRG or the software. The worksheet's conditional eligibility relies on manual attestations and is not broker-verified. Include fresh purchased-vehicle quote, event risk, cash/loss caps, first *actual* obstacle, net-after-fees R:R and session-specific stop eligibility. GTC/stop submission is not guaranteed extended-hours protection or fill.
8. **Secrets/privacy:** no tokens, account identifiers, private Notion dumps, raw broker exports, or financial personal data in public GitHub commits, CI logs or deployable pages. Use GitHub Secrets / least privilege; do not log credentials. The public journal is **percent-only** and covers closed trades: no symbols, sizes, prices, fills, fees, FX, SGD/USD amounts, starting capital, open positions, notes or Notion links/IDs. Don't expand it without user approval. Test fixtures, docs and commit messages use synthetic values only; never copy real journal numbers or trade tickers into them.
9. **No uncontrolled publishing:** PRs and audits on branches; keep one Pages production workflow, publishing only the audited `_site/` allowlist. Do not push straight to main without explicit permission. Preserve the last working public site when tests fail.

## Required verification, proportionate to changes
Before requesting review, record which checks were executed and their exact outcomes. For code changes affecting data, UI, sync, or deployment, at minimum:
```bash
python -m unittest discover -s scripts -p 'test_sector_breadth.py' -v
python -m unittest discover -s scripts -p 'test_reference_trajectory.py' -v
python -m unittest discover -s scripts -p 'test_price_context.py' -v
python -m unittest discover -s scripts -p 'test_release_manifest.py' -v
python -m unittest discover -s scripts -p 'test_publication_privacy.py' -v
python -m unittest discover -s scripts -p 'test_completed_bars.py' -v
node scripts/test_all_dashboards.cjs
node scripts/test_desk_home.cjs
node scripts/test_desk_health.cjs
node scripts/test_execution_gate.cjs
python scripts/test_journal_snapshot.py
```
Generated-data-dependent validations (run after the market-data build; requires network and correct secrets for live sync):
```bash
python scripts/build_rrg_data.py
python scripts/validate_rrg.py
python scripts/audit_rrg_reference_daily.py
python scripts/build_sector_breadth.py
python scripts/audit_market_universe.py
node scripts/test_stock_leadership.cjs
node scripts/test_breadth_confirmation.cjs
node scripts/test_breadth_ticker_mapping.cjs
node scripts/test_breadth_feed.cjs data/sector-breadth.json
python scripts/build_release_manifest.py
python scripts/build_site.py _site
```
For UI changes, run `scripts/smoke_dashboard_browser.py` in Chromium against the locally served `_site/` directory (`python -m http.server 8765 --directory _site`) and test at desktop/mobile sizes plus iframe loading. Do not claim an HTML file exists therefore it renders. For release changes, verify **published** Pages JSON/HTML against the generated release manifest after deployment, and run `python scripts/check_public_exposure.py` against the live URL.

If a command cannot be run (e.g. provider unavailable), say what is **not verified**; do not substitute a fake passing output.

## Coding and UX principles
- Prefer narrow, reviewable changes over sweeping rewrites; reuse existing data models and UI components.
- Mobile-first clarity: show `data as of`, compare two benchmarks explicitly, highlight true conflicts and actionable research gates; avoid proliferating charts.
- Use accessible labels, keyboard interaction, helpful errors and responsive charts; no silent empty dropdowns.
- All indicators are historical data summaries. Distinguish opportunity discovery, developing setup, and confirmed executable trade.
- Document precise source links/paths and screenshots for visual regressions; add regression tests for bugs found in production.
- Avoid unnecessary services, paid APIs, backend/database migrations, and switching the publisher simply for aesthetics.

## Suggested first audit deliverable
Produce a concise architecture/data-flow map, ranked top five problems by **impact × reproducibility**, a UX mock/workflow for stock→industry→sector confirmation, a measurable RRG date/trajectory calibration plan, a coverage matrix of currently tested views, and an implementation plan as small PRs. **First audit is read-only.**

See `.claude/skills/market-rotation-qa/SKILL.md` for the reusable QA protocol.
