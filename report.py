"""
HTML report in the "Supertrend Combined Scanner" layout (same look as the US tool),
extended with a 4H timeframe, SL / TP on every buy card and quality ranking.

Layout, top to bottom:
  topbar                     title, parameters, generated time
  held-bearish alert banner  only when a coin in input/portfolio.csv gets a Weekly/Daily SELL
  Recent Buy Flips (7 days)  from data/flip_log.json, grouped by day, ranked by quality
  stats row                  fresh signal counts per timeframe
  Buying Opportunities       fresh buys: confluence, Weekly, Daily, 4H (last 24h), ranked
  Data notes                 ticker replacements, failures, exclusions (only if any)
  Full Watchlist             Weekly / Daily / 4H side by side, filters, search, sorting
  footer

CSS and JS live in report_assets/ and are inlined, so each report is one self-contained file.
The email carries a short inline-styled summary with this report attached
(Gmail drops <style> blocks and CSS variables, so the full layout only renders as a file).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from html import escape

import settings

ASSETS = settings.ROOT / "report_assets"
TF_SHORT = {"1W": ("W", "tf-tag-w"), "1D": ("D", "tf-tag-d"), "4H": ("4H", "tf-tag-4h")}
TF_RANK = {"1W": 0, "1D": 1, "4H": 2}


# ------------------------------------------------------------------ formatting
def fp(p) -> str:
    """Price formatting that works from BTC down to PEPE."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    if p >= 1000:
        return f"{p:,.0f}"
    if p >= 10:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.3f}"
    if p <= 0:
        return f"{p}"
    return f"{p:.{-math.floor(math.log10(p)) + 3}f}"


