"""Opportunity filter: hard gates + 'at least N of 5 checks'."""
import filters
import settings


def flip(**kw):
    e = {"symbol": "SOL", "tf": "4H", "close": 100.0, "stop": 94.0, "tp1": 112.0, "tp2": 118.0,
         "risk_pct": 6.0, "score": 70, "grade": "B", "vol_ratio": 2.0, "rsi": 62.0, "rs_7d": 3.0,
         "trend_1D": 1, "trend_1W": 1, "dollar_vol_30d": 50e6}
    e.update(kw)
    return e


def test_all_checks_is_strong():
    r = filters.evaluate(flip(), 101.0)
    assert r["passed"] and r["met"] == 5 and r["tier"] == "Strong"


def test_one_miss_still_shown():
    # the old all-or-nothing filter dropped this; now it's still a Strong candidate
    r = filters.evaluate(flip(vol_ratio=None), 101.0)
    assert r["passed"] and r["met"] == 4 and r["tier"] == "Strong"


def test_three_checks_is_watch_two_is_hidden():
    r = filters.evaluate(flip(vol_ratio=1.0, rsi=45), 101.0)
    assert r["passed"] and r["tier"] == "Watch"
    r = filters.evaluate(flip(vol_ratio=1.0, rsi=45, rs_7d=-9), 101.0)
    assert not r["passed"]


def test_small_dip_counts_as_holding():
    tol = settings.OPPORTUNITY_FILTERS["4H"]["hold_tolerance_pct"]
    assert filters.evaluate(flip(), 100 * (1 - tol / 100) + 0.01)["checks"]["holding"][0]
    assert not filters.evaluate(flip(), 100 * (1 - tol / 100) - 0.5)["checks"]["holding"][0]


def test_hard_gates_override_checks():
    assert not filters.evaluate(flip(), 93.0)["passed"]              # below stop
    assert not filters.evaluate(flip(), 113.0)["passed"]             # past TP1
    assert not filters.evaluate(flip(risk_pct=12), 101.0)["passed"]  # stop wider than 4H cap
    assert not filters.evaluate(flip(dollar_vol_30d=1e6), 101.0)["passed"]


def test_split_orders_by_checks_then_score():
    a = flip(symbol="A", score=90, vol_ratio=1.0)   # 4 checks
    b = flip(symbol="B", score=60)                   # 5 checks
    c = flip(symbol="C", vol_ratio=1.0, rsi=40, rs_7d=-9)  # 2 checks -> hidden
    shown, hidden = filters.split([a, b, c], {"A": 101, "B": 101, "C": 101})
    assert [e["symbol"] for e in shown] == ["B", "A"]
    assert hidden[0]["symbol"] == "C" and hidden[0]["fail_reasons"][0].startswith("only 2/5")
