"""Opportunity filter gates."""
import filters


def flip(**kw):
    e = {"symbol": "SOL", "tf": "4H", "close": 100.0, "stop": 94.0, "tp1": 112.0, "tp2": 118.0,
         "risk_pct": 6.0, "score": 70, "grade": "B", "vol_ratio": 2.0, "rsi": 62.0, "rs_7d": 3.0,
         "trend_1D": 1, "trend_1W": 1, "dollar_vol_30d": 50e6}
    e.update(kw)
    return e


def test_good_4h_flip_passes():
    ok, why = filters.evaluate(flip(), last_price=101.0)
    assert ok, why


def test_volume_gate():
    ok, why = filters.evaluate(flip(vol_ratio=1.2), 101.0)
    assert not ok and any("volume" in w for w in why)
    ok, why = filters.evaluate(flip(vol_ratio=None), 101.0)
    assert not ok and "no volume data" in why


def test_momentum_gates():
    assert not filters.evaluate(flip(rsi=48), 101.0)[0]            # too weak
    assert not filters.evaluate(flip(rsi=80), 101.0)[0]            # stretched
    assert not filters.evaluate(flip(rs_7d=-2.0), 101.0)[0]        # lagging BTC
    assert not filters.evaluate(flip(), 99.0)[0]                   # faded below flip close


def test_trend_and_trade_validity():
    assert not filters.evaluate(flip(trend_1D=-1), 101.0)[0]       # 4H against Daily
    assert not filters.evaluate(flip(risk_pct=9.5), 101.0)[0]      # stop wider than 8%
    assert not filters.evaluate(flip(), 113.0)[0]                  # already past TP1
    assert not filters.evaluate(flip(dollar_vol_30d=1e6), 101.0)[0]


def test_split_sorts_by_score_and_tags_reasons():
    a, b, c = flip(symbol="A", score=60), flip(symbol="B", score=80), flip(symbol="C", vol_ratio=1.0)
    passed, rejected = filters.split([a, b, c], {"A": 101, "B": 101, "C": 101})
    assert [e["symbol"] for e in passed] == ["B", "A"]
    assert rejected[0]["symbol"] == "C" and rejected[0]["fail_reasons"]