def pct(v, signed=True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def q_class(grade: str) -> str:
    return {"A": "q-high", "B": "q-med", "C": "q-med"}.get(grade, "q-low")


def q_title(e: dict) -> str:
    p = e.get("parts", {})
    w = settings.SCORE_WEIGHTS
    bits = [f"trend {p.get('trend_alignment', 0):g}/{w['trend_alignment']}",
            f"BTC {p.get('market_regime', 0):g}/{w['market_regime']}",
            f"volume {p.get('volume', 0):g}/{w['volume']}",
            f"stop {p.get('stop_distance', 0):g}/{w['stop_distance']}",
            f"candle {p.get('candle', 0):g}/{w['candle']}",
            f"RSI {p.get('momentum', 0):g}/{w['momentum']}",
            f"clean {p.get('cleanliness', 0):g}/{w['cleanliness']}"]
    if e.get("penalty"):
        bits.append(f"liquidity -{e['penalty']}")
    extra = []
    if e.get("vol_ratio") is not None:
        extra.append(f"volume {e['vol_ratio']:.1f}x avg")
    if e.get("rsi") is not None:
        extra.append(f"RSI {e['rsi']:.0f}")
    head = f"Quality {e['score']:.0f}/100, grade {e['grade']}"
    if extra:
        head += " — " + ", ".join(extra)
    return escape(f"{head}. " + "; ".join(bits))


def tf_tag(tf: str, long: bool = False) -> str:
    short, cls = TF_SHORT[tf]
    if long:
        return f'<span class="tf-tag {cls}">{settings.TIMEFRAMES[tf]["label"]}</span>'
    return f'<span class="flip-tag {cls}">{short}</span>'


def levels_html(e: dict) -> str:
    return (f'<div class="fc-levels">Entry <span class="lv-entry">{fp(e["close"])}</span> · '
            f'SL <span class="lv-sl">{fp(e["stop"])}</span> ({pct(-e["risk_pct"])}) · '
            f'TP1 <span class="lv-tp">{fp(e["tp1"])}</span> ({pct(e["tp1_pct"])}) · '
            f'TP2 <span class="lv-tp">{fp(e["tp2"])}</span> ({pct(e["tp2_pct"])})</div>')


def notes_html(e: dict) -> str:
    return f'<div class="fc-notes">{escape("; ".join(e["notes"]))}</div>' if e.get("notes") else ""


def in_trend_label(n: int, tf: str) -> str:
    if tf == "1W":
        return f"{n}w"
    if tf == "1D":
        return f"{n}d"
    hours = n * 4
    return f"{hours}h" if hours < 48 else f"{hours / 24:.1f}d"


# ------------------------------------------------------------------ recent flips panel
def flip_card(e: dict, star: bool) -> str:
    star_html = '<span class="q-star" title="Top-ranked BUY on this day">★</span>' if star else ""
    return f"""
    <div class="flip-card flip-buy">
      {tf_tag(e['tf'])}
      <span class="flip-tkr">{star_html}{escape(e['symbol'])}</span>
      <span class="flip-meta">BUY · Bullish · Close {fp(e['close'])} · ST {fp(e['st'])}</span>
      <span class="q-badge {q_class(e['grade'])}" title="{q_title(e)}">{e['score']:.0f}</span>
      {levels_html(e)}{notes_html(e)}
    </div>"""


def recent_panel(ctx: dict) -> str:
    today = ctx["today"]
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=settings.RECENT_DAYS - 1)).strftime("%Y-%m-%d")
    buys = [e for e in ctx["flip_log"] if e["direction"] == "buy" and e["close_date"] >= cutoff]
    days = sorted({e["close_date"] for e in buys}, reverse=True)
    blocks = []
    for d in days:
        items = sorted((e for e in buys if e["close_date"] == d),
                       key=lambda e: (-e["score"], TF_RANK[e["tf"]], e["symbol"]))
        many = len(items) > 5
        today_tag = ' <span class="today-tag">today</span>' if d == today else ""
        top = f' <span class="flip-topbadge">★ top 3 of {len(items)}</span>' if many else ""
        cards = "".join(flip_card(e, many and i < 3) for i, e in enumerate(items))
        blocks.append(f'<div class="flip-day"><div class="flip-day-head">{d}{today_tag}{top}</div>'
                      f'<div class="flip-grid">{cards}</div></div>')
    body = "".join(blocks) or '<div class="empty-note">No BUY flips in the last 7 days.</div>'
    first = " First run: back-filled from price history." if ctx["first_run"] else ""
    return f"""
    <div class="panel flip-log-panel">
      <div class="panel-head">
        <h2>Recent Buy Flips (Last {settings.RECENT_DAYS} Days)</h2>
        <span class="subtle">{len(buys)} BUY flip(s) across {len(days)} day(s). Anything older than {settings.RECENT_DAYS} days rolls off this list automatically. History in <code>data/flip_log.json</code>.{first}</span>
      </div>
      <div class="flip-mode-note">Long-only view — SELL flips are hidden here (Weekly/Daily sells still trigger the held-bearish alert). Weekly, Daily and 4H buys, grouped by the UTC day the bar closed and sorted by quality; ★ marks the top 3 when a day has more than 5 candidates. Each card shows Entry, SL (Supertrend line) and TP1/TP2 at {settings.TP_R_MULTIPLES[0]:g}R/{settings.TP_R_MULTIPLES[1]:g}R.</div>
      {body}
    </div>"""


# ------------------------------------------------------------------ alerts, stats, buying opportunities
def alert_banner(ctx: dict) -> str:
    if not ctx["alerts"]:
        return ""
    items = []
    for a in ctx["alerts"]:
        tf_label = settings.TIMEFRAMES[a["tf"]]["label"]
        trade = f"Close {fp(a['close'])} · Supertrend resistance {fp(a['st'])}"
        if a.get("entry"):
            trade += f" · Your entry {fp(a['entry'])} · P/L {pct(a.get('pnl_pct'))}"
        items.append(f"""
      <div class="alert-item">
        <div class="alert-ticker">{escape(a['symbol'])}</div>
        <div><div class="alert-body">{tf_label} Supertrend flipped to SELL on a coin you hold. Exit or tighten the stop.</div>
        <div class="alert-trade">{trade}</div></div>
      </div>""")
    return f'<div class="alert-banner"><div class="alert-head">⚠ Held coins turned bearish</div>{"".join(items)}</div>'


def _dedupe_latest(entries: list[dict]) -> list[dict]:
    """A coin can flip more than once in 24h on 4H; keep the latest bar per coin/timeframe."""
    best = {}
    for e in entries:
        k = (e["symbol"], e["tf"])
        if k not in best or e["bar_time"] > best[k]["bar_time"]:
            best[k] = e
    return list(best.values())


