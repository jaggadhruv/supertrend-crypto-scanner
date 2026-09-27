"""
Opportunity filter: turns "every BUY flip" into "BUY flips worth looking at".

A flip passes only if it clears every gate in settings.OPPORTUNITY_FILTERS for
its timeframe, with the emphasis on volume (participation) and momentum
(RSI in a strong-but-not-stretched band, outperforming BTC, price holding
above the flip close). Failing reasons are kept so the report can say why a
coin was filtered out.
"""
from __future__ import annotations

import math

import settings


def _num(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def evaluate(e: dict, last_price: float | None) -> tuple[bool, list[str]]:
    """Returns (passed, reasons it failed). Only BUY flips are evaluated."""
    f = settings.OPPORTUNITY_FILTERS[e["tf"]]
    fails: list[str] = []

    # --- volume ---------------------------------------------------------
    vr = _num(e.get("vol_ratio"))
    if vr is None:
        fails.append("no volume data")
    elif vr < f["min_vol_ratio"]:
        fails.append(f"volume {vr:.2f}x < {f['min_vol_ratio']:g}x")

    dv = _num(e.get("dollar_vol_30d"))
    if dv is not None and dv < settings.MIN_DOLLAR_VOLUME:
        fails.append(f"thin liquidity ${dv / 1e6:.1f}M/day")

    # --- momentum -------------------------------------------------------
    r = _num(e.get("rsi"))
    if r is None:
        fails.append("no RSI")
    elif r < f["rsi_min"]:
        fails.append(f"RSI {r:.0f} < {f['rsi_min']}")
    elif r > f["rsi_max"]:
        fails.append(f"RSI {r:.0f} > {f['rsi_max']} (stretched)")

    rs = _num(e.get("rs_7d"))
    if rs is None:
        fails.append("no 7-day return vs BTC")
    elif rs < f["min_rs_vs_btc_7d"]:
        fails.append(f"lagging BTC by {-rs:.1f} pts (7d)")

    if f["require_follow_through"] and last_price is not None and last_price < e["close"]:
        fails.append(f"faded {100 * (last_price / e['close'] - 1):.1f}% since flip")

    # --- trend context --------------------------------------------------
    if f["require_daily_up"] and e.get("trend_1D") != 1:
        fails.append("Daily trend down")
    if f["require_weekly_up"] and e.get("trend_1W") != 1:
        fails.append("Weekly trend down")

    # --- trade still valid ----------------------------------------------
    cap = settings.TIMEFRAMES[e["tf"]]["max_risk_pct"]
    if e.get("risk_pct") is not None and e["risk_pct"] > cap:
        fails.append(f"stop {e['risk_pct']:.1f}% > {cap:g}% cap")
    if last_price is not None:
        if last_price <= e["stop"]:
            fails.append("already below stop")
        elif last_price >= e["tp1"]:
            fails.append("already past TP1")

    return not fails, fails


def split(entries: list[dict], prices: dict[str, float]) -> tuple[list[dict], list[dict]]:
    """
    Tags each entry with 'passed' / 'fail_reasons' and returns (qualified, rejected),
    each sorted by quality score. Caps are applied by the caller per section.
    """
    passed, rejected = [], []
    for e in entries:
        ok, why = evaluate(e, prices.get(e["symbol"]))
        e["passed"], e["fail_reasons"] = ok, why
        (passed if ok else rejected).append(e)
    key = lambda e: (-e["score"], e["symbol"])  # noqa: E731
    return sorted(passed, key=key), sorted(rejected, key=key)


def describe(tf: str) -> str:
    """One-line human description of the gates for a timeframe."""
    f = settings.OPPORTUNITY_FILTERS[tf]
    parts = [f"volume ≥ {f['min_vol_ratio']:g}x", f"RSI {f['rsi_min']}-{f['rsi_max']}",
             "beating BTC over 7d" if f["min_rs_vs_btc_7d"] >= 0 else f"within {-f['min_rs_vs_btc_7d']:g} pts of BTC over 7d"]
    if f["require_follow_through"]:
        parts.append("holding above the flip close")
    if f["require_daily_up"]:
        parts.append("Daily trend up")
    if f["require_weekly_up"]:
        parts.append("Weekly trend up")
    parts.append(f"stop ≤ {settings.TIMEFRAMES[tf]['max_risk_pct']:g}%")
    return ", ".join(parts)
