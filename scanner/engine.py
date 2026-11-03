"""Scan pipeline. Order matters for speed: cheap RSI filter first, support only for survivors."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .config import BARS_52W, CHUNK_SIZE, HTF_OPTIONS, LTF_OPTIONS, SUFFIX, VOL_AVG_BARS, ScanParams
from .data import fetch_htf, fetch_ltf
from .indicators import rsi, to_weekly
from .support import Zone, find_zones, nearest_zone
from .utils import chunked, clean_daily, drop_incomplete, naive_ist

Progress = Callable[[float, str], None]


@dataclass
class ScanResult:
    params: ScanParams
    table: pd.DataFrame
    stats: dict
    htf: dict[str, pd.DataFrame] = field(default_factory=dict)       # keyed by symbol
    rsi_ltf: dict[str, pd.Series] = field(default_factory=dict)
    zones: dict[str, list[Zone]] = field(default_factory=dict)
    nearest: dict[str, Zone] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    finished_at: str = ""


def run_scan(p: ScanParams, universe: pd.DataFrame, progress: Progress) -> ScanResult:
    t0 = time.time()
    uni = universe.head(p.max_stocks) if p.max_stocks else universe
    names = dict(zip(uni["Symbol"], uni["Company Name"]))
    tickers = [s + SUFFIX for s in uni["Symbol"]]
    interval, period, minutes = LTF_OPTIONS[p.ltf]

    # 1) Lower timeframe download, in batches
    ltf: dict[str, pd.DataFrame] = {}
    batches = list(chunked(tickers, CHUNK_SIZE))
    for i, b in enumerate(batches):
        progress(0.70 * i / len(batches), f"Downloading {p.ltf} candles, batch {i + 1} of {len(batches)}")
        ltf.update(fetch_ltf(tuple(b), interval, period))
    skipped = [t[:-len(SUFFIX)] for t in tickers if t not in ltf]

    # 2) RSI filter (cheap, runs on everything)
    progress(0.72, "Checking RSI on the lower timeframe")
    cands: dict[str, tuple[float, float, pd.Series]] = {}
    for t, df in ltf.items():
        ltp = float(df["Close"].iloc[-1])
        calc = df if p.include_live else drop_incomplete(df, minutes)
        if ltp < p.min_price or len(calc) < p.rsi_period * 2:
            continue
        r = rsi(calc["Close"], p.rsi_period)
        if pd.notna(r.iloc[-1]) and r.iloc[-1] < p.rsi_threshold:
            r = r.dropna().tail(300)
            r.index = naive_ist(r.index)
            cands[t] = (ltp, float(r.iloc[-1]), r)

    # 3) Daily download for survivors only
    daily: dict[str, pd.DataFrame] = {}
    keys = list(cands)
    hb = list(chunked(keys, CHUNK_SIZE))
    for i, b in enumerate(hb):
        progress(0.75 + 0.15 * i / max(len(hb), 1), f"Loading {p.htf.lower()} history for {len(keys)} oversold stocks")
        daily.update(fetch_htf(tuple(b), *HTF_OPTIONS[p.htf]))

    # 4) Support zones and classification
    rows, res = [], ScanResult(p, pd.DataFrame(), {}, skipped=skipped)
    for i, t in enumerate(keys):
        progress(0.90 + 0.09 * i / max(len(keys), 1), "Finding support zones")
        d = daily.get(t)
        if d is None or len(d) < 60:
            continue
        d = clean_daily(d)
        avg_vol = float(d["Volume"].tail(VOL_AVG_BARS).mean())
        if avg_vol < p.min_volume:
            continue
        h = to_weekly(d) if p.htf == "Weekly" else d
        zones = find_zones(h, p, BARS_52W[p.htf])
        ltp, r_val, r_series = cands[t]
        hit = nearest_zone(zones, ltp, p.near_tol, p.below_tol)
        if hit is None:
            continue
        sym = t[:-len(SUFFIX)]
        z = hit.zone
        h_rsi = rsi(h["Close"], p.rsi_period).iloc[-1]
        rows.append({
            "Symbol": sym, "Company": names.get(sym, sym), "LTP": round(ltp, 2),
            "LTF RSI": round(r_val, 1), "HTF RSI": None if pd.isna(h_rsi) else round(float(h_rsi), 1),
            "Support Type": z.kind, "Support Level": round(z.level, 2),
            "Zone Low": round(z.low, 2), "Zone High": round(z.high, 2), "Touches": z.touches,
            "Distance %": round(hit.dist_pct, 2), "Distance Rs": round(hit.dist_abs, 2),
            "Status": hit.status, "Avg Volume": int(avg_vol),
        })
        res.htf[sym], res.rsi_ltf[sym] = h, r_series
        res.zones[sym], res.nearest[sym] = zones, z

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.reindex(table["Distance %"].abs().sort_values().index).reset_index(drop=True)
    res.table = table
    res.stats = {
        "scanned": len(ltf), "oversold": len(cands), "matches": len(table),
        "at": int((table["Status"] == "At Support").sum()) if len(table) else 0,
        "below": int((table["Status"] == "Below Support").sum()) if len(table) else 0,
        "seconds": time.time() - t0,
    }
    res.finished_at = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%H:%M:%S IST")
    progress(1.0, "Done")
    return res