def stats_row(ctx: dict, fresh: list[dict], confluence: list) -> str:
    def n(tf, d):
        return sum(1 for e in fresh if e["tf"] == tf and e["direction"] == d)

    btc = ctx["btc"].get("btc_trend_1D")
    btc_num = '<span class="bull">▲</span>' if btc == 1 else '<span class="bear">▼</span>' if btc == -1 else "—"
    errors = len(ctx["changes"]["failures"])
    return f"""
    <div class="stats-row">
      <div class="stat-chip"><div class="num">{len(ctx['rows'])}</div><div class="label">Coins</div></div>
      <div class="stat-chip"><div class="num">{btc_num}</div><div class="label">BTC Daily</div></div>
      <div class="stats-group-label">Weekly</div>
      <div class="stat-chip stat-buy"><div class="num">{n('1W', 'buy')}</div><div class="label">Buy</div></div>
      <div class="stat-chip stat-sell"><div class="num">{n('1W', 'sell')}</div><div class="label">Sell</div></div>
      <div class="stats-group-label">Daily</div>
      <div class="stat-chip stat-buy"><div class="num">{n('1D', 'buy')}</div><div class="label">Buy</div></div>
      <div class="stat-chip stat-sell"><div class="num">{n('1D', 'sell')}</div><div class="label">Sell</div></div>
      <div class="stats-group-label">4H (24h)</div>
      <div class="stat-chip stat-buy"><div class="num">{n('4H', 'buy')}</div><div class="label">Buy</div></div>
      <div class="stats-group-label">Confluence</div>
      <div class="stat-chip stat-buy"><div class="num">{len(confluence)}</div><div class="label">Buy (2+ TF)</div></div>
      <div class="stat-chip"><div class="num">{errors}</div><div class="label">Errors</div></div>
    </div>"""


def buy_item(e: dict, rank: int, extra_tags: str = "") -> str:
    status = ""
    last = e.get("last_close")
    if last is not None:
        if last <= e["stop"]:
            status = '<div class="status-note">Already below stop</div>'
        elif last >= e["tp1"]:
            status = '<div class="status-note">TP1 already reached</div>'
    when = f" · bar {e['bar_time'][:10]}" + (f" {e['bar_time'][11:16]} UTC" if e["tf"] == "4H" else "")
    return f"""
          <div class="buy-item">
            <div class="bi-head"><span class="q-rank">#{rank}</span>{extra_tags}<span class="buy-ticker">{escape(e['symbol'])}</span>
              <span class="q-badge {q_class(e['grade'])}" title="{q_title(e)}">{e['grade']} {e['score']:.0f}</span></div>
            <div class="buy-meta">Close {fp(e['close'])} · ST {fp(e['st'])}{when}</div>
            {levels_html(e)}{notes_html(e)}{status}
          </div>"""


def buying_panel(fresh_buys: list[dict], confluence: list) -> str:
    def grid(items_html):
        return f'<div class="buy-grid">{items_html}</div>' if items_html else '<div class="empty-note">Nothing fresh.</div>'

    conf_html = ""
    for i, (sym, entries) in enumerate(confluence):
        best = max(entries, key=lambda e: e["score"])
        tags = "".join(tf_tag(e["tf"]) for e in sorted(entries, key=lambda e: TF_RANK[e["tf"]]))
        conf_html += buy_item(best, i + 1, tags)

    subs = []
    for tf, head in [("1W", "Buy Flips"), ("1D", "Buy Flips"), ("4H", "Buy Flips (last 24h)")]:
        items = sorted((e for e in fresh_buys if e["tf"] == tf), key=lambda e: (-e["score"], e["symbol"]))
        subs.append(f"""
        <div class="buy-subpanel">
          <h3>{tf_tag(tf, long=True)} {head} <span class="count">{len(items)}</span></h3>
          {grid("".join(buy_item(e, i + 1) for i, e in enumerate(items)))}
        </div>""")
    return f"""
    <div class="panel">
      <h2>Buying Opportunities</h2>
      <div class="buy-panels">
        <div class="buy-subpanel confluence-panel">
          <h3>★ Confluence Buy (fresh BUY on 2+ timeframes) <span class="count">{len(confluence)}</span></h3>
          {grid(conf_html)}
        </div>{"".join(subs)}
      </div>
    </div>"""


