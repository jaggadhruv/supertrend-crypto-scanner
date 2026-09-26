"""
Supertrend, reimplemented from TradingView's built-in "Supertrend" script.

Pine reference (default settings, "Change ATR Calculation Method" = on):

    atr  = ta.atr(Periods)                         // Wilder RMA of true range
    up   = hl2 - Multiplier * atr
    up1  = nz(up[1], up)
    up  := close[1] > up1 ? max(up, up1) : up
    dn   = hl2 + Multiplier * atr
    dn1  = nz(dn[1], dn)
    dn  := close[1] < dn1 ? min(dn, dn1) : dn
    trend := nz(trend[1], 1)
    trend := trend == -1 and close > dn1 ? 1 : trend == 1 and close < up1 ? -1 : trend

This is the same logic as the US equity tool, so a golden-file check against
TradingView is the gate before trusting any signal (see tests/).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """TradingView ta.tr(true): first bar falls back to high - low."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr.iloc[0] = df["High"].iloc[0] - df["Low"].iloc[0]
    return tr


def rma(series: pd.Series, length: int) -> pd.Series:
    """TradingView ta.rma: seeded with an SMA of the first `length` values, then Wilder smoothing."""
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < length:
        return pd.Series(out, index=series.index)
    out[length - 1] = values[:length].mean()
    alpha = 1.0 / length
    for i in range(length, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return pd.Series(out, index=series.index)


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    return rma(true_range(df), length)


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 2.5) -> pd.DataFrame:
    """
    Returns a copy of df with columns:
      atr, up, dn, trend (1 / -1), st_line, buy (bool), sell (bool)

    st_line is the active band: `up` while trend == 1 (support / stop level),
    `dn` while trend == -1 (resistance).
    """
    out = df.copy()
    a = atr(df, period).to_numpy()
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    hl2 = (high + low) / 2.0
    n = len(df)

    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    trend = np.ones(n, dtype=int)

    for i in range(n):
        prev_trend = trend[i - 1] if i > 0 else 1
        if np.isnan(a[i]):
            trend[i] = prev_trend
            continue

        basic_up = hl2[i] - multiplier * a[i]
        basic_dn = hl2[i] + multiplier * a[i]

        up1 = up[i - 1] if i > 0 and not np.isnan(up[i - 1]) else basic_up
        dn1 = dn[i - 1] if i > 0 and not np.isnan(dn[i - 1]) else basic_dn

        prev_close = close[i - 1] if i > 0 else close[i]
        up[i] = max(basic_up, up1) if prev_close > up1 else basic_up
        dn[i] = min(basic_dn, dn1) if prev_close < dn1 else basic_dn

        if prev_trend == -1 and close[i] > dn1:
            trend[i] = 1
        elif prev_trend == 1 and close[i] < up1:
            trend[i] = -1
        else:
            trend[i] = prev_trend

    out["atr"] = a
    out["up"] = up
    out["dn"] = dn
    out["trend"] = trend
    out["st_line"] = np.where(trend == 1, up, dn)

    prev = np.roll(trend, 1)
    valid = ~np.isnan(a)
    valid_prev = np.roll(valid, 1)
    valid_prev[0] = False
    out["buy"] = (trend == 1) & (prev == -1) & valid & valid_prev
    out["sell"] = (trend == -1) & (prev == 1) & valid & valid_prev
    return out


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder RSI, same smoothing TradingView uses."""
    delta = close.diff()
    gain = delta.clip(lower=0).fillna(0)
    loss = (-delta.clip(upper=0)).fillna(0)
    avg_gain = rma(gain.iloc[1:], length).reindex(close.index)
    avg_loss = rma(loss.iloc[1:], length).reindex(close.index)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(avg_loss == 0) & avg_gain.notna()] = 100.0
    return out
