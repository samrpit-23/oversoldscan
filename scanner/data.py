"""Data access: Nifty 500 list and cached yfinance downloads."""
from __future__ import annotations

import io
import time

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from .config import FALLBACK_CSV, HTTP_HEADERS, NSE_URL, TTL_HTF, TTL_INTRADAY, TTL_UNIVERSE

OHLCV = ("Open", "High", "Low", "Close", "Volume")


@st.cache_data(ttl=TTL_UNIVERSE, show_spinner=False)
def load_universe() -> tuple[pd.DataFrame, str]:
    """Nifty 500 constituents. Tries NSE first, then the committed data/nifty500.csv."""
    try:
        r = requests.get(NSE_URL, headers=HTTP_HEADERS, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        if "Symbol" not in df.columns:
            raise ValueError("unexpected NSE response")
        source = "NSE live list"
    except Exception:
        df = pd.read_csv(FALLBACK_CSV)
        df.columns = [c.strip() for c in df.columns]
        source = "fallback file"
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    if "Company Name" not in df.columns:
        df["Company Name"] = df["Symbol"]
    return df.drop_duplicates("Symbol").reset_index(drop=True), source


def _split(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Turn one multi-ticker download into {ticker: OHLCV frame}."""
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    multi = isinstance(raw.columns, pd.MultiIndex)
    for t in tickers:
        try:
            part = raw[t] if multi else raw
        except KeyError:
            continue
        part = part[[c for c in OHLCV if c in part.columns]].dropna(how="all")
        if "Close" in part and part["Close"].notna().any():
            out[t] = part.dropna(subset=["Close"])
        if not multi:
            break
    return out


def _download(tickers: tuple[str, ...], interval: str, period: str) -> dict[str, pd.DataFrame]:
    """Batch download with one retry for tickers that came back empty."""
    result: dict[str, pd.DataFrame] = {}
    todo = list(tickers)
    for attempt in range(2):
        if not todo:
            break
        try:
            raw = yf.download(tickers=todo, interval=interval, period=period, group_by="ticker",
                              auto_adjust=True, threads=True, progress=False)
            result.update(_split(raw, todo))
        except Exception:
            time.sleep(1.5)
        todo = [t for t in todo if t not in result]
    return result


@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_ltf(tickers: tuple[str, ...], interval: str, period: str) -> dict[str, pd.DataFrame]:
    """Lower-timeframe candles, cached for a few minutes."""
    return _download(tickers, interval, period)


@st.cache_data(ttl=TTL_HTF, show_spinner=False)
def fetch_htf(tickers: tuple[str, ...], interval: str, period: str) -> dict[str, pd.DataFrame]:
    """Daily candles for support detection, cached for an hour."""
    return _download(tickers, interval, period)