def data_notes(ch: dict) -> str:
    items = [f"Added to CSV: {', '.join(ch['added'])}"] if ch["added"] else []
    if ch["removed"]:
        items.append(f"Removed from CSV: {', '.join(ch['removed'])}")
    items += [f"{s}: {n}" for s, n in ch["replacements"]]
    items += [f"{s} skipped: {n}" for s, _, n in ch["failures"]]
    items += [f"{s} excluded: {w}" for s, w in ch["excluded"]]
    if not items:
        return ""
    lis = "".join(f"<li>{escape(x)}</li>" for x in items)
    return f'<div class="panel data-notes"><h2>Data Notes</h2><ul>{lis}</ul></div>'


# ------------------------------------------------------------------ watchlist table
def tf_cell(t: dict | None, tf: str) -> tuple[str, int]:
    if not t:
        return '<td data-sort="9999"><span class="error-cell">no data</span></td>', 9999
    bull = t["trend"] == 1
    word = "Bullish" if bull else "Bearish"
    d = f'<span class="dir {"dir-bull" if bull else "dir-bear"}">{"▲" if bull else "▼"} {word}</span>'
    if t["signal"] == "buy":
        badge = '<span class="badge badge-buy">BUY</span>'
    elif t["signal"] == "sell":
        badge = '<span class="badge badge-sell">SELL</span>'
    elif t["changed"]:
        was = "Bullish" if t["prev_trend"] == 1 else "Bearish"
        badge = f'<span class="flip-changed" title="Was {was} at the last run; the flip bar has already passed">↺ Changed</span>'
    else:
        badge = '<span class="badge badge-none">—</span>'
    unit = {"1W": "week", "1D": "day", "4H": "4H bar"}[tf]
    plural = "" if t["in_trend"] == 1 else "s"
    trend = (f'<span class="in-trend {"trend-bull" if bull else "trend-bear"}" '
             f'title="{word} for {t["in_trend"]} {unit}{plural} — since {t["since"]}">{in_trend_label(t["in_trend"], tf)}</span>')
    return (f'<td data-sort="{t["in_trend"]}"><span class="tf-cell">{d} {badge} {trend} '
            f'<span class="muted small">ST {fp(t["st"])}</span></span></td>'), t["in_trend"]


def confluence_of(r: dict) -> tuple[str, str, int]:
    trends = [r["tf"][tf]["trend"] if r["tf"].get(tf) else None for tf in settings.TIMEFRAME_ORDER]
    arrows = "".join("▲" if t == 1 else "▼" if t == -1 else "·" for t in trends)
    if all(t == 1 for t in trends):
        return "bull", f'<span class="confluence-cell conf-bull" title="Weekly, Daily and 4H all bullish">{arrows}</span>', 0
    if all(t == -1 for t in trends):
        return "bear", f'<span class="confluence-cell conf-bear" title="Weekly, Daily and 4H all bearish">{arrows}</span>', 1
    if any(t is None for t in trends):
        return "none", f'<span class="confluence-cell conf-none">{arrows}</span>', 3
    return "mixed", f'<span class="confluence-cell conf-mixed" title="Weekly / Daily / 4H disagree">{arrows}</span>', 2


def _th_tf(tf: str, extra: str) -> str:
    label = settings.TIMEFRAMES[tf]["label"]
    return (f'<th title="Click to sort by {label.lower()} bars-in-trend (freshest flip first){extra}">'
            f'<span class="tf-tag {TF_SHORT[tf][1]}">{TF_SHORT[tf][0]}</span>'
            f'{label} (dir · signal · in-trend · ST) ↕</th>')


