"""
Check every coin in input/crypto_universe.csv against Yahoo before trusting the scan.

    python validate_tickers.py           # print a status table
    python validate_tickers.py --write   # also save data/resolved_tickers.json

Status values:
  OK         CSV ticker has fresh data
  REPLACED   CSV ticker is dead/stale, an alternate or Yahoo search hit was used
  STABLE     excluded as a stablecoin
  FAILED     nothing fresh found; fix the CSV or add a line to config/ticker_overrides.csv
"""
from __future__ import annotations

import argparse

import data
import settings
from run_scan import is_stable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    now = data.utcnow()
    overrides = data.load_overrides()
    resolved: dict = {}
    counts = {"OK": 0, "REPLACED": 0, "STABLE": 0, "FAILED": 0}

    print(f"{'Rank':>4}  {'Symbol':<7} {'CSV ticker':<14} {'Used ticker':<16} {'Last bar':<11} Status")
    for coin in data.load_universe():
        sym = coin["symbol"]
        if sym in settings.STABLECOINS:
            status, used, last = "STABLE", "-", "-"
        else:
            ticker, daily, note = data.resolve_and_fetch_daily(coin, overrides, resolved, now)
            if not ticker:
                status, used, last = "FAILED", "-", "-"
            else:
                used, last = ticker, daily.index[-1].strftime("%Y-%m-%d")
                if is_stable(daily):
                    status = "STABLE"
                else:
                    status = "OK" if ticker == coin["csv_ticker"] else "REPLACED"
                    resolved[sym] = {"ticker": ticker, "checked": now.strftime("%Y-%m-%d")}
        counts[status] += 1
        print(f"{coin['rank']:>4}  {sym:<7} {coin['csv_ticker']:<14} {used:<16} {last:<11} {status}")

    print("\n" + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    if args.write:
        data.save_resolved(resolved)
        print(f"Saved {settings.RESOLVED_TICKERS_FILE.relative_to(settings.ROOT)}")


if __name__ == "__main__":
    main()
