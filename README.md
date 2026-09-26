# Crypto Supertrend Tool

Sister repo to the US equity Supertrend screener. Same engine (TradingView-matched Supertrend,
ATR 10, multiplier 2.5), same free stack (yfinance, GitHub Actions, Gmail SMTP, state committed to
the repo), adapted for a 24/7 market.

## What it does

Every 4 hours it scans the coins in `input/crypto_universe.csv` on three timeframes:

| Timeframe | Buy flips | Sell flips |
|---|---|---|
| Weekly (Mon 00:00 UTC weeks) | Card with SL / TP + quality score | Exit alert |
| Daily (00:00 UTC) | Card with SL / TP + quality score | Exit alert |
| 4-hour (00/04/08/12/16/20 UTC) | Card with SL / TP + quality score | Not reported |

Only closed bars are used. A flip is reported once, on the first run after its bar closes.

**Trade levels on each buy card**

- Entry: close of the flip bar (the card also shows the current price and move since)
- Stop loss: the Supertrend line on the flip bar
- TP1 = 2R, TP2 = 3R, where R = entry minus stop
- If price is already below the stop or past a target when the email goes out, the card says so

**Quality score (0-100, graded A/B/C/D)**

| Component | Points | What it rewards |
|---|---|---|
| Trend alignment | 30 | 4H: Daily and Weekly Supertrend up. 1D: Weekly up, above 200-day SMA. 1W: above a rising 50-week SMA |
| Market regime | 15 | BTC Daily Supertrend up, BTC above its 200-day SMA |
| Volume | 15 | Flip-bar volume vs 20-bar average (1.0x = 0, 2.0x+ = full) |
| Stop distance | 15 | Stop % relative to the timeframe cap (4H 8%, 1D 15%, 1W 30%) |
| Candle | 10 | Flip bar closing near its high |
| Momentum | 10 | RSI(14) between 55 and 70 |
| Cleanliness | 5 | Few flips in the prior 30 bars (no chop) |
| Liquidity penalty | -10 | 30-day average daily $ volume under $5M |

Every card shows the breakdown. The weights are a starting hypothesis; every flip is appended to
`data/signal_log.csv` so the grades can be checked against outcomes after a few months.

**Email sections**: new buy flips ranked by score, exit alerts, list changes, all coins (daily
digest only), run summary. An email goes out when there is at least one new flip, plus one digest
per UTC day (the 00:07 run). `reports/latest.html` always holds the full report and
`reports/daily/` keeps one per day.

## Setup

1. Create a new GitHub repo and push these files.
2. Add repository secrets (Settings > Secrets and variables > Actions):
   `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO` (same values as the US tool).
3. Settings > Actions > General > Workflow permissions: **Read and write**.
4. Locally, check the tickers and run the gate before trusting any signal:

```bash
pip install -r requirements.txt
python validate_tickers.py --write      # see which Yahoo tickers resolve; commit data/resolved_tickers.json
python tests/make_golden_template.py BTC-USD 1D
python tests/make_golden_template.py BTC-USD 4H
# fill tv_ columns from TradingView (tests/golden/README.md), then:
pytest tests -q
python run_scan.py --no-email           # writes reports/latest.html
```

5. Actions tab > crypto-supertrend-scan > Run workflow (tick "force digest" for a full first email).

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
| `report.py` | HTML email / report |
| `emailer.py` | Gmail SMTP |
| `state.py` | `data/state.json` and `data/signal_log.csv` |
| `validate_tickers.py` | Ticker health check |
| `tests/` | Supertrend + resampling tests, golden-file gate |
