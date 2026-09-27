"""
Opportunity filter: "checks, not a wall".

Hard gates remove flips that are not tradeable any more (stop already hit, TP1
already hit, stop too wide, illiquid). Everything else is judged on five
volume/momentum checks; a flip is shown when it meets at least `min_checks`
of them, and flips meeting more checks rank first. See settings.OPPORTUNITY_FILTERS.
"""
from __future__ import annotations

import math

import settings

CHECK_NAMES = ["volume", "rsi", "vs_btc", "holding", "trend"]
CHECK_LABELS = {"volume": "Volume", "rsi": "RSI", "vs_btc": "vs BTC", "holding": "Holding", "trend": "Trend"}
TREND_SOURCE = {"4H": ("trend_1D", "Daily"), "1D": ("trend_1W", "Weekly"), "1W": ("trend_1D", "Daily")}


def _num(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def evaluate(e: dict, last_price: float | None) -> dict:
    """
    Returns {"hard_fails": [...], "checks": {name: (met, detail)}, "met": int,
             "passed": bool, "tier": "Strong" | "Watch" | None}
    """
    f = settings.OPPORTUNITY_FILTERS[e["tf"]]
    hard: list[str] = []

    # ---- hard gates -------------------------------------------------------
    cap = settings.TIMEFRAMES[e["tf"]]["max_risk_pct"]
    if e.get("risk_pct") is not None and e["risk_pct"] > cap:
        hard.append(f"stop {e['risk_pct']:.1f}% wider than {cap:g}%")
    dv = _num(e.get("dollar_vol_30d"))
    if dv is not None and dv < settings.MIN_DOLLAR_VOLUME:
        hard.append(f"thin liquidity ${dv / 1e6:.1f}M/day")
    if last_price is not None:
        if last_price <= e["stop"]:
            hard.append("already below stop")
        elif last_price >= e["tp1"]:
            hard.append("already past TP1")

    # ---- five checks ------------------------------------------------------
    checks: dict[str, tuple[bool, str]] = {}

    vr = _num(e.get("vol_ratio"))
    checks["volume"] = ((vr is not None and vr >= f["min_vol_ratio"]),
                        "no volume data" if vr is None else f"volume {vr:.2f}x (need {f['min_vol_ratio']:g}x)")

    r = _num(e.get("rsi"))
    checks["rsi"] = ((r is not None and f["rsi_min"] <= r <= f["rsi_max"]),
                     "no RSI" if r is None else f"RSI {r:.0f} (need {f['rsi_min']}-{f['rsi_max']})")

    rs = _num(e.get("rs_7d"))
    checks["vs_btc"] = ((rs is not None and rs >= f["min_rs_vs_btc_7d"]),
                        "no 7-day data" if rs is None else f"vs BTC 7d {rs:+.1f} pts (need ≥ {f['min_rs_vs_btc_7d']:g})")

    if last_price is None:
        checks["holding"] = (False, "no current price")
    else:
        move = (last_price / e["close"] - 1) * 100
        checks["holding"] = (move >= -f["hold_tolerance_pct"],
                             f"{move:+.1f}% since flip (allowed down to -{f['hold_tolerance_pct']:g}%)")

    key, label = TREND_SOURCE[e["tf"]]
    t = e.get(key)
    checks["trend"] = (t == 1, f"{label} trend {'up' if t == 1 else 'down' if t == -1 else 'unknown'}")

    met = sum(1 for ok, _ in checks.values() if ok)
    passed = not hard and met >= f["min_checks"]
    tier = None
    if passed:
        tier = "Strong" if met >= settings.STRONG_MIN_CHECKS else "Watch"
    return {"hard_fails": hard, "checks": checks, "met": met, "passed": passed, "tier": tier}


def reasons(e: dict) -> list[str]:
    """Why a flip isn't shown: hard gate failures first, else the checks it missed."""
    if e["hard_fails"]:
        return e["hard_fails"]
    missed = [detail for ok, detail in e["checks"].values() if not ok]
    need = settings.OPPORTUNITY_FILTERS[e["tf"]]["min_checks"]
    return [f"only {e['met']}/5 checks (need {need})"] + missed


def split(entries: list[dict], prices: dict[str, float]) -> tuple[list[dict], list[dict]]:
    """Tags each entry and returns (shown candidates, not shown), best first."""
    passed, rejected = [], []
    for e in entries:
        res = evaluate(e, prices.get(e["symbol"]))
        e.update(res)
        e["fail_reasons"] = [] if res["passed"] else reasons(e)
        (passed if res["passed"] else rejected).append(e)
    key = lambda e: (-e["met"], -e["score"], e["symbol"])  # noqa: E731
    return sorted(passed, key=key), sorted(rejected, key=key)


def check_counts(entries: list[dict]) -> dict[str, int]:
    """How many flips met each check (entries must have been through split())."""
    return {n: sum(1 for e in entries if e["checks"][n][0]) for n in CHECK_NAMES}


def describe(tf: str) -> str:
    f = settings.OPPORTUNITY_FILTERS[tf]
    trend = TREND_SOURCE[tf][1]
    return (f"at least {f['min_checks']} of 5 checks: volume ≥ {f['min_vol_ratio']:g}x, "
            f"RSI {f['rsi_min']}-{f['rsi_max']}, vs BTC 7d ≥ {f['min_rs_vs_btc_7d']:g} pts, "
            f"holding within {f['hold_tolerance_pct']:g}% of the flip close, {trend} trend up. "
            f"Always required: price above stop and below TP1, stop ≤ {settings.TIMEFRAMES[tf]['max_risk_pct']:g}%, "
            f"≥ ${settings.MIN_DOLLAR_VOLUME / 1e6:g}M/day volume")
