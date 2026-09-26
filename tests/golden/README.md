# Golden files: the Phase 1 gate

Same rule as the US tool: if Supertrend doesn't match TradingView, no signal is trusted.

## Make a golden file

```bash
python tests/make_golden_template.py BTC-USD 1D
python tests/make_golden_template.py BTC-USD 4H
python tests/make_golden_template.py ETH-USD 1D
```

## Fill it from TradingView (free tier)

1. Open the chart **`CRYPTO:BTCUSD`** (TradingView's own multi-venue index). This is the closest
   match to Yahoo, which is also an aggregate. A single exchange feed such as `BINANCE:BTCUSDT`
   will differ slightly, so don't use it here.
2. Chart timezone: **UTC** (bottom-right of the chart). Timeframe: 1D, 4h or 1W to match the file.
3. Add the built-in **Supertrend** indicator, set ATR Period 10, Factor 2.5.
4. Hover each of the last few bars, read the Supertrend value from the Data Window, and type it into
   `tv_st_line`. Put `1` in `tv_trend` if the line is green (below price), `-1` if red.
5. Run `pytest tests -q`.

Tolerance is 0.5% on the line value, and the trend direction must match exactly. BTC and ETH
should sit well inside that. If a small-cap coin fails by a fraction of a percent, that's the data
source, not the formula. If BTC fails, stop and investigate before using any signal.