def watchlist(ctx: dict) -> str:
    rows_html = []
    rows = sorted(ctx["rows"], key=lambda r: ((r["tf"].get("1D") or {}).get("in_trend", 9999), r["rank"]))
    for r in rows:
        conf, conf_html, conf_sort = confluence_of(r)
        cells = {tf: tf_cell(r["tf"].get(tf), tf) for tf in settings.TIMEFRAME_ORDER}
        sig = {tf: (r["tf"][tf]["signal"] if r["tf"].get(tf) else "none") for tf in settings.TIMEFRAME_ORDER}
        flip = {tf: "1" if (r["tf"].get(tf) and (r["tf"][tf]["signal"] != "none" or r["tf"][tf]["changed"])) else "0"
                for tf in settings.TIMEFRAME_ORDER}
        held = r["held"]
        held_html = '<span class="held-yes">HELD</span>' if held else '<span class="muted">—</span>'
        pnl = r.get("pnl_pct")
        if held and pnl is not None:
            pnl_html = f'<td data-sort="{pnl:.2f}"><span class="{"pnl-pos" if pnl >= 0 else "pnl-neg"}">{pct(pnl)}</span></td>'
        else:
            pnl_html = '<td data-sort="-99999">—</td>'
        bar = {tf: (r["tf"][tf]["bar"] if r["tf"].get(tf) else "—") for tf in settings.TIMEFRAME_ORDER}
        rows_html.append(f"""
    <tr data-ticker="{escape(r['symbol'].lower())}"
        data-w-signal="{sig['1W']}" data-d-signal="{sig['1D']}" data-h-signal="{sig['4H']}"
        data-w-flip="{flip['1W']}" data-d-flip="{flip['1D']}" data-h-flip="{flip['4H']}"
        data-held="{1 if held else 0}" data-confluence="{conf}"
        data-w-recency="{cells['1W'][1]}" data-d-recency="{cells['1D'][1]}" data-h-recency="{cells['4H'][1]}">
      <td data-sort="{conf_sort}">{conf_html}</td>
      <td class="col-ticker">{escape(r['symbol'])}</td>
      <td data-sort="{r['close']}">{fp(r['close'])}</td>
      {cells['1W'][0]}{cells['1D'][0]}{cells['4H'][0]}
      <td>{held_html}</td>
      {pnl_html}
      <td class="muted small">{bar['1W']}</td>
      <td class="muted small">{bar['1D']}</td>
      <td class="muted small">{bar['4H']}</td>
    </tr>""")

    return f"""
  <div class="panel">
    <h2>Full Watchlist — Weekly, Daily &amp; 4H Side-by-Side</h2>
    <div class="controls">
      <button class="chip-btn active" data-filter="all">All</button>
      <button class="chip-btn" data-filter="recent7">Recent (7d)</button>
      <button class="chip-btn" data-filter="any-buy">Any Buy</button>
      <button class="chip-btn" data-filter="any-sell">Any Sell</button>
      <button class="chip-btn" data-filter="conf-bull">Confluence ▲▲▲</button>
      <button class="chip-btn" data-filter="conf-bear">Confluence ▼▼▼</button>
      <button class="chip-btn" data-filter="weekly-flip">Weekly Flips</button>
      <button class="chip-btn" data-filter="daily-flip">Daily Flips</button>
      <button class="chip-btn" data-filter="h4-flip">4H Flips</button>
      <button class="chip-btn" data-filter="held">My Portfolio</button>
      <input type="text" id="search-box" class="search-box" placeholder="Search coin...">
    </div>
    <div style="overflow-x:auto">
    <table id="scan-table">
      <thead>
        <tr>
          <th title="Weekly / Daily / 4H direction — click to sort: all bull → all bear → mixed → none">Conf. ↕</th>
          <th>Coin</th>
          <th>Close</th>
          {_th_tf('1W', '')}
          {_th_tf('1D', ' — this is the default order')}
          {_th_tf('4H', '')}
          <th>Held</th>
          <th>Position P/L</th>
          <th>Weekly Bar</th>
          <th>Daily Bar</th>
          <th>4H Bar</th>
        </tr>
      </thead>
      <tbody>{"".join(rows_html)}
      </tbody>
    </table>
    </div>
  </div>"""


# ------------------------------------------------------------------ page
def _fresh_sets(ctx: dict):
    # latest traded price (last 1h close) decides "already below stop" / "TP1 reached"
    closes = {r["symbol"]: r.get("last_price") or r["close"] for r in ctx["rows"]}
    fresh = _dedupe_latest(ctx["fresh"])
    for e in fresh:
        e["last_close"] = closes.get(e["symbol"])
    buys = [e for e in fresh if e["direction"] == "buy"]
    by_coin: dict[str, list] = {}
    for e in buys:
        by_coin.setdefault(e["symbol"], []).append(e)
    confluence = sorted(((s, es) for s, es in by_coin.items() if len(es) >= 2),
                        key=lambda x: -max(e["score"] for e in x[1]))
    return fresh, buys, confluence


