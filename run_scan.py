"""
Crypto Supertrend daily scan (GitHub Actions, 00:30 UTC).

    python run_scan.py              # normal run: report + email (if secrets are set)
    python run_scan.py --no-email   # report only
    python run_scan.py --dry-run    # nothing written, nothing sent

Per coin:
  resolve Yahoo ticker -> fetch 1d + 1h -> closed Weekly / Daily / 4H bars -> Supertrend
  Fresh signals:
    Weekly / Daily : a flip on the latest closed bar (buy or sell)
    4H             : BUY flips on any 4H bar closed in the last 24 hours (4H sells ignored)
  Every flip on a bar closed since the previous run goes into data/flip_log.json, so a
  skipped day loses nothing. On the very first run the log is back-filled with 7 days.
"""
from __future__ import annotations

import argparse
import logging
import sys

import numpy as np
import pandas as pd

import data
import emailer
import report
import scoring
import settings
import state as state_mod
from supertrend import rsi, supertrend

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("scan")

MIN_BARS = settings.ATR_PERIOD + 5
BAR_LEN = {"1W": pd.Timedelta(days=7), "1D": pd.Timedelta(days=1), "4H": pd.Timedelta(hours=4)}


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame | None:
    if bars is None or len(bars) < MIN_BARS:
        return None
    out = supertrend(bars, settings.ATR_PERIOD, settings.MULTIPLIER)
    out["rsi"] = rsi(out["Close"])
    return out


def sma_flag(close: pd.Series, n: int):
    if len(close) < n:
        return None
    return bool(close.iloc[-1] > close.rolling(n).mean().iloc[-1])


def is_stable(daily: pd.DataFrame) -> bool:
    tail = daily["Close"].tail(90)
    if len(tail) < 30:
        return False
    return (tail.max() - tail.min()) / tail.mean() * 100 < settings.STABLE_RANGE_PCT


def build_frames(daily_raw: pd.DataFrame, hourly_raw: pd.DataFrame, now) -> dict:
    d = data.closed_daily(daily_raw, now)
    return {
        "1D": add_indicators(d),
        "1W": add_indicators(data.to_weekly(d, now)),
        "4H": add_indicators(data.to_4h(hourly_raw, now)),
        "_daily_closed": d,
    }


def coin_context(frames: dict, btc_ctx: dict) -> dict:
    d, w = frames["_daily_closed"], frames["1W"]
    ctx = dict(btc_ctx)
    ctx["trend_1D"] = int(frames["1D"]["trend"].iloc[-1]) if frames["1D"] is not None else None
    ctx["trend_1W"] = int(w["trend"].iloc[-1]) if w is not None else None
    ctx["above_sma200d"] = sma_flag(d["Close"], 200)
    if w is not None and len(w) >= 54:
        sma50 = w["Close"].rolling(50).mean()
        ctx["above_sma50w"] = bool(w["Close"].iloc[-1] > sma50.iloc[-1])
        ctx["sma50w_rising"] = bool(sma50.iloc[-1] > sma50.iloc[-5])
    else:
        ctx["above_sma50w"] = ctx["sma50w_rising"] = None
    tail = d.tail(30)
    ctx["dollar_volume_30d"] = float((tail["Close"] * tail["Volume"]).mean()) if len(tail) else None
    return ctx


def flip_entry(sym, ticker, tf, bars, pos, ctx, run_utc) -> dict:
    """One flip on one bar, as stored in flip_log.json and shown on cards."""
    ts = bars.index[pos]
    row = bars.iloc[pos]
    close_time = ts + BAR_LEN[tf]
    e = {
        "symbol": sym, "ticker": ticker, "tf": tf,
        "direction": "buy" if bool(row["buy"]) else "sell",
        "bar_time": ts.isoformat(),
        "close_date": close_time.strftime("%Y-%m-%d"),
        "close": float(row["Close"]),
        "st": float(row["st_line"]),
        "logged_utc": run_utc,
    }
    if e["direction"] == "buy":
        sc = scoring.score_buy_flip(tf, bars, pos, ctx)
        e.update({k: sc[k] for k in ("stop", "tp1", "tp2", "risk_pct", "tp1_pct", "tp2_pct", "score", "grade")})
        e["parts"] = sc["parts"]
        e["penalty"] = sc["penalty"]
        e["notes"] = sc["notes"]
        e["vol_ratio"] = None if np.isnan(sc["vol_ratio"]) else round(sc["vol_ratio"], 2)
        e["rsi"] = None if np.isnan(sc["rsi"]) else round(sc["rsi"], 1)
    return e


