# Crypto Supertrend Tool

Sister repo to the US equity Supertrend screener. Same engine (TradingView-matched Supertrend,
ATR 10, multiplier 2.5), same free stack (yfinance, GitHub Actions, Gmail SMTP, state committed to
the repo), adapted for a 24/7 market.

## What it does

Once a day (00:30 UTC, after the Daily candle closes) it scans the coins in
`input/crypto_universe.csv` on three timeframes and writes one report in the same
"Supertrend Combined Scanner" layout as the US tool.

| Timeframe | Buy flips | Sell flips |
|---|---|---|
| Weekly (Mon 00:00 UTC weeks) | Card with SL / TP + quality score | Signal + held-bearish alert |
| Daily (00:00 UTC) | Card with SL / TP + quality score | Signal + held-bearish alert |
| 4H (00/04/08/12/16/20 UTC) | Card with SL / TP + quality score, every 4H bar of the last 24h | Not reported |

Only closed bars are used. Every flip since the previous run is written to `data/flip_log.json`,
so a missed day loses nothing. The first run back-fills 7 days.

**Report sections** (same order and styling as the US report): held-bearish alert banner,
Recent Buy Flips (last 7 days, grouped by day, ★ on the top 3), stats row, Buying Opportunities
(confluence = fresh buy on 2+ timeframes, then Weekly, Daily, 4H), data notes, and the full
watchlist with Weekly / Daily / 4H side by side, filters, search and sortable columns.

**Trade levels on every buy card**: Entry = flip-bar close, SL = Supertrend line on the flip bar,
TP1 = 2R, TP2 = 3R. Cards say so if price is already below the stop or past TP1.

**Quality score (0-100, graded A/B/C/D)**

| Component | Points | What it rewards |
|---|---|---|
| Trend alignment | 30 | 4H: Daily and Weekly up. 1D: Weekly up, above 200-day SMA. 1W: above a rising 50-week SMA |
| Market regime | 15 | BTC Daily Supertrend up, BTC above its 200-day SMA |
| Volume | 15 | Flip-bar volume vs 20-bar average (1.0x = 0, 2.0x+ = full) |
| Stop distance | 15 | Stop % relative to the timeframe cap (4H 8%, 1D 15%, 1W 30%) |
| Candle | 10 | Flip bar closing near its high |
| Momentum | 10 | RSI(14) between 55 and 70 |
| Cleanliness | 5 | Few flips in the prior 30 bars (no chop) |
| Liquidity penalty | -10 | 30-day average daily $ volume under $5M |

Hover a quality badge for the breakdown. Every flip is also appended to `data/signal_log.csv`
so the grades can be checked against outcomes later.

**Website (GitHub Pages)**: each run writes the site into `docs/`:

```
docs/
  index.html                          newest report + "Report archive" picker (the site's home page)
  .nojekyll                           tells Pages not to run Jekyll (only used by branch deploys)
  reports/
    crypto_supertrend_YYYY-MM-DD.html   dated reports, newest 30 kept, each links back to index.html
```

The workflow then publishes `docs/` with GitHub's official Pages actions, so the Pages source must be
**GitHub Actions** (see Setup). GitHub shows `.html` files inside the repo as source code, so always
read reports through the Pages link.

**Retention**: after each run only the newest 30 dated reports are kept (`REPORT_RETENTION` in
`settings.py`); older ones are deleted and the deletion is committed. `data/flip_log.json` keeps
30 days. Deleted files remain in git history, so `.git` grows slowly (a few hundred KB a month).
If an older version of this repo left a top-level `reports/` folder, the next run moves those
reports into `docs/reports/` and removes the old folder.

**Email**: one per run. Gmail strips `<style>` blocks, so the body is an inline-styled summary
(held alerts, ranked fresh buys with Entry / SL / TP) and the full report is attached.

**Portfolio (optional)**: add rows to `input/portfolio.csv` (`Symbol,Entry_Price,Quantity`) to fill
the Held and Position P/L columns, the My Portfolio filter and the red held-bearish banner.

## Setup

1. Create a new GitHub repo and push these files.
2. Add repository secrets (Settings > Secrets and variables > Actions):
   `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO` (same values as the US tool).
3. Settings > Actions > General > Workflow permissions: **Read and write**.
   Settings > Pages > Build and deployment > **Source: GitHub Actions**. Do not use
   "Deploy from a branch" (main / root or main / docs): commits made by the workflow's GITHUB_TOKEN
   never trigger a branch-based Pages build, so the site would stay stuck on the README or an old report.
   Pages needs a public repo on the free GitHub plan; a public repo also makes `input/portfolio.csv`
   and every report readable by anyone.
4. Locally, check the tickers and run the gate before trusting any signal:

```bash
pip install -r requirements.txt
python validate_tickers.py --write      # see which Yahoo tickers resolve; commit data/resolved_tickers.json
python tests/make_golden_template.py BTC-USD 1D
python tests/make_golden_template.py BTC-USD 4H
# fill tv_ columns from TradingView (tests/golden/README.md), then:
pytest tests -q
python run_scan.py --no-email           # writes docs/index.html + docs/reports/crypto_supertrend_<date>.html
```

5. Actions tab > crypto-supertrend-scan > Run workflow. When both jobs (scan, deploy) are green, the
   deploy job shows the site URL (`https://<user>.github.io/<repo>/`). After that it runs daily.

## Coin list

Edit `input/crypto_universe.csv` (columns `Rank,Symbol,Yahoo_Finance_Ticker`). When a ticker has no
fresh data, the scan tries `config/ticker_overrides.csv`, then Yahoo search, and reports any
replacement under List changes. Stablecoins are skipped by name and by a 90-day price-range check.

## Files

| File | Role |
|---|---|
| `settings.py` | All parameters |
| `supertrend.py` | Supertrend, ATR (RMA), RSI, TradingView-matched |
| `data.py` | Universe, ticker resolution, fetching, 4H/weekly resampling, closed-bar filter |
| `scoring.py` | SL / TP levels and the quality score |
| `run_scan.py` | Orchestration, flip detection, state |
| `report.py` | HTML report (US scanner layout) and email summary |
| `report_assets/` | Report CSS and JS, inlined into each report |
| `docs/` | The website GitHub Pages publishes (generated, committed by the workflow) |
| `emailer.py` | Gmail SMTP |
| `state.py` | State, flip log, signal log, portfolio, report retention |
| `validate_tickers.py` | Ticker health check |
| `tests/` | Supertrend + resampling tests, golden-file gate |
