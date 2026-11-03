"""Technical indicators (vectorised)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI via exponential smoothing with alpha = 1/period."""
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    avg_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_down != 0, 100.0).where(avg_up.notna())


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weeks ending Friday."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return daily.resample("W-FRI").agg(agg).dropna(subset=["Close"])