def tf_snapshot(bars: pd.DataFrame, tf: str, prev: dict, now) -> dict:
    """Current direction / signal / in-trend for the watchlist table."""
    trend = int(bars["trend"].iloc[-1])
    last = bars.index[-1]
    if tf == "4H":
        window = bars[bars.index + BAR_LEN[tf] >= now - pd.Timedelta(hours=settings.FRESH_4H_HOURS)]
        signal = "buy" if bool(window["buy"].any()) else "none"
    else:
        signal = "buy" if bool(bars["buy"].iloc[-1]) else "sell" if bool(bars["sell"].iloc[-1]) else "none"

    # consecutive bars in the current direction, including the latest one
    changes = np.flatnonzero(bars["trend"].to_numpy() != trend)
    start_pos = changes[-1] + 1 if len(changes) else 0
    in_trend = len(bars) - start_pos
    since = bars.index[start_pos]
    prev_trend = prev.get("trend")
    changed = signal == "none" and prev_trend is not None and prev_trend != trend
    return {
        "trend": trend, "signal": signal, "changed": changed, "prev_trend": prev_trend,
        "in_trend": int(in_trend), "since": since.strftime("%Y-%m-%d %H:%M" if tf == "4H" else "%Y-%m-%d"),
        "st": float(bars["st_line"].iloc[-1]), "bar": last.strftime("%Y-%m-%d %H:%M" if tf == "4H" else "%Y-%m-%d"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    now = data.utcnow()
    now_ts = pd.Timestamp(now)
    run_utc = now.strftime("%Y-%m-%d %H:%M UTC")
    today = now.strftime("%Y-%m-%d")

    universe = data.load_universe()
    overrides = data.load_overrides()
    resolved = data.load_resolved()
    portfolio = state_mod.load_portfolio()
    st = state_mod.load_state()
    flip_log = state_mod.load_flip_log()
    first_run = not st["coins"]

    excluded, failures, replacements = [], [], []
    new_flips, fresh, rows = [], [], []

    # ---- BTC regime ------------------------------------------------------
    btc_coin = next((c for c in universe if c["symbol"] == "BTC"),
                    {"symbol": "BTC", "csv_ticker": "BTC-USD", "rank": 0})
    btc_ticker, btc_daily, _ = data.resolve_and_fetch_daily(btc_coin, overrides, resolved, now)
    btc_ctx = {"btc_trend_1D": None, "btc_above_sma200d": None}
    if btc_ticker:
        bd = add_indicators(data.closed_daily(btc_daily, now))
        if bd is not None:
            btc_ctx["btc_trend_1D"] = int(bd["trend"].iloc[-1])
            btc_ctx["btc_above_sma200d"] = sma_flag(bd["Close"], 200)
    cache = {"BTC": (btc_ticker, btc_daily)} if btc_ticker else {}

    for coin in universe:
        sym = coin["symbol"]
        if sym in settings.STABLECOINS:
            excluded.append((sym, "Stablecoin (explicit list)"))
            continue
        if sym in cache:
            ticker, daily_raw, note = *cache[sym], ""
        else:
            ticker, daily_raw, note = data.resolve_and_fetch_daily(coin, overrides, resolved, now)
        if not ticker:
            failures.append((sym, coin["csv_ticker"], note))
            log.warning("%s: %s", sym, note)
            continue
        if note:
            replacements.append((sym, note))
        resolved[sym] = {"ticker": ticker, "checked": today}
        if is_stable(daily_raw):
            excluded.append((sym, f"Stablecoin (90-day range under {settings.STABLE_RANGE_PCT:.0f}%)"))
            continue

        hourly_raw = data.fetch(ticker, settings.HOURLY_PERIOD, "1h")
        frames = build_frames(daily_raw, hourly_raw, now)
        if frames["1D"] is None:
            failures.append((sym, ticker, "Not enough daily history"))
            continue

        ctx = coin_context(frames, btc_ctx)
        coin_state = st["coins"].get(sym, {})
        new_state = {"ticker": ticker}
        row = {"symbol": sym, "rank": coin["rank"], "ticker": ticker,
               "close": float(frames["1D"]["Close"].iloc[-1]),
               "last_price": float(hourly_raw["Close"].iloc[-1]) if not hourly_raw.empty else None,
               "tf": {}, "held": sym in portfolio}
        if row["held"]:
            entry = portfolio[sym]["entry"]
            row["entry"] = entry
            row["pnl_pct"] = (row["close"] / entry - 1) * 100 if entry else None

        for tf in settings.TIMEFRAME_ORDER:
            bars = frames[tf]
            if bars is None:
                row["tf"][tf] = None
                continue
            prev = coin_state.get(tf, {})
            buy_only = settings.TIMEFRAMES[tf]["buy_only"]

            # 1) flips since last run -> flip log
            if prev.get("last_bar"):
                new_mask = bars.index > pd.Timestamp(prev["last_bar"])
            else:  # first sight: back-fill the recent window
                new_mask = bars.index + BAR_LEN[tf] >= now_ts - pd.Timedelta(days=settings.RECENT_DAYS)
            for pos in np.flatnonzero(new_mask & (bars["buy"] | (bars["sell"] & (not buy_only))).to_numpy()):
                new_flips.append(flip_entry(sym, ticker, tf, bars, int(pos), ctx, run_utc))

            # 2) fresh signals for the Buying Opportunities panel / stats
            if tf == "4H":
                fresh_mask = bars.index + BAR_LEN[tf] >= now_ts - pd.Timedelta(hours=settings.FRESH_4H_HOURS)
                fresh_pos = np.flatnonzero((fresh_mask & bars["buy"]).to_numpy())
            else:
                last = len(bars) - 1
                fresh_pos = [last] if bars["buy"].iloc[-1] or bars["sell"].iloc[-1] else []
            for pos in fresh_pos:
                fresh.append(flip_entry(sym, ticker, tf, bars, int(pos), ctx, run_utc))

            snap = tf_snapshot(bars, tf, prev, now_ts)
            row["tf"][tf] = snap
            new_state[tf] = {"last_bar": bars.index[-1].isoformat(), "trend": snap["trend"]}

        st["coins"][sym] = new_state
        rows.append(row)
        log.info("%-6s %-14s ok", sym, ticker)

    # ---- list changes ----------------------------------------------------
    cur_universe = {c["symbol"] for c in universe if c["symbol"] not in settings.STABLECOINS}
    prev_universe = set(st.get("universe") or [])
    removed = sorted(prev_universe - cur_universe)
    for sym in removed:
        st["coins"].pop(sym, None)

    # ---- held-bearish alerts ---------------------------------------------
    alerts = []
    held = {r["symbol"]: r for r in rows if r["held"]}
    for f in fresh:
        if f["direction"] == "sell" and f["symbol"] in held:
            alerts.append({**f, "entry": held[f["symbol"]].get("entry"),
                           "pnl_pct": held[f["symbol"]].get("pnl_pct")})

    flip_log = state_mod.merge_flip_log(flip_log, new_flips, now)

    ctx_out = {
        "run_utc": run_utc, "today": today, "first_run": first_run,
        "fresh": fresh, "alerts": alerts, "rows": rows,
        "flip_log": flip_log, "btc": btc_ctx, "has_portfolio": bool(portfolio),
        "changes": {"added": sorted(cur_universe - prev_universe) if prev_universe else [],
                    "removed": removed, "replacements": replacements,
                    "failures": failures, "excluded": excluded},
        "universe_size": len(universe),
    }

    html = report.build_html(ctx_out)
    report_name = f"{settings.REPORT_PREFIX}{today}.html"
    if not args.dry_run:
        moved = state_mod.migrate_legacy_reports()
        if moved:
            log.info("Moved %d report(s) from reports/ to docs/reports/", len(moved))
        report_name, deleted = state_mod.write_site(html, today, report)
        if deleted:
            log.info("Retention: deleted %d old report(s): %s", len(deleted), ", ".join(deleted))
        log.info("Website written: docs/index.html + docs/reports/%s", report_name)

    if not (args.no_email or args.dry_run):
        emailer.send(report.subject(ctx_out), report.email_summary(ctx_out), html, report_name)

    if not args.dry_run:
        st["universe"] = sorted(cur_universe)
        st["last_run"] = run_utc
        state_mod.save_state(st)
        state_mod.save_flip_log(flip_log)
        data.save_resolved(resolved)
        state_mod.append_signal_log(new_flips, run_utc)

    log.info("Done: %d fresh signals, %d new flips logged, %d failures", len(fresh), len(new_flips), len(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
