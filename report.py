"""
HTML for both the email and reports/latest.html.

Email clients strip a lot of CSS, so layout uses tables and inline styles.
Sections (mirrors the US tool, plus the market header):
  header       BTC regime + share of coins in an uptrend per timeframe
  1. New buy flips, ranked by quality score (cards with Entry / SL / TP1 / TP2)
  2. Exit alerts (Weekly / Daily sell flips)
  3. List changes (CSV adds/removes, ticker replacements, failures, exclusions)
  4. All coins (full state, digest runs and the saved report)
  5. Run summary
"""
from __future__ import annotations

import math
from html import escape

import pandas as pd

import settings

# palette
PAPER = "#F4F5F2"
CARD = "#FFFFFF"
INK = "#1B2330"
MUTED = "#667085"
RULE = "#D9DDD6"
ACCENT = "#23408E"
UP = "#1D7A4A"
DOWN = "#A4332B"
GRADE_COLORS = {"A": "#1D7A4A", "B": "#56802C", "C": "#A36B12", "D": "#8A8F98"}

FONT = "'Segoe UI', -apple-system, Helvetica, Arial, sans-serif"
NUM = "font-variant-numeric: tabular-nums;"


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def fmt_price(p) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    if p >= 1000:
        return f"{p:,.0f}"
    if p >= 1:
        return f"{p:,.2f}" if p >= 10 else f"{p:.4f}"
    if p <= 0:
        return f"{p}"
    digits = -math.floor(math.log10(p)) + 3
    return f"{p:.{digits}f}"