def build_html(ctx: dict) -> str:
    fresh, buys, confluence = _fresh_sets(ctx)
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    js = (ASSETS / "script.js").read_text(encoding="utf-8")
    tp1, tp2 = settings.TP_R_MULTIPLES
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Supertrend Combined Scanner — {ctx['today']}</title>
<style>
{css}
</style>
</head>
<body>
<div class="wrap">

  <div class="topbar">
    <h1>Crypto Supertrend Combined Scanner</h1>
    <div class="params">ATR({settings.ATR_PERIOD}) &times; {settings.MULTIPLIER} &middot; Weekly + Daily + 4H &middot; Generated {escape(ctx['run_utc'])}</div>
  </div>

  {alert_banner(ctx)}
  {recent_panel(ctx)}
  {stats_row(ctx, fresh, confluence)}
  {buying_panel(buys, confluence)}
  {data_notes(ctx['changes'])}
  {watchlist(ctx)}

  <footer>
    Parameters: ATR period {settings.ATR_PERIOD}, multiplier {settings.MULTIPLIER}. Data via Yahoo Finance (yfinance), which aggregates
    prices across exchanges, so levels can differ slightly from a single-exchange chart. All candles are UTC and only closed bars are used.
    "Signal" is a fresh cross on the latest closed Weekly or Daily bar, or a 4H BUY on any 4H bar closed in the last 24 hours
    (4H SELL flips are not signalled). "↺ Changed" means the direction differs from the last run even though the flip bar has
    already passed, so nothing is missed if a run is skipped. "In-trend" counts consecutive bars in the current direction
    (w = weeks, d = days, h = hours on 4H; hover for the start). Confluence ▲▲▲ means Weekly, Daily and 4H all agree.
    Buy cards: Entry = flip-bar close, SL = Supertrend line on that bar, TP1/TP2 = {tp1:g}R/{tp2:g}R.
    Quality (0-100, A 75+ / B 60+ / C 45+ / D) = trend alignment 30, BTC regime 15, volume 15, stop distance 15, candle 10, RSI 10,
    cleanliness 5, minus 10 for thin liquidity; hover a badge for the breakdown. The table is sorted by Daily flip recency by default;
    click any header to re-sort. Only the newest {settings.REPORT_RETENTION} reports are kept; older ones are deleted automatically.
    This report is a personal analysis tool, not investment advice — verify signals independently before trading.
  </footer>

</div>

<script>
{js}
</script>

