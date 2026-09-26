"""
Data layer: universe CSV, Yahoo ticker resolution, price fetching, resampling.

Candle conventions (all UTC, matching how crypto charts are drawn on TradingView):
  4H     : resampled from 1h bars, bins start at 00/04/08/12/16/20 UTC
  Daily  : Yahoo daily bars (00:00 UTC open)
  Weekly : resampled from daily bars, weeks run Monday 00:00 UTC to Sunday close

Only CLOSED bars are ever used for signals. The still-forming bar of each
timeframe is dropped, otherwise a flip could appear and vanish intra-bar.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

import settings

log = logging.getLogger(__name__)

OHLCV = ["Open", "High", "Low", "Close", "Volume"]
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


# --------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------
def _pick(row: dict, *names: str) -> str:
    lowered = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        if n in lowered and lowered[n] is not None:
            return str(lowered[n]).strip()
    return ""


def load_universe(path=settings.UNIVERSE_CSV) -> list[dict]:
    """Reads the coin list. Accepts flexible column names; de-duplicates by symbol."""
    coins, seen = [], set()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            symbol = _pick(row, "symbol", "coin", "asset").upper()
            ticker = _pick(row, "yahoo_finance_ticker", "yahoo_ticker", "ticker", "yahoo")
            rank = _pick(row, "rank", "#")
            if not symbol and ticker:
                symbol = ticker.split("-")[0].upper()
            if not symbol or symbol in seen:
                continue
            if not ticker:
                ticker = f"{symbol}-USD"
            seen.add(symbol)
            coins.append(
                {
                    "symbol": symbol,
                    "csv_ticker": ticker.upper(),
                    "rank": int(rank) if rank.isdigit() else len(coins) + 1,
                }
            )
    return coins


def load_overrides(path=settings.TICKER_OVERRIDES_CSV) -> dict[str, list[str]]:
    """symbol -> list of alternate Yahoo tickers to try, in order."""
    out: dict[str, list[str]] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(line for line in fh if not line.startswith("#")):
            sym = (row.get("symbol") or "").strip().upper()
            alt = (row.get("alternate_ticker") or "").strip().upper()
            if sym and alt:
                out.setdefault(sym, []).append(alt)
    return out


def load_resolved(path=settings.RESOLVED_TICKERS_FILE) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_resolved(resolved: dict, path=settings.RESOLVED_TICKERS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolved, indent=2, sort_keys=True))


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV)
    df = df[[c for c in OHLCV if c in df.columns]].copy()
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)
    return df


def fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        raw = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    except Exception as exc:  # yfinance raises a variety of things on bad tickers
        log.debug("fetch %s %s failed: %s", ticker, interval, exc)
        raw = None
    finally:
        time.sleep(settings.FETCH_DELAY_SEC)
    return _clean(raw)


def is_fresh(daily: pd.DataFrame, now: datetime) -> bool:
    if daily.empty:
        return False
    return (now - daily.index[-1].to_pydatetime()) <= timedelta(days=settings.STALE_DAYS)


def _search_candidates(symbol: str) -> list[str]:
    """Ask Yahoo's search endpoint for USD crypto pairs matching the symbol."""
    try:
        quotes = yf.Search(symbol, max_results=10, news_count=0, lists_count=0,
                           raise_errors=False).quotes
    except Exception:
        return []
    finally:
        time.sleep(settings.FETCH_DELAY_SEC)
    out = []
    for q in quotes or []:
        sym = str(q.get("symbol", "")).upper()
        if q.get("quoteType") == "CRYPTOCURRENCY" and sym.endswith("-USD"):
            base = sym[:-4]
            # exact symbol, or symbol + CoinMarketCap id suffix (e.g. TON11419-USD)
            if base == symbol or (base.startswith(symbol) and base[len(symbol):].isdigit()):
                out.append(sym)
    return out


def resolve_and_fetch_daily(coin: dict, overrides: dict, resolved: dict, now: datetime):
    """
    Returns (ticker, daily_df, note). Tries, in order:
      1. previously resolved ticker (cached in data/resolved_tickers.json)
      2. ticker from the CSV
      3. alternates in config/ticker_overrides.csv
      4. Yahoo search (symbol-USD or symbol<id>-USD)
    First candidate with fresh daily data wins. Among search hits, the one
    with the highest recent dollar volume wins (avoids picking a dead clone).
    """
    symbol = coin["symbol"]
    tried: list[str] = []

    def attempt(t: str):
        if t in tried:
            return None
        tried.append(t)
        df = fetch(t, settings.DAILY_PERIOD, "1d")
        return df if is_fresh(df, now) else None

    cached = resolved.get(symbol, {}).get("ticker")
    ordered = ([cached] if cached else []) + [coin["csv_ticker"]] + overrides.get(symbol, [])
    for t in ordered:
        df = attempt(t)
        if df is not None:
            # only report a replacement the first time it happens, not on every run
            note = "" if t in (coin["csv_ticker"], cached) else f"CSV ticker {coin['csv_ticker']} replaced by {t}"
            return t, df, note

    best = None
    for t in _search_candidates(symbol):
        df = attempt(t)
        if df is None:
            continue
        dollar_vol = float((df["Close"] * df["Volume"]).tail(30).mean())
        if best is None or dollar_vol > best[2]:
            best = (t, df, dollar_vol)
    if best:
        if best[0] == cached:
            return best[0], best[1], ""
        return best[0], best[1], f"CSV ticker {coin['csv_ticker']} replaced by {best[0]} (Yahoo search)"

    return None, pd.DataFrame(columns=OHLCV), f"No fresh Yahoo data (tried {', '.join(tried)})"


# --------------------------------------------------------------------------
# Resampling and closed-bar filtering
# --------------------------------------------------------------------------
def closed_daily(daily: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if daily.empty:
        return daily
    daily = daily.copy()
    daily.index = daily.index.normalize()
    daily = daily[~daily.index.duplicated(keep="last")]
    return daily[daily.index + pd.Timedelta(days=1) <= now]


def to_weekly(daily_closed: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Monday-open weeks, labelled by the Monday. Drops the forming week."""
    if daily_closed.empty:
        return daily_closed
    wk = daily_closed.resample("W-MON", label="left", closed="left").agg(AGG).dropna(subset=["Close"])
    return wk[wk.index + pd.Timedelta(days=7) <= now]


def to_4h(hourly: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """4H bins anchored to 00:00 UTC. Drops the forming bin."""
    if hourly.empty:
        return hourly
    h4 = hourly.resample("4h", origin="epoch", label="left", closed="left").agg(AGG).dropna(subset=["Close"])
    return h4[h4.index + pd.Timedelta(hours=4) <= now]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