def fmt_pct(v, signed=True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def fmt_time(iso_or_ts, tf: str) -> str:
    ts = pd.Timestamp(iso_or_ts)
    if tf == "4H":
        end = ts + pd.Timedelta(hours=4)
        return f"{ts:%a %d %b} {ts:%H:%M}-{end:%H:%M} UTC"
    if tf == "1W":
        return f"week of {ts:%d %b %Y}"
    return f"{ts:%a %d %b %Y}"


def trend_word(t) -> str:
    if t == 1:
        return f'<span style="color:{UP};font-weight:600">Up</span>'
    if t == -1:
        return f'<span style="color:{DOWN};font-weight:600">Down</span>'
    return f'<span style="color:{MUTED}">n/a</span>'


def section(title: str, body: str, note: str = "") -> str:
    note_html = f'<div style="color:{MUTED};font-size:13px;margin:2px 0 12px">{note}</div>' if note else ""
    return (
        f'<tr><td style="padding:28px 0 0">'
        f'<div style="font-size:19px;font-weight:600;color:{INK};border-bottom:2px solid {INK};'
        f'padding-bottom:6px;margin-bottom:8px">{escape(title)}</div>{note_html}{body}</td></tr>'
    )


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------
def buy_card(s: dict, position: int) -> str:
    g = s["grade"]
    gc = GRADE_COLORS[g]
    tf_label = settings.TIMEFRAMES[s["tf"]]["label"]

    def level(label, value, pct, color=INK):
        return (
            f'<td style="padding:8px 10px;border-left:1px solid {RULE};vertical-align:top">'
            f'<div style="font-size:12px;color:{MUTED}">{label}</div>'
            f'<div style="font-size:16px;font-weight:600;color:{color};{NUM}">{fmt_price(value)}</div>'
            f'<div style="font-size:12px;color:{MUTED};{NUM}">{pct}</div></td>'
        )

    levels = (
        '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;'
        f'border-top:1px solid {RULE};margin-top:10px"><tr>'
        + level("Entry", s["entry"], f"now {fmt_price(s['last_price'])} ({fmt_pct(s['move_since'])})")
        + level("Stop loss", s["stop"], f"-{s['risk_pct']:.1f}% risk", DOWN)
        + level(f"TP1 ({settings.TP_R_MULTIPLES[0]:g}R)", s["tp1"], fmt_pct(s["tp1_pct"]), UP)
        + level(f"TP2 ({settings.TP_R_MULTIPLES[1]:g}R)", s["tp2"], fmt_pct(s["tp2_pct"]), UP)
        + "</tr></table>"
    )

    p = s["parts"]
    w = settings.SCORE_WEIGHTS
    breakdown = ", ".join(
        f"{name} {p[key]:g}/{w[key]}"
        for key, name in [
            ("trend_alignment", "trend"), ("market_regime", "BTC"), ("volume", "volume"),
            ("stop_distance", "stop"), ("candle", "candle"), ("momentum", "RSI"), ("cleanliness", "clean"),
        ]
    )
    if s["penalty"]:
        breakdown += f", liquidity -{s['penalty']}"

    vol = "n/a" if math.isnan(s["vol_ratio"]) else f"{s['vol_ratio']:.1f}x avg"
    rsi_txt = "n/a" if math.isnan(s["rsi"]) else f"{s['rsi']:.0f}"
    facts = f"Volume {vol}. RSI {rsi_txt}. Trail the stop with the {tf_label} Supertrend line."

    status = s["status"]
    status_html = ""
    if status != "Live":
        color = DOWN if "stop" in status.lower() else ACCENT
        status_html = (f'<div style="margin-top:8px;font-size:13px;font-weight:600;color:{color}">'
                       f'{escape(status)}</div>')
    notes_html = ""
    if s["notes"]:
        notes_html = (f'<div style="margin-top:6px;font-size:13px;color:{DOWN}">'
                      f'{escape("; ".join(s["notes"]))}</div>')

    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;
  background:{CARD};border:1px solid {RULE};border-left:6px solid {gc};margin:0 0 12px">
  <tr>
    <td style="width:78px;padding:14px 0;text-align:center;vertical-align:top;border-right:1px solid {RULE}">
      <div style="font-size:40px;line-height:40px;font-weight:700;color:{gc}">{g}</div>
      <div style="font-size:13px;color:{MUTED};{NUM}">{s['score']:.0f}/100</div>
      <div style="font-size:12px;color:{MUTED};margin-top:4px">#{position}</div>
    </td>
    <td style="padding:12px 14px;vertical-align:top">
      <div style="font-size:18px;font-weight:600;color:{INK}">{escape(s['symbol'])}
        <span style="font-weight:400;color:{MUTED};font-size:14px">{escape(s['ticker'])}</span></div>
      <div style="font-size:14px;color:{INK}">{tf_label} buy flip, bar {fmt_time(s['bar_time'], s['tf'])}</div>
      {levels}
      <div style="margin-top:8px;font-size:13px;color:{INK}">{facts}</div>
      <div style="margin-top:4px;font-size:12px;color:{MUTED};{NUM}">Score: {breakdown}</div>
      {status_html}{notes_html}
    </td>
  </tr>
</table>"""


def exit_card(e: dict) -> str:
    tf_label = settings.TIMEFRAMES[e["tf"]]["label"]
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;
  background:{CARD};border:1px solid {RULE};border-left:6px solid {DOWN};margin:0 0 10px">
  <tr><td style="padding:10px 14px">
    <div style="font-size:16px;font-weight:600;color:{INK}">{escape(e['symbol'])}
      <span style="font-weight:400;color:{MUTED};font-size:14px">{tf_label} sell flip, bar {fmt_time(e['bar_time'], e['tf'])}</span></div>
    <div style="font-size:13px;color:{INK};margin-top:4px;{NUM}">
      Flip close {fmt_price(e['entry'])}, now {fmt_price(e['last_price'])} ({fmt_pct(e['move_since'])}).
      Supertrend resistance {fmt_price(e['st_line'])}. Exit or tighten any open long.</div>
  </td></tr>
</table>"""


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
def full_state_table(rows: list[dict]) -> str:
    th = f'style="text-align:left;padding:6px 8px;font-size:12px;color:{MUTED};font-weight:600;border-bottom:1px solid {INK}"'
    head = f"<tr><th {th}>#</th><th {th}>Coin</th><th {th}>Price</th>"
    for tf in settings.TIMEFRAME_ORDER:
        head += f"<th {th}>{settings.TIMEFRAMES[tf]['label']}</th>"
    head += "</tr>"
    body = []
    for i, r in enumerate(rows):
        bg = CARD if i % 2 == 0 else PAPER
        td = f'style="padding:5px 8px;font-size:13px;border-bottom:1px solid {RULE};{NUM}background:{bg}"'
        cells = [f"<td {td}>{r['rank']}</td>", f"<td {td}><b>{escape(r['symbol'])}</b></td>",
                 f"<td {td}>{fmt_price(r['price'])}</td>"]
        for tf in settings.TIMEFRAME_ORDER:
            t = r["tf"].get(tf)
            if not t:
                cells.append(f"<td {td}>n/a</td>")
                continue
            since = f"{t['bars_since']} bars" if t["bars_since"] is not None else "no flip yet"
            cells.append(
                f"<td {td}>{trend_word(t['trend'])} "
                f"<span style='color:{MUTED}'>{since}, {fmt_pct(t['dist_pct'])} vs line</span></td>"
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div style="overflow-x:auto"><table cellspacing="0" cellpadding="0" '
            f'style="width:100%;border-collapse:collapse;background:{CARD}">{head}{"".join(body)}</table></div>')


def changes_block(ch: dict) -> str:
    items = []
    if ch["added"]:
        items.append(f"Added to CSV: {', '.join(ch['added'])}")
    if ch["removed"]:
        items.append(f"Removed from CSV: {', '.join(ch['removed'])}")
    for sym, note in ch["replacements"]:
        items.append(f"{sym}: {note}")
    for sym, tkr, note in ch["failures"]:
        items.append(f"{sym} skipped: {note}")
    for sym, why in ch["excluded"]:
        items.append(f"{sym} excluded: {why}")
    if not items:
        return f'<div style="font-size:14px;color:{MUTED}">No changes since the last run.</div>'
    lis = "".join(f'<li style="margin:2px 0">{escape(x)}</li>' for x in items)
    return f'<ul style="margin:0;padding-left:18px;font-size:13px;color:{INK}">{lis}</ul>'


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------
def subject(ctx: dict) -> str:
    n = len(ctx["signals"])
    a = sum(1 for s in ctx["signals"] if s["grade"] == "A")
    ex = len(ctx["exits"])
    parts = []
    if n:
        parts.append(f"{n} buy flip{'s' if n != 1 else ''}" + (f" ({a} A-grade)" if a else ""))
    if ex:
        parts.append(f"{ex} exit alert{'s' if ex != 1 else ''}")
    if not parts:
        parts.append("daily digest, no new flips")
    return f"Crypto Supertrend | {', '.join(parts)} | {ctx['run_utc']}"


def build_html(ctx: dict, include_full_state: bool) -> str:
    btc = ctx["btc"]
    b = ctx["breadth"]
    btc_line = (
        f"BTC Daily trend {trend_word(btc.get('btc_trend_1D'))}, "
        + ("above" if btc.get("btc_above_sma200d") else "below" if btc.get("btc_above_sma200d") is False else "n/a vs")
        + " its 200-day average."
    )
    breadth_line = ". ".join(
        f"{settings.TIMEFRAMES[tf]['label']} uptrends: {b[tf]['up']} of {b[tf]['total']}"
        for tf in settings.TIMEFRAME_ORDER
    ) + "."

    header = f"""
<tr><td style="padding:24px 0 4px">
  <div style="font-size:26px;font-weight:700;color:{INK};letter-spacing:-0.3px">Crypto Supertrend</div>
  <div style="font-size:14px;color:{MUTED};{NUM}">{escape(ctx['run_utc'])}. Supertrend ATR {settings.ATR_PERIOD}, x{settings.MULTIPLIER}, closed bars only.</div>
  <div style="margin-top:12px;padding:12px 14px;background:{CARD};border:1px solid {RULE};font-size:14px;color:{INK};{NUM}">
    {btc_line}<br>{breadth_line}
  </div>
</td></tr>"""

    if ctx["signals"]:
        cards = "".join(buy_card(s, i + 1) for i, s in enumerate(ctx["signals"]))
    else:
        cards = f'<div style="font-size:14px;color:{MUTED}">No new buy flips on closed bars since the last run.</div>'
    sec_buys = section(
        "New buy flips, ranked",
        cards,
        "Weekly, Daily and 4-hour buy flips. Stop = Supertrend line on the flip bar. "
        "Grades: A 75+, B 60+, C 45+, D below.",
    )

    if ctx["exits"]:
        sec_exits = section("Exit alerts", "".join(exit_card(e) for e in ctx["exits"]),
                            "Weekly and Daily sell flips. 4-hour sell flips are not reported.")
    else:
        sec_exits = section("Exit alerts", f'<div style="font-size:14px;color:{MUTED}">No new Weekly or Daily sell flips.</div>')

    sec_changes = section("List changes", changes_block(ctx["changes"]))

    sec_full = ""
    if include_full_state:
        sec_full = section("All coins", full_state_table(ctx["full_rows"]),
                           "Bars since the last flip, and price distance from the active Supertrend line.")

    sm = ctx["summary"]
    first = " First run: only flips on the latest closed bar were considered." if ctx["first_run"] else ""
    sec_summary = section(
        "Run summary",
        f'<div style="font-size:13px;color:{INK};{NUM}">{sm["universe"]} coins in CSV, {sm["scanned"]} scanned, '
        f'{sm["excluded"]} excluded, {sm["failed"]} failed. {sm["buy_flips"]} buy flips, '
        f'{sm["exit_alerts"]} exit alerts.{first}</div>'
        f'<div style="font-size:12px;color:{MUTED};margin-top:8px">Signals are mechanical screens, not advice. '
        f'Yahoo crypto prices are aggregated across venues and can differ from a single exchange chart.</div>',
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crypto Supertrend {escape(ctx['run_utc'])}</title></head>
<body style="margin:0;padding:0;background:{PAPER};font-family:{FONT};color:{INK}">
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;background:{PAPER}"><tr><td align="center" style="padding:0 12px 32px">
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;max-width:760px;text-align:left;table-layout:fixed">
{header}{sec_buys}{sec_exits}{sec_changes}{sec_full}{sec_summary}
</table></td></tr></table></body></html>"""
