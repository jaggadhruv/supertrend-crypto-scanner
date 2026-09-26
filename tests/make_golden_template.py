"""
Create a golden-file template for the TradingView check.

    python tests/make_golden_template.py BTC-USD 1D
    python tests/make_golden_template.py ETH-USD 4H

Writes tests/golden/<ticker>_<tf>.csv with Yahoo OHLCV (frozen, so the test is
repeatable), our Supertrend values for reference, and empty tv_st_line / tv_trend
columns on the last 15 bars. Fill those in from TradingView (see README.md).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data  # noqa: E402
import settings  # noqa: E402
from supertrend import supertrend  # noqa: E402

FILL_ROWS = 15


def main(ticker: str, tf: str) -> None:
    now = data.utcnow()
    if tf == "4H":
        bars = data.to_4h(data.fetch(ticker, settings.HOURLY_PERIOD, "1h"), now)
    else:
        daily = data.closed_daily(data.fetch(ticker, settings.DAILY_PERIOD, "1d"), now)
        bars = daily if tf == "1D" else data.to_weekly(daily, now)
    if bars.empty:
        sys.exit(f"No data for {ticker}")
    st = supertrend(bars, settings.ATR_PERIOD, settings.MULTIPLIER)
    out = bars.copy()
    out["our_st_line"] = st["st_line"]
    out["our_trend"] = st["trend"]
    out["tv_st_line"] = ""
    out["tv_trend"] = ""
    out.index.name = "time"
    path = Path(__file__).parent / "golden" / f"{ticker.replace('-', '_')}_{tf}.csv"
    out.to_csv(path)
    print(f"Wrote {path}. Fill tv_st_line and tv_trend (1 or -1) on the last {FILL_ROWS} rows you check.")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in ("1W", "1D", "4H"):
        sys.exit("usage: python tests/make_golden_template.py <YAHOO_TICKER> <1W|1D|4H>")
    main(sys.argv[1], sys.argv[2])
