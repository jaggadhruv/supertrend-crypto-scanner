"""
Everything persisted in the repo (committed by the workflow, which also keeps
GitHub Actions from auto-disabling the schedule).

data/state.json       last processed bar + trend per coin and timeframe
data/flip_log.json    rolling flip history (pruned to FLIP_LOG_KEEP_DAYS); feeds the
                      "Recent Buy Flips (Last 7 Days)" panel
data/signal_log.csv   append-only flip history, for validating the quality score later
docs/                 the website (index.html + reports/), see write_site()
input/portfolio.csv   optional holdings (Symbol, Entry_Price, Quantity)
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timedelta

import settings

LOG_FIELDS = [
    "run_utc", "symbol", "ticker", "timeframe", "direction", "bar_time",
    "entry", "stop", "tp1", "tp2", "risk_pct", "score", "grade",
]


# ---------------------------------------------------------------- state
def load_state(path=settings.STATE_FILE) -> dict:
    if path.exists():
        st = json.loads(path.read_text())
        st.setdefault("coins", {})
        return st
    return {"coins": {}, "universe": [], "last_run": None}


def save_state(state: dict, path=settings.STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------- flip log
def load_flip_log(path=settings.FLIP_LOG_FILE) -> list[dict]:
    if path.exists():
        return json.loads(path.read_text())
    return []


def flip_key(e: dict) -> str:
    return f"{e['symbol']}|{e['tf']}|{e['bar_time']}"


def merge_flip_log(log: list[dict], new: list[dict], now: datetime) -> list[dict]:
    """Add new flips (deduplicated) and drop anything older than FLIP_LOG_KEEP_DAYS."""
    by_key = {flip_key(e): e for e in log}
    for e in new:
        by_key.setdefault(flip_key(e), e)
    cutoff = (now - timedelta(days=settings.FLIP_LOG_KEEP_DAYS)).strftime("%Y-%m-%d")
    kept = [e for e in by_key.values() if e["close_date"] >= cutoff]
    return sorted(kept, key=lambda e: (e["close_date"], e["bar_time"], e["symbol"]))


def save_flip_log(log: list[dict], path=settings.FLIP_LOG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=1, default=str))


# ---------------------------------------------------------------- signal log (csv)
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
                "run_utc": run_utc, "symbol": r["symbol"], "ticker": r["ticker"],
                "timeframe": r["tf"], "direction": r["direction"], "bar_time": r["bar_time"],
                "entry": _g(r.get("close")), "stop": _g(r.get("stop")),
                "tp1": _g(r.get("tp1")), "tp2": _g(r.get("tp2")),
                "risk_pct": "" if r.get("risk_pct") is None else f"{r['risk_pct']:.2f}",
                "score": r.get("score", ""), "grade": r.get("grade", ""),
            })


def _g(v):
    return "" if v is None else f"{v:.8g}"


# ---------------------------------------------------------------- portfolio
def load_portfolio(path=settings.PORTFOLIO_CSV) -> dict[str, dict]:
    """symbol -> {"entry": float|None, "qty": float|None}. Missing file = no holdings."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(line for line in fh if not line.startswith("#")):
            low = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            sym = low.get("symbol", "").upper()
            if not sym:
                continue
            out[sym] = {"entry": _num(low.get("entry_price")), "qty": _num(low.get("quantity"))}
    return out


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# ---------------------------------------------------------------- report retention
def cleanup_reports(keep: int = settings.REPORT_RETENTION, folder=settings.REPORTS_DIR) -> list[str]:
    """
    Keep only the newest `keep` report files. Report names carry the date
    (crypto_supertrend_YYYY-MM-DD.html) so name order = date order.
    Returns the names that were deleted.
    """
    files = sorted(folder.glob(f"{settings.REPORT_PREFIX}*.html"), key=lambda p: p.name, reverse=True)
    deleted = []
    for p in files[keep:]:
        p.unlink()
        deleted.append(p.name)
    return deleted


# ---------------------------------------------------------------- website (docs/)
def migrate_legacy_reports(legacy=settings.LEGACY_REPORTS_DIR, target=settings.REPORTS_DIR) -> list[str]:
    """One-off: move reports from the old top-level reports/ folder into docs/reports/, then remove it."""
    if not legacy.exists():
        return []
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in legacy.glob(f"{settings.REPORT_PREFIX}*.html"):
        dest = target / p.name
        if not dest.exists():
            shutil.move(str(p), dest)
            moved.append(p.name)
    shutil.rmtree(legacy, ignore_errors=True)   # old index.html, .nojekyll, .gitkeep, daily/
    return moved


def write_site(report_html: str, today: str, report_mod) -> tuple[str, list[str]]:
    """
    Writes the whole website and applies retention:
      docs/reports/crypto_supertrend_<today>.html   (with a link back to the latest report)
      docs/index.html                                (newest report + archive picker)
      docs/.nojekyll
    Returns (dated report file name, deleted file names).
    """
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{settings.REPORT_PREFIX}{today}.html"
    (settings.REPORTS_DIR / name).write_text(report_mod.build_archived(report_html), encoding="utf-8")
    deleted = cleanup_reports()
    kept = [p.name for p in settings.REPORTS_DIR.glob(f"{settings.REPORT_PREFIX}*.html")]
    (settings.SITE_DIR / "index.html").write_text(report_mod.build_index(report_html, kept), encoding="utf-8")
    (settings.SITE_DIR / ".nojekyll").touch()
    return name, deleted
