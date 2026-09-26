"""
Crypto Supertrend scan. Runs every 4 hours via GitHub Actions.

    python run_scan.py                 # normal run (email if secrets are set)
    python run_scan.py --no-email      # write report only
    python run_scan.py --dry-run       # no email, no state/log writes
    python run_scan.py --force-digest  # include full state table and send even without flips

Flow per coin:
  resolve Yahoo ticker -> fetch 1d + 1h -> build closed 1W / 1D / 4H bars
  -> Supertrend on each -> find flips on bars newer than last run
  -> BUY flips get SL / TP + quality score, SELL flips (1W / 1D only) become exit alerts
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


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame | None:
    if bars is None or len(bars) < MIN_BARS:
        return None
    out = supertrend(bars, settings.ATR_PERIOD, settings.MULTIPLIER)
    out["rsi"] = rsi(out["Close"])
    return out


def last_flip(bars: pd.DataFrame):
    flips = bars.index[bars["buy"] | bars["sell"]]
    if len(flips) == 0:
        return None, None
    ts = flips[-1]
    return ts, ("buy" if bars.at[ts, "buy"] else "sell")


def sma_flag(close: pd.Series, n: int):
    if len(close) < n:
        return None
    return bool(close.iloc[-1] > close.rolling(n).mean().iloc[-1])


def build_frames(daily_raw: pd.DataFrame, hourly_raw: pd.DataFrame, now) -> dict:
    d = data.closed_daily(daily_raw, now)
    frames = {
        "1D": add_indicators(d),
        "1W": add_indicators(data.to_weekly(d, now)),
        "4H": add_indicators(data.to_4h(hourly_raw, now)),
    }
    frames["_daily_closed"] = d
    return frames


def coin_context(frames: dict, btc_ctx: dict) -> dict:
    d = frames["_daily_closed"]
    w = frames["1W"]
    ctx = dict(btc_ctx)
    ctx["trend_1D"] = int(frames["1D"]["trend"].iloc[-1]) if frames["1D"] is not None else None
    ctx["trend_1W"] = int(w["trend"].iloc[-1]) if w is not None else None
    ctx["above_sma200d"] = sma_flag(d["Close"], 200)
    if w is not None and len(w) >= 54:
        sma50 = w["Close"].rolling(50).mean()
        ctx["above_sma50w"] = bool(w["Close"].iloc[-1] > sma50.iloc[-1])
        ctx["sma50w_rising"] = bool(sma50.iloc[-1] > sma50.iloc[-5])
    else:
        ctx["above_sma50w"] = None
        ctx["sma50w_rising"] = None
    tail = d.tail(30)
    ctx["dollar_volume_30d"] = float((tail["Close"] * tail["Volume"]).mean()) if len(tail) else None
    return ctx


def is_stable(daily: pd.DataFrame) -> bool:
    tail = daily["Close"].tail(90)
    if len(tail) < 30:
        return False
    return (tail.max() - tail.min()) / tail.mean() * 100 < settings.STABLE_RANGE_PCT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-digest", action="store_true")
    args = ap.parse_args(argv)

    now = data.utcnow()
    run_utc = now.strftime("%Y-%m-%d %H:%M UTC")
    today = now.strftime("%Y-%m-%d")

    universe = data.load_universe()
    overrides = data.load_overrides()
    resolved = data.load_resolved()
    st = state_mod.load_state()
    first_run = not st.get("coins")

    excluded, failures, replacements = [], [], []
    signals, exits, full_rows = [], [], []

    # ---- BTC regime first (always, even if BTC isn't in the CSV) ----------
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
            ticker, daily_raw = cache[sym]
            note = ""
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
        last_price = float(hourly_raw["Close"].iloc[-1]) if not hourly_raw.empty else float(daily_raw["Close"].iloc[-1])
        coin_state = st["coins"].get(sym, {})
        new_coin_state = {"ticker": ticker}
        row = {"symbol": sym, "rank": coin["rank"], "ticker": ticker, "price": last_price, "tf": {}}

        for tf in settings.TIMEFRAME_ORDER:
            bars = frames[tf]
            if bars is None:
                row["tf"][tf] = None
                continue
            prev_last = coin_state.get(tf, {}).get("last_bar")
            if prev_last is None:
                new_idx = bars.index[-1:]      # first sight of this coin/TF: only the latest bar counts
            else:
                new_idx = bars.index[bars.index > pd.Timestamp(prev_last)]

            for ts in new_idx:
                pos = bars.index.get_loc(ts)
                is_buy, is_sell = bool(bars.at[ts, "buy"]), bool(bars.at[ts, "sell"])
                base = {"symbol": sym, "rank": coin["rank"], "ticker": ticker, "tf": tf,
                        "bar_time": ts.isoformat(), "last_price": last_price}
                if is_buy:
                    sc = scoring.score_buy_flip(tf, bars, pos, ctx)
                    signals.append({**base, **sc, "direction": "buy",
                                    "move_since": (last_price / sc["entry"] - 1) * 100,
                                    "status": _status(last_price, sc)})
                elif is_sell and not settings.TIMEFRAMES[tf]["buy_only"]:
                    close = float(bars.at[ts, "Close"])
                    exits.append({**base, "direction": "sell", "entry": close,
                                  "st_line": float(bars.at[ts, "st_line"]),
                                  "move_since": (last_price / close - 1) * 100})

            lf_ts, lf_dir = last_flip(bars)
            trend = int(bars["trend"].iloc[-1])
            st_line = float(bars["st_line"].iloc[-1])
            new_coin_state[tf] = {
                "last_bar": bars.index[-1].isoformat(),
                "trend": trend,
                "last_flip": lf_ts.isoformat() if lf_ts is not None else None,
                "last_flip_dir": lf_dir,
            }
            row["tf"][tf] = {
                "trend": trend,
                "since": lf_ts,
                "bars_since": (len(bars) - 1 - bars.index.get_loc(lf_ts)) if lf_ts is not None else None,
                "dist_pct": (last_price / st_line - 1) * 100 if st_line else np.nan,
            }
        st["coins"][sym] = new_coin_state
        full_rows.append(row)
        log.info("%-6s %-14s ok", sym, ticker)

    # ---- list changes ---------------------------------------------------
    prev_universe = set(st.get("universe") or [])
    cur_universe = {c["symbol"] for c in universe if c["symbol"] not in settings.STABLECOINS}
    added = sorted(cur_universe - prev_universe) if prev_universe else []
    removed = sorted(prev_universe - cur_universe)
    for sym in removed:
        st["coins"].pop(sym, None)

    signals.sort(key=lambda s: (-s["score"], s["rank"]))
    exits.sort(key=lambda s: (settings.TIMEFRAME_ORDER.index(s["tf"]), s["rank"]))

    is_digest = args.force_digest or st.get("last_digest_date") != today
    breadth = {
        tf: _breadth(full_rows, tf) for tf in settings.TIMEFRAME_ORDER
    }
    ctx_out = {
        "run_utc": run_utc,
        "is_digest": is_digest,
        "first_run": first_run,
        "signals": signals,
        "exits": exits,
        "full_rows": sorted(full_rows, key=lambda r: r["rank"]),
        "btc": btc_ctx,
        "breadth": breadth,
        "changes": {"added": added, "removed": removed, "replacements": replacements,
                    "failures": failures, "excluded": excluded},
        "summary": {
            "universe": len(universe),
            "scanned": len(full_rows),
            "excluded": len(excluded),
            "failed": len(failures),
            "buy_flips": len(signals),
            "exit_alerts": len(exits),
        },
    }

    html_full = report.build_html(ctx_out, include_full_state=True)
    settings.REPORTS_DIR.mkdir(exist_ok=True)
    if not args.dry_run:
        (settings.REPORTS_DIR / "latest.html").write_text(html_full, encoding="utf-8")
        if is_digest:
            daily_dir = settings.REPORTS_DIR / "daily"
            daily_dir.mkdir(exist_ok=True)
            (daily_dir / f"{today}.html").write_text(html_full, encoding="utf-8")

    should_email = bool(signals or exits) or is_digest or settings.EMAIL_ON_NO_FLIPS
    if should_email and not (args.no_email or args.dry_run):
        html_mail = report.build_html(ctx_out, include_full_state=is_digest and settings.DIGEST_INCLUDE_FULL_STATE)
        emailer.send(report.subject(ctx_out), html_mail)

    if not args.dry_run:
        st["universe"] = sorted(cur_universe)
        st["last_run"] = run_utc
        if is_digest:
            st["last_digest_date"] = today
        state_mod.save_state(st)
        data.save_resolved(resolved)
        state_mod.append_signal_log(signals + exits, run_utc)

    log.info("Done: %d buy flips, %d exit alerts, %d failures", len(signals), len(exits), len(failures))
    return 0


def _status(last_price: float, sc: dict) -> str:
    if last_price <= sc["stop"]:
        return "Below stop now"
    if last_price >= sc["tp2"]:
        return "TP2 already reached"
    if last_price >= sc["tp1"]:
        return "TP1 already reached"
    return "Live"


def _breadth(rows: list[dict], tf: str) -> dict:
    vals = [r["tf"][tf]["trend"] for r in rows if r["tf"].get(tf)]
    up = sum(1 for v in vals if v == 1)
    return {"up": up, "total": len(vals), "pct": up / len(vals) * 100 if vals else 0.0}


if __name__ == "__main__":
    sys.exit(main())