</body>
</html>"""


# ------------------------------------------------------------------ email
def subject(ctx: dict) -> str:
    fresh, buys, _ = _fresh_sets(ctx)
    a = sum(1 for e in buys if e["grade"] == "A")
    sells = sum(1 for e in fresh if e["direction"] == "sell")
    parts = [f"{len(buys)} buy" + (f" ({a} A-grade)" if a else "")]
    if sells:
        parts.append(f"{sells} sell")
    if ctx["alerts"]:
        parts.append(f"{len(ctx['alerts'])} HELD ALERT")
    return f"Crypto Supertrend {ctx['today']} | {', '.join(parts)}"


def email_summary(ctx: dict) -> str:
    """Inline-styled summary that survives Gmail. The full report is attached."""
    fresh, buys, confluence = _fresh_sets(ctx)
    bg, panel, border, text, muted = "#0B0E14", "#12161F", "#232A38", "#E7ECF3", "#7C8797"
    bull, bear, amber = "#2FBF71", "#F0475D", "#F0A93D"
    mono = "Consolas, 'SF Mono', monospace"
    gcol = {"A": bull, "B": amber, "C": amber, "D": muted}

    alerts = ""
    for a in ctx["alerts"]:
        alerts += (f'<div style="padding:8px 12px;margin-bottom:6px;border:1px solid {bear};color:{bear};font-weight:700;font-size:13px">'
                   f'{escape(a["symbol"])}: {settings.TIMEFRAMES[a["tf"]]["label"]} SELL on a held coin '
                   f'(close {fp(a["close"])}, P/L {pct(a.get("pnl_pct"))})</div>')

    td = f"padding:6px 8px;border-bottom:1px solid {border};font-family:{mono};font-size:12px;color:{text}"
    th = f"padding:6px 8px;border-bottom:1px solid {border};font-size:11px;color:{muted};text-align:left"
    rows = ""
    conf_syms = {s for s, _ in confluence}
    for e in sorted(buys, key=lambda e: (-e["score"], TF_RANK[e["tf"]])):
        star = "★ " if e["symbol"] in conf_syms else ""
        rows += (f"<tr><td style=\"{td};color:{gcol[e['grade']]};font-weight:700\">{e['grade']} {e['score']:.0f}</td>"
                 f"<td style=\"{td};font-weight:700\">{star}{escape(e['symbol'])}</td>"
                 f"<td style=\"{td}\">{TF_SHORT[e['tf']][0]}</td>"
                 f"<td style=\"{td}\">{fp(e['close'])}</td>"
                 f"<td style=\"{td};color:{bear}\">{fp(e['stop'])} ({pct(-e['risk_pct'])})</td>"
                 f"<td style=\"{td};color:{bull}\">{fp(e['tp1'])}</td>"
                 f"<td style=\"{td};color:{bull}\">{fp(e['tp2'])}</td></tr>")
    if rows:
        table = (f'<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;background:{panel}">'
                 f'<tr><th style="{th}">Quality</th><th style="{th}">Coin</th><th style="{th}">TF</th>'
                 f'<th style="{th}">Entry</th><th style="{th}">SL</th><th style="{th}">TP1</th><th style="{th}">TP2</th></tr>'
                 f'{rows}</table>')
    else:
        table = f'<div style="color:{muted};font-size:13px">No fresh buy flips.</div>'

    sells = [e for e in fresh if e["direction"] == "sell"]
    sells_html = ""
    if sells:
        sells_html = (f'<div style="margin-top:14px;font-size:12px;color:{muted}">Fresh sells: '
                      + ", ".join(f"{escape(e['symbol'])} ({TF_SHORT[e['tf']][0]})" for e in sells) + "</div>")

    return f"""<!DOCTYPE html><html><body style="margin:0;background:{bg};padding:20px;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:{text}">
<div style="max-width:720px;margin:0 auto">
<div style="font-size:18px;font-weight:700;color:{text}">Crypto Supertrend Combined Scanner</div>
<div style="font-size:12px;color:{muted};font-family:{mono};margin-bottom:14px">ATR({settings.ATR_PERIOD}) × {settings.MULTIPLIER} · Weekly + Daily + 4H · {escape(ctx['run_utc'])}</div>
{alerts}
<div style="font-size:12px;color:{muted};text-transform:uppercase;letter-spacing:0.04em;margin:8px 0">Fresh buy flips, ranked by quality (★ = 2+ timeframes)</div>
{table}{sells_html}
<div style="margin-top:16px;font-size:12px;color:{muted}">The full report (7-day flip history, watchlist, filters) is attached. Open the HTML file in a browser.</div>
</div></body></html>"""


# ------------------------------------------------------------------ index page (GitHub Pages)
def build_index(latest_html: str, report_names: list[str]) -> str:
    """
    reports/index.html = the newest report plus a picker for every report still kept.
    GitHub Pages serves reports/ as the site, so the site root always opens today's report.
    """
    names = sorted(report_names, reverse=True)
    options = "".join(
        f'<option value="{escape(n)}">{escape(n[len(settings.REPORT_PREFIX):-5])}'
        f'{" (latest, shown)" if i == 0 else ""}</option>'
        for i, n in enumerate(names)
    )
    bar = f"""
  <div class="archive-bar">
    <span class="archive-label">Report archive</span>
    <select onchange="if (this.value) window.location.href = this.value;">
      <option value="">Open an earlier report ({len(names)} kept)…</option>{options}
    </select>
    <span class="archive-note">Newest {settings.REPORT_RETENTION} reports are kept; older ones are deleted automatically.</span>
  </div>"""
    marker = '<div class="topbar">'
    start = latest_html.find(marker)
    end = latest_html.find("</div>\n  </div>", start)  # close of .params + .topbar
    if start == -1 or end == -1:
        return latest_html
    insert_at = end + len("</div>\n  </div>")
    return latest_html[:insert_at] + bar + latest_html[insert_at:]
