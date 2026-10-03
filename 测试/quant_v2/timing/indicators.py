"""
Quant V2 择时指标库（增强模块：timing/indicators）

基于 numpy 向量化的常用技术指标，供 Signals 打分器复用。
只做"计算"，不做判断；指标口径与策略层保持一致。

指标：
- SMA / EMA
- RSI
- MACD（DIF/DEA/HIST）
- ATR
- Bollinger Bands
- Volume Profile（POC/VAH/VAL）
- VWAP（累计）
- 20日均量
- Z-Score
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


def sma(values: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均，前 period-1 个为 NaN"""
    if period <= 0:
        return np.full_like(values, np.nan, dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    cs = np.cumsum(np.nan_to_num(values))
    for i in range(period - 1, len(values)):
        out[i] = (cs[i] - (cs[i - period] if i - period >= 0 else 0.0)) / period
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    out = np.full(len(values), np.nan)
    if len(values) == 0 or period <= 0:
        return out
    k = 2.0 / (period + 1)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI（Wilder 平滑）"""
    out = np.full(len(values), np.nan)
    if len(values) < 2:
        return out
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    alpha = 1.0 / period
    if period > len(gains):
        out[:] = np.nan
        return out
    ag = gains[:period].mean()
    al = losses[:period].mean()
    avg_gain = np.full(len(values), np.nan)
    avg_loss = np.full(len(values), np.nan)
    avg_gain[period] = ag
    avg_loss[period] = al
    for i in range(period + 1, len(values)):
        avg_gain[i] = ag = alpha * gains[i - 1] + (1 - alpha) * ag
        avg_loss[i] = al = alpha * losses[i - 1] + (1 - alpha) * al
    out = np.where(avg_loss > 0,
                   100 - 100 / (1 + avg_gain / np.maximum(avg_loss, 1e-10)),
                   np.where(avg_gain > 0, 100.0, 50.0))
    out[:period] = np.nan
    return out


@dataclass
class MACDResult:
    dif: np.ndarray
    dea: np.ndarray
    hist: np.ndarray


def macd(values: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult:
    """MACD：DIF=EMA(fast)-EMA(slow)；DEA=EMA(DIF,signal)；HIST=DIF-DEA"""
    dif = ema(values, fast) - ema(values, slow)
    dea = ema(np.nan_to_num(dif), signal)
    hist = dif - dea
    return MACDResult(dif, dea, hist)


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """TR = max(H-L, |H-prevC|, |L-prevC|)"""
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    return np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """ATR（Wilder 平滑）"""
    tr = true_range(high, low, close)
    out = np.full(len(tr), np.nan)
    if len(tr) < period:
        return out
    out[period - 1] = tr[:period].mean()
    alpha = 1.0 / period
    v = out[period - 1]
    for i in range(period, len(tr)):
        v = alpha * tr[i] + (1 - alpha) * v
        out[i] = v
    return out


@dataclass
class BollingerResult:
    mid: np.ndarray
    upper: np.ndarray
    lower: np.ndarray


def bollinger(values: np.ndarray, period: int = 20, num_std: float = 2.0) -> BollingerResult:
    """布林带：mid=SMA；band=num_std*std"""
    mid = sma(values, period)
    upper = np.full(len(values), np.nan)
    lower = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        sd = float(np.std(window))
        upper[i] = mid[i] + num_std * sd
        lower[i] = mid[i] - num_std * sd
    return BollingerResult(mid, upper, lower)


@dataclass
class VProfile:
    poc: float
    vah: float
    val: float
    total_volume: float


def volume_profile(high: np.ndarray, low: np.ndarray, volume: np.ndarray, bins: int = 40) -> Optional[VProfile]:
    """Volume Profile：把成交分配到价格桶，找 POC 与 70% 价值区（VAH/VAL）。"""
    if len(high) == 0:
        return None
    lo = float(np.nanmin(low))
    hi = float(np.nanmax(high))
    if hi <= lo or hi - lo < 1e-9:
        return None
    width = (hi - lo) / bins
    edges = np.linspace(lo, hi, bins + 1)
    counts = np.zeros(bins)
    mid = (high + low) / 2.0
    idx = np.clip(((mid - lo) / width).astype(int), 0, bins - 1)
    np.add.at(counts, idx, np.nan_to_num(volume))
    poc_bin = int(np.argmax(counts))
    poc = edges[poc_bin] + width / 2
    total = float(counts.sum())

    def value_range(target_frac: float = 0.70) -> tuple:
        order = np.argsort(counts)[::-1]
        acc = 0.0
        included = set()
        for b in order:
            included.add(int(b))
            acc += counts[b]
            if total > 0 and acc / total >= target_frac:
                break
        ib = min(included)
        ub = max(included)
        return edges[ib], edges[ub + 1]

    val_low, val_high = value_range(0.70)
    return VProfile(poc, val_high, val_low, total)


def vwap(typical: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """累计 VWAP（自起点累计）"""
    cum_v = np.cumsum(np.nan_to_num(volume))
    cum_pv = np.cumsum(np.nan_to_num(typical) * np.nan_to_num(volume))
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-10), np.nan)
    return out


def avg_volume(volume: np.ndarray, period: int = 20) -> np.ndarray:
    return sma(volume, period)


def zscore(values: np.ndarray, period: int = 20) -> np.ndarray:
    """滚动 Z-Score"""
    out = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        sd = float(np.std(window))
        mean = float(np.mean(window))
        out[i] = (values[i] - mean) / sd if sd > 1e-12 else 0.0
    return out
