"""
State persisted as committed files in the repo (same pattern as the US tool;
the commits also keep GitHub Actions from auto-disabling the schedule).

data/state.json
  {
    "last_run": "...",
    "last_digest_date": "YYYY-MM-DD",
    "universe": ["BTC", "ETH", ...],
    "coins": {
      "BTC": {
        "ticker": "BTC-USD",
        "1W": {"last_bar": iso, "trend": 1, "last_flip": iso, "last_flip_dir": "buy"},
        "1D": {...},
        "4H": {...}
      }
    }
  }

data/signal_log.csv  one row per flip ever emitted, for later score validation.
"""
from __future__ import annotations

import csv
import json

import settings

LOG_FIELDS = [
    "run_utc", "symbol", "ticker", "timeframe", "direction", "bar_time",
    "entry", "stop", "tp1", "tp2", "risk_pct", "score", "grade",
]


def load_state(path=settings.STATE_FILE) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"coins": {}, "universe": [], "last_digest_date": None, "last_run": None}


def save_state(state: dict, path=settings.STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str))


def append_signal_log(rows: list[dict], run_utc: str, path=settings.SIGNAL_LOG_CSV) -> None:
    if not rows:
        return
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({
                "run_utc": run_utc,
                "symbol": r["symbol"],
                "ticker": r["ticker"],
                "timeframe": r["tf"],
                "direction": r["direction"],
                "bar_time": r["bar_time"],
                "entry": _fmt(r.get("entry")),
                "stop": _fmt(r.get("stop")),
                "tp1": _fmt(r.get("tp1")),
                "tp2": _fmt(r.get("tp2")),
                "risk_pct": _fmt(r.get("risk_pct"), 2),
                "score": r.get("score", ""),
                "grade": r.get("grade", ""),
            })


def _fmt(v, nd=8):
    if v is None:
        return ""
    return f"{v:.{nd}g}" if nd > 2 else f"{v:.{nd}f}"
