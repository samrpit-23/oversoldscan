"""Small helpers: chunking, timezone cleanup, candle completeness, market status."""
from __future__ import annotations

from typing import Iterator, Sequence

import pandas as pd

from .config import IST, SESSION_CLOSE


def chunked(items: Sequence, size: int) -> Iterator[Sequence]:
    """Yield successive slices of `items` with at most `size` elements."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def naive_ist(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert a tz-aware index to naive IST wall-clock time (what charts expect)."""
    if index.tz is not None:
        index = index.tz_convert(IST).tz_localize(None)
    return index


def clean_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Naive, de-duplicated, sorted daily frame with a Volume column."""
    out = df.copy()
    out.index = naive_ist(out.index).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out["Volume"] = out["Volume"].fillna(0) if "Volume" in out else 0
    return out


def drop_incomplete(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Drop the last intraday candle if it is still forming."""
    if df.empty:
        return df
    last = df.index[-1]
    last = last.tz_convert(IST) if last.tzinfo else last.tz_localize(IST)
    close = last.normalize() + pd.Timedelta(hours=SESSION_CLOSE[0], minutes=SESSION_CLOSE[1])
    end = min(last + pd.Timedelta(minutes=minutes), close)
    return df.iloc[:-1] if end > pd.Timestamp.now(tz=IST) else df


def market_status() -> tuple[bool, str]:
    """(is NSE open right now, formatted IST timestamp). Ignores exchange holidays."""
    now = pd.Timestamp.now(tz=IST)
    hm = (now.hour, now.minute)
    is_open = now.weekday() < 5 and (9, 15) <= hm <= SESSION_CLOSE
    return is_open, now.strftime("%d %b, %H:%M IST")
