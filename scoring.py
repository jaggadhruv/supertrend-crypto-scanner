"""
Trade levels (SL / TP) and the 0-100 quality score for BUY flips.

Score components (weights in settings.SCORE_WEIGHTS):

  trend_alignment (30)  Is the flip going WITH the bigger picture?
                          4H flip : Daily ST up (15) + Weekly ST up (15)
                          1D flip : Weekly ST up (20) + close > 200-day SMA (10)
                          1W flip : close > 50-week SMA (15) + 50-week SMA rising over 4 weeks (15)
  market_regime   (15)  BTC Daily ST up (8) + BTC close > 200-day SMA (7).
                          Alts rarely hold a long against a falling BTC.
  volume          (15)  Flip-bar volume vs 20-bar average. 1.0x = 0, 2.0x+ = full.
  stop_distance   (15)  Stop % vs the timeframe cap. <= 40% of cap = full, >= cap = 0.
                          Tighter stop = better reward per unit of risk at TP.
  candle          (10)  Where the flip bar closed in its range. Top 30% = full.
  momentum        (10)  RSI(14) on the flip bar. 55-70 full, 50-55 / 70-75 = 6,
                          > 75 = 2 (stretched), < 50 = 3.
  cleanliness      (5)  Flips in the prior 30 bars. Many flips = choppy market,
                          Supertrend whipsaws.

  Penalty: 30-day average daily $ volume below settings.MIN_DOLLAR_VOLUME = -10.

Grades: A >= 75, B >= 60, C >= 45, D below.

The weights are a starting hypothesis, not a validated model. Every flip is
logged to data/signal_log.csv so the score can be checked against outcomes
once a few months of signals exist.
"""
from __future__ import annotations

import math

import pandas as pd

import settings

W = settings.SCORE_WEIGHTS


def _lin(x: float, lo: float, hi: float) -> float:
    """0 at lo, 1 at hi, clipped. Works for hi < lo (inverted scale)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def grade(score: float) -> str:
    for threshold, g in settings.GRADES:
        if score >= threshold:
            return g
    return "D"


def trade_levels(entry: float, stop: float) -> dict:
    risk = entry - stop
    tps = [entry + m * risk for m in settings.TP_R_MULTIPLES]
    return {
        "entry": entry,
        "stop": stop,
        "risk": risk,
        "risk_pct": risk / entry * 100 if entry else float("nan"),
        "tp1": tps[0],
        "tp2": tps[1],
        "tp1_pct": (tps[0] / entry - 1) * 100,
        "tp2_pct": (tps[1] / entry - 1) * 100,
    }


def score_buy_flip(tf: str, bars: pd.DataFrame, i: int, ctx: dict) -> dict:
    """
    bars : timeframe DataFrame with supertrend() + 'rsi' columns
    i    : integer position of the flip bar
    ctx  : context dict built in run_scan.py (higher-TF trends, SMAs, BTC regime, liquidity)
    """
    row = bars.iloc[i]
    levels = trade_levels(float(row["Close"]), float(row["st_line"]))
    parts, notes = {}, []

    # --- trend alignment -------------------------------------------------
    ta = 0.0
    if tf == "4H":
        ta += 15 if ctx.get("trend_1D") == 1 else 0
        ta += 15 if ctx.get("trend_1W") == 1 else 0
        if ctx.get("trend_1D") != 1:
            notes.append("Against the Daily trend")
    elif tf == "1D":
        ta += 20 if ctx.get("trend_1W") == 1 else 0
        above = ctx.get("above_sma200d")
        ta += 10 if above else 0
        if above is None:
            notes.append("Under 200 days of history")
    else:  # 1W
        above = ctx.get("above_sma50w")
        rising = ctx.get("sma50w_rising")
        ta += 15 if above else 0
        ta += 15 if rising else 0
        if above is None:
            notes.append("Under 50 weeks of history")
    parts["trend_alignment"] = ta

    # --- market regime (BTC) --------------------------------------------
    mr = (8 if ctx.get("btc_trend_1D") == 1 else 0) + (7 if ctx.get("btc_above_sma200d") else 0)
    parts["market_regime"] = mr
    if ctx.get("btc_trend_1D") == -1:
        notes.append("BTC Daily trend is down")

    # --- volume ----------------------------------------------------------
    lb = settings.VOLUME_LOOKBACK_BARS
    prior_vol = bars["Volume"].iloc[max(0, i - lb):i]
    avg_vol = float(prior_vol.mean()) if len(prior_vol) else 0.0
    vol_ratio = float(row["Volume"]) / avg_vol if avg_vol > 0 else float("nan")
    if math.isnan(vol_ratio):
        notes.append("No volume data from Yahoo")
    parts["volume"] = W["volume"] * _lin(vol_ratio, 1.0, 2.0)

    # --- stop distance ---------------------------------------------------
    cap = settings.TIMEFRAMES[tf]["max_risk_pct"]
    rp = levels["risk_pct"]
    if rp > cap:
        notes.append(f"Wide stop ({rp:.1f}% > {cap:.0f}% cap)")
    parts["stop_distance"] = W["stop_distance"] * _lin(rp, cap, cap * 0.4)

    # --- candle ----------------------------------------------------------
    rng = float(row["High"] - row["Low"])
    close_pos = float((row["Close"] - row["Low"]) / rng) if rng > 0 else 0.5
    parts["candle"] = W["candle"] * _lin(close_pos, 0.3, 0.7)

    # --- momentum --------------------------------------------------------
    r = float(row.get("rsi", float("nan")))
    if math.isnan(r):
        m = 0
    elif 55 <= r <= 70:
        m = 10
    elif 50 <= r < 55 or 70 < r <= 75:
        m = 6
    elif r > 75:
        m = 2
        notes.append(f"RSI stretched ({r:.0f})")
    else:
        m = 3
    parts["momentum"] = m

    # --- cleanliness -----------------------------------------------------
    window = bars.iloc[max(0, i - settings.CHOP_LOOKBACK_BARS):i]
    prior_flips = int(window["buy"].sum() + window["sell"].sum())
    parts["cleanliness"] = {0: 5, 1: 5, 2: 3, 3: 1}.get(prior_flips, 0)
    if prior_flips >= 3:
        notes.append(f"Choppy: {prior_flips} flips in last {settings.CHOP_LOOKBACK_BARS} bars")

    # --- penalty ---------------------------------------------------------
    penalty = 0
    dv = ctx.get("dollar_volume_30d")
    if dv is not None and dv < settings.MIN_DOLLAR_VOLUME:
        penalty = settings.THIN_LIQUIDITY_PENALTY
        notes.append(f"Thin liquidity (${dv / 1e6:.1f}M/day)")

    total = max(0.0, sum(parts.values()) - penalty)
    return {
        **levels,
        "score": round(total, 1),
        "grade": grade(total),
        "parts": {k: round(v, 1) for k, v in parts.items()},
        "penalty": penalty,
        "vol_ratio": vol_ratio,
        "rsi": r,
        "close_pos": close_pos,
        "prior_flips": prior_flips,
        "notes": notes,
    }
