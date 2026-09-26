"""
Phase 1 gate, same as the US tool: Supertrend must reproduce TradingView.

Two layers:
  1. Synthetic tests (always run): mechanics that must hold on any data.
  2. Golden files (run when present): tests/golden/*.csv produced by
     make_golden_template.py and filled in with values read off TradingView.
     See tests/golden/README.md.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from supertrend import atr, rma, supertrend

GOLDEN = Path(__file__).parent / "golden"
PRICE_TOL = 0.005   # 0.5%: Yahoo aggregates venues, TradingView CRYPTO:<X>USD is also an index


def make_bars(closes, spread=1.0):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D", tz="UTC")
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame({
        "Open": opens,
        "High": np.maximum(opens, closes) + spread,
        "Low": np.minimum(opens, closes) - spread,
        "Close": closes,
        "Volume": 1000.0,
    }, index=idx)


def test_rma_seed_is_sma():
    s = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    out = rma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx((1 / 3) * 4 + (2 / 3) * 2.0)


def test_atr_warmup_length():
    bars = make_bars(np.linspace(100, 120, 30))
    a = atr(bars, 10)
    assert a.iloc[:9].isna().all()
    assert a.iloc[9:].notna().all()


def test_uptrend_then_crash_flips_to_sell_then_buy():
    closes = list(np.linspace(100, 150, 40)) + list(np.linspace(150, 90, 25)) + list(np.linspace(90, 140, 25))
    st = supertrend(make_bars(closes), 10, 2.5)
    sells = st.index[st["sell"]]
    buys = st.index[st["buy"]]
    assert len(sells) >= 1 and len(buys) >= 1
    assert sells[0] < buys[-1]
    assert st["trend"].iloc[-1] == 1


def test_lower_band_never_falls_during_uptrend():
    closes = np.linspace(100, 200, 60)
    st = supertrend(make_bars(closes), 10, 2.5).dropna(subset=["up"])
    up_while_long = st.loc[st["trend"] == 1, "up"]
    assert (up_while_long.diff().dropna() >= -1e-9).all()


def test_st_line_is_below_price_in_uptrend():
    st = supertrend(make_bars(np.linspace(100, 200, 60)), 10, 2.5).dropna(subset=["atr"])
    long = st[st["trend"] == 1]
    assert (long["st_line"] < long["Close"]).all()


def test_no_flip_reported_during_warmup():
    st = supertrend(make_bars(np.r_[np.linspace(100, 50, 12), np.linspace(50, 100, 12)]), 10, 2.5)
    assert not st["buy"].iloc[:10].any()
    assert not st["sell"].iloc[:10].any()


GOLDEN_FILES = sorted(GOLDEN.glob("*.csv"))


@pytest.mark.skipif(not GOLDEN_FILES, reason="no golden files yet, see tests/golden/README.md")
@pytest.mark.parametrize("path", GOLDEN_FILES, ids=[p.name for p in GOLDEN_FILES])
def test_matches_tradingview(path):
    df = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    st = supertrend(df[["Open", "High", "Low", "Close", "Volume"]], 10, 2.5)
    checked = df.dropna(subset=["tv_st_line", "tv_trend"])
    if checked.empty:
        pytest.skip(f"{path.name}: tv_ columns not filled in yet")
    for ts, row in checked.iterrows():
        ours = st.loc[ts]
        assert int(ours["trend"]) == int(row["tv_trend"]), f"{path.name} {ts}: trend differs"
        assert ours["st_line"] == pytest.approx(row["tv_st_line"], rel=PRICE_TOL), (
            f"{path.name} {ts}: line {ours['st_line']:.6g} vs TradingView {row['tv_st_line']:.6g}"
        )
