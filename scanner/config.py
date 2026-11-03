"""Central configuration: every default and magic number lives here."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NSE_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
FALLBACK_CSV = ROOT / "data" / "nifty500.csv"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,*/*",
}
SUFFIX = ".NS"
IST = "Asia/Kolkata"
SESSION_CLOSE = (15, 30)          # NSE close, used to judge whether a candle is complete

CHUNK_SIZE = 100                  # tickers per yf.download call

# label -> (yfinance interval, history period, minutes per bar)
LTF_OPTIONS = {
    "5m": ("5m", "5d", 5),
    "15m": ("15m", "10d", 15),
    "30m": ("30m", "1mo", 30),
    "1h": ("60m", "2mo", 60),
}
# label -> (yfinance interval, history period). Weekly is resampled from daily.
HTF_OPTIONS = {"Daily": ("1d", "2y"), "Weekly": ("1d", "5y")}

TTL_UNIVERSE = 86_400             # seconds
TTL_INTRADAY = 180
TTL_HTF = 3_600

EXTRA_HALF_WIDTH = 0.005          # +/-0.5% band around 52W low / 200 EMA
MIN_ZONE_HALF_WIDTH = 0.003       # minimum half width of a swing-low zone
EMA_SPAN = 200
BARS_52W = {"Daily": 252, "Weekly": 52}
VOL_AVG_BARS = 20                 # daily bars used for the average-volume filter
CHART_BARS = {"Daily": 160, "Weekly": 120}


@dataclass(frozen=True)
class ScanParams:
    """All user-tunable scan settings, with defaults."""

    ltf: str = "15m"
    rsi_period: int = 14
    rsi_threshold: float = 30.0
    include_live: bool = False
    htf: str = "Daily"
    swing_lookback: int = 5
    cluster_tol: float = 1.5      # % band for merging swing lows into a zone
    min_touches: int = 2
    near_tol: float = 2.0         # % above zone still counted as "At Support"
    below_tol: float = 3.0        # max % below zone still counted as "Below Support"
    use_swing: bool = True
    use_52w: bool = True
    use_ema: bool = False
    min_price: float = 20.0
    min_volume: int = 100_000     # average daily volume
    max_stocks: int = 0           # 0 = scan the whole list
