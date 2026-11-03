"""Support-zone detection and classification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from .config import EMA_SPAN, EXTRA_HALF_WIDTH, MIN_ZONE_HALF_WIDTH, ScanParams


@dataclass(frozen=True)
class Zone:
    """A support band. `touches` counts the swing lows merged into it."""
    low: float
    high: float
    level: float
    touches: int
    kind: str


class Hit(NamedTuple):
    zone: Zone
    dist_pct: float      # + above the zone, 0 inside it, - below it
    dist_abs: float      # same sign convention, in rupees
    status: str          # "At Support" | "Below Support"


def _cluster(prices: np.ndarray, tol: float) -> list[np.ndarray]:
    """Group sorted prices so each group spans at most `tol` (fraction) from its first price."""
    p = np.sort(prices)
    groups, start = [], 0
    for i in range(1, len(p) + 1):
        if i == len(p) or p[i] > p[start] * (1 + tol):
            groups.append(p[start:i])
            start = i
    return groups


def swing_zones(lows: np.ndarray, lookback: int, tol: float, min_touches: int) -> list[Zone]:
    """Swing lows (lowest within `lookback` bars each side), merged into zones."""
    n = len(lows)
    if n < 2 * lookback + 1:
        return []
    idx = argrelextrema(lows, np.less_equal, order=lookback)[0]
    idx = idx[(idx >= lookback) & (idx < n - lookback)]      # only confirmed pivots
    if idx.size == 0:
        return []
    idx = idx[np.insert(np.diff(idx) > 1, 0, True)]          # collapse flat-bottom duplicates
    zones = []
    for g in _cluster(lows[idx], tol):
        if len(g) < min_touches:
            continue
        level = float(g.mean())
        pad = level * MIN_ZONE_HALF_WIDTH
        zones.append(Zone(float(min(g.min(), level - pad)), float(max(g.max(), level + pad)),
                          level, len(g), "Swing low"))
    return zones


def _band(level: float, kind: str) -> Zone:
    return Zone(level * (1 - EXTRA_HALF_WIDTH), level * (1 + EXTRA_HALF_WIDTH), level, 1, kind)


def find_zones(df: pd.DataFrame, p: ScanParams, bars_52w: int) -> list[Zone]:
    """All support zones for one stock on the higher timeframe."""
    zones: list[Zone] = []
    if p.use_swing:
        zones += swing_zones(df["Low"].to_numpy(float), p.swing_lookback,
                             p.cluster_tol / 100, p.min_touches)
    if p.use_52w:
        prior = df["Low"].iloc[:-p.swing_lookback]            # exclude the newest bars so the level is a prior low
        if len(prior) >= 20:
            zones.append(_band(float(prior.tail(bars_52w).min()), "52W low"))
    if p.use_ema and len(df) >= EMA_SPAN:
        ema = df["Close"].ewm(span=EMA_SPAN, adjust=False).mean().iloc[-1]
        zones.append(_band(float(ema), "200 EMA"))
    return zones


def nearest_zone(zones: list[Zone], ltp: float, near_tol: float, below_tol: float) -> Optional[Hit]:
    """Closest zone the price is at (within `near_tol` % above) or just under (`below_tol` %)."""
    best: Optional[Hit] = None
    for z in zones:
        if ltp < z.low:
            pct, edge, status = (ltp - z.low) / z.low * 100, z.low, "Below Support"
            if -pct > below_tol:
                continue
        elif ltp <= z.high:
            pct, edge, status = 0.0, ltp, "At Support"
        else:
            pct, edge, status = (ltp - z.high) / z.high * 100, z.high, "At Support"
            if pct > near_tol:
                continue
        hit = Hit(z, pct, ltp - edge, status)
        if best is None or (abs(pct), -z.touches) < (abs(best.dist_pct), -best.zone.touches):
            best = hit
    return best
