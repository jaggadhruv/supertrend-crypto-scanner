"""
Central settings for the crypto Supertrend tool.

Everything tunable lives here so the logic files never hold magic numbers.
Supertrend parameters match the US equity tool (ATR 10, multiplier 2.5,
TradingView's default ATR method = Wilder's RMA).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
UNIVERSE_CSV = ROOT / "input" / "crypto_universe.csv"
PORTFOLIO_CSV = ROOT / "input" / "portfolio.csv"
TICKER_OVERRIDES_CSV = ROOT / "config" / "ticker_overrides.csv"
STATE_FILE = ROOT / "data" / "state.json"
FLIP_LOG_FILE = ROOT / "data" / "flip_log.json"
RESOLVED_TICKERS_FILE = ROOT / "data" / "resolved_tickers.json"
SIGNAL_LOG_CSV = ROOT / "data" / "signal_log.csv"
REPORTS_DIR = ROOT / "reports"

# --------------------------------------------------------------------------
# Supertrend
# --------------------------------------------------------------------------
ATR_PERIOD = 10
MULTIPLIER = 2.5

# --------------------------------------------------------------------------
# Timeframes
#   buy_only       : only BUY flips generate cards (4H per spec)
#   max_risk_pct   : stop distance above this = "wide stop" flag, 0 risk points
#   label          : human label used in the report
# --------------------------------------------------------------------------
TIMEFRAMES = {
    "1W": {"label": "Weekly", "buy_only": False, "max_risk_pct": 30.0},
    "1D": {"label": "Daily", "buy_only": False, "max_risk_pct": 15.0},
    "4H": {"label": "4-hour", "buy_only": True, "max_risk_pct": 8.0},
}
TIMEFRAME_ORDER = ["1W", "1D", "4H"]

# --------------------------------------------------------------------------
# Trade levels (BUY flips)
#   Entry = close of the flip bar
#   Stop  = Supertrend line on the flip bar (the lower band)
#   TP1/TP2 = entry + R multiples, where R = entry - stop
# --------------------------------------------------------------------------
TP_R_MULTIPLES = (2.0, 3.0)

# --------------------------------------------------------------------------
# Data fetching (yfinance only, no keys)
# --------------------------------------------------------------------------
DAILY_PERIOD = "3y"       # daily bars; weekly bars are resampled from these
HOURLY_PERIOD = "90d"     # 1h bars; 4H bars are resampled from these (Yahoo cap is 730d)
FETCH_DELAY_SEC = 0.3     # polite sequential fetching, same as the US tool
STALE_DAYS = 3            # a ticker whose latest daily bar is older than this is treated as dead/renamed

# --------------------------------------------------------------------------
# Universe hygiene
# --------------------------------------------------------------------------
# Stablecoins have no trend to follow. Explicit list plus an automatic check.
STABLECOINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDD", "USDS", "BUSD"}
STABLE_RANGE_PCT = 3.0    # 90-day (max-min)/mean below this % = treated as a stablecoin
MIN_DOLLAR_VOLUME = 5_000_000   # 30-day avg daily $ volume below this = "thin liquidity" penalty

# --------------------------------------------------------------------------
# Quality score (0-100) for BUY flips. See scoring.py for the full logic.
# --------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "trend_alignment": 30,
    "market_regime": 15,
    "volume": 15,
    "stop_distance": 15,
    "candle": 10,
    "momentum": 10,
    "cleanliness": 5,
}
THIN_LIQUIDITY_PENALTY = 10
CHOP_LOOKBACK_BARS = 30
VOLUME_LOOKBACK_BARS = 20
GRADES = [(75, "A"), (60, "B"), (45, "C"), (0, "D")]

# --------------------------------------------------------------------------
# Daily run, report and retention
#   The scan runs once a day (00:30 UTC, after the Daily candle closes).
#   4H buy flips from the whole previous 24 hours are picked up in that run.
# --------------------------------------------------------------------------
FRESH_4H_HOURS = 24          # 4H buy flips closed within this window count as "fresh"
RECENT_DAYS = 7              # "Recent Buy Flips" panel window
FLIP_LOG_KEEP_DAYS = 30      # flip_log.json prunes entries older than this
REPORT_PREFIX = "crypto_supertrend_"
REPORT_RETENTION = 30        # max report files kept in reports/; oldest deleted first

# --------------------------------------------------------------------------
# Email (Gmail SMTP). Summary in the body, full report attached.
# --------------------------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
