"""Candle construction: UTC alignment and dropping the still-forming bar."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import data


def hourly(start, hours):
    idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    v = np.arange(hours, dtype=float) + 100
    return pd.DataFrame({"Open": v, "High": v + 1, "Low": v - 1, "Close": v + 0.5, "Volume": 1.0}, index=idx)


def daily(start, days):
    idx = pd.date_range(start, periods=days, freq="D", tz="UTC")
    v = np.arange(days, dtype=float) + 100
    return pd.DataFrame({"Open": v, "High": v + 1, "Low": v - 1, "Close": v + 0.5, "Volume": 1.0}, index=idx)


def test_4h_bins_align_to_utc_midnight_and_drop_forming_bar():
    now = datetime(2026, 9, 26, 10, 30, tzinfo=timezone.utc)   # 08:00 bar still forming
    h = hourly("2026-09-25 00:00", 35)                           # up to 10:00 on the 26th
    h4 = data.to_4h(h, now)
    assert all(ts.hour % 4 == 0 and ts.minute == 0 for ts in h4.index)
    assert h4.index[-1] == pd.Timestamp("2026-09-26 04:00", tz="UTC")
    first = h4.iloc[0]
    assert first["Open"] == h["Open"].iloc[0]
    assert first["Close"] == h["Close"].iloc[3]
    assert first["High"] == h["High"].iloc[:4].max()
    assert first["Volume"] == 4.0


def test_daily_drops_today():
    now = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    d = data.closed_daily(daily("2026-09-20", 7), now)
    assert d.index[-1] == pd.Timestamp("2026-09-25", tz="UTC")


def test_weekly_weeks_start_monday_and_forming_week_dropped():
    now = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)      # Saturday
    d = data.closed_daily(daily("2026-08-31", 27), now)          # Mon 31 Aug onwards
    wk = data.to_weekly(d, now)
    assert all(ts.dayofweek == 0 for ts in wk.index)
    assert wk.index[-1] == pd.Timestamp("2026-09-14", tz="UTC")  # week of 21 Sep not closed yet
    first = wk.iloc[0]
    assert first["Open"] == d["Open"].iloc[0]
    assert first["Close"] == d["Close"].iloc[6]
