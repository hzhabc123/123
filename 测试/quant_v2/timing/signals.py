"""
Quant V2 择时信号打分器（增强模块：timing/signals）

把方法论文档的"十三类信号源"固化为可计算的 0/1 特征。
每一类信号独立打分后返回，Scorer 再做共振聚合。

输出结构：每个信号项 {name, hit(0/1), detail(str)}。
所有计算只用真实历史数据，杜绝前视。

信号类别（对应文档）：
  1. structure   结构：前低/前高、W底/M头简化、支撑阻力
  2. momentum    动量：RSI背离(简化)、MACD金叉/死叉
  3. volume      量能：地量后放量 / 天量滞涨
  4. volatility  波动：布林下/上轨、ATR 收/扩
  5. emotion     情绪：恐慌/狂热（用指标代理，真实情绪数据由调用方注入）
  6. cross       跨市场：由调用方注入（股债汇等共振）
  7. fundamental 基本面：由调用方注入（估值分位/股息）
  8. options     期权/衍生品：由调用方注入（PCR/资金费率）
  9. timing      时间/事件：由调用方注入（财报/节气/到期日）
  10. confirm     确认：收盘突破/跌破 + 回踩
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from timing import indicators as ind


@dataclass
class SignalItem:
    name: str
    hit: int
    detail: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "hit": self.hit, "detail": self.detail}


@dataclass
class SignalInput:
    closes: np.ndarray
    highs: Optional[np.ndarray] = None
    lows: Optional[np.ndarray] = None
    volumes: Optional[np.ndarray] = None
    atr_arr: Optional[np.ndarray] = None
    rsi_arr: Optional[np.ndarray] = None
    macd: Optional[ind.MACDResult] = None
    boll: Optional[ind.BollingerResult] = None

    def validate(self) -> bool:
        return len(self.closes) >= 2


# ---------------- 1. 结构 ----------------

def structure_signal(inp: SignalInput, lookback: int = 60) -> List[SignalItem]:
    items: List[SignalItem] = []
    closes = inp.closes
    if len(closes) < 2 or not inp.validate():
        return [SignalItem("结构", 0, "数据不足")]
    price = closes[-1]
    win = closes[-lookback:-1] if len(closes) - 1 >= 1 else np.array([price])
    if len(win) == 0:
        win = np.array([price])
    prev_high = float(np.max(win))
    prev_low = float(np.min(win))
    d_low = (price - prev_low) / price if price > 0 else 0.0
    d_high = (prev_high - price) / price if price > 0 else 0.0
    hit_low = d_low <= 0.03
    hit_high = d_high <= 0.03
    if hit_low:
        items.append(SignalItem("结构-接近前低", 1, f"距前低{prev_low:.2f} 仅{d_low*100:.1f}%"))
    elif hit_high:
        items.append(SignalItem("结构-接近前高", 1, f"距前高{prev_high:.2f} 仅{d_high*100:.1f}%"))
    else:
        items.append(SignalItem("结构", 0, f"处于前低{prev_low:.2f}与前高{prev_high:.2f}之间"))
    return items


# ---------------- 2. 动量 ----------------

def momentum_signal(inp: SignalInput) -> List[SignalItem]:
    items: List[SignalItem] = []
    closes = inp.closes
    if len(closes) < 30:
        return [SignalItem("动量", 0, "数据不足")]
    _m = ind.macd(closes) if inp.macd is None else inp.macd
    dif, dea, hist = _m.dif, _m.dea, _m.hist
    r = inp.rsi_arr if inp.rsi_arr is not None else ind.rsi(closes, 14)
    cross_up = dif[-1] > dea[-1] and dif[-2] <= dea[-2]
    cross_dn = dif[-1] < dea[-1] and dif[-2] >= dea[-2]
    r_now = r[-1] if len(r) and not np.isnan(r[-1]) else 50.0
    if cross_up:
        items.append(SignalItem("动量-MACD金叉", 1, "DIF上穿DEA"))
    elif r_now < 30:
        items.append(SignalItem("动量-RSI超卖", 1, f"RSI={r_now:.1f}<30"))
    elif cross_dn:
        items.append(SignalItem("动量-MACD死叉", 1, "DIF下穿DEA"))
    elif r_now > 70:
        items.append(SignalItem("动量-RSI超买", 1, f"RSI={r_now:.1f}>70"))
    else:
        items.append(SignalItem("动量", 0, f"MACD无交叉 RSI={r_now:.1f}"))
    return items


# ---------------- 3. 量能 ----------------

def volume_signal(inp: SignalInput) -> List[SignalItem]:
    items: List[SignalItem] = []
    if inp.volumes is None or len(inp.volumes) < 25:
        return [SignalItem("量能", 0, "无量数据")]
    closes = inp.closes
    vols = inp.volumes
    v20 = ind.avg_volume(vols, 20)
    v_now = vols[-1]
    v_avg = v20[-2] if not np.isnan(v20[-2]) else (v20[-1] if not np.isnan(v20[-1]) else np.mean(vols[-20:]))
    r = closes[-1] / closes[-2] - 1 if closes[-2] else 0.0
    recent_vol = vols[-6:-1]
    is_landmark_low = recent_vol.max() <= v_avg * 0.8 if recent_vol.max() > 0 else False
    if is_landmark_low and v_now > 1.5 * v_avg and r > 0:
        items.append(SignalItem("量能-地量后放量阳线", 1, f"v={v_now:.0f}>{1.5*v_avg:.0f} 涨{r*100:.2f}%"))
    elif v_now >= 1.8 * v_avg and abs(r) < 0.005:
        items.append(SignalItem("量能-天量滞涨", 1, f"天量{v_now:.0f}但仅{r*100:.2f}%"))
    else:
        items.append(SignalItem("量能", 0, f"量比{v_now/v_avg:.2f} 涨跌{r*100:.2f}%"))
    return items


# ---------------- 4. 波动 ----------------

def volatility_signal(inp: SignalInput, atr_period: int = 14, num_std: float = 2.0) -> List[SignalItem]:
    items: List[SignalItem] = []
    if inp.highs is None or inp.lows is None or len(inp.closes) < 22:
        return [SignalItem("波动", 0, "缺高低价")]
    atr_a = inp.atr_arr if inp.atr_arr is not None else ind.atr(inp.highs, inp.lows, inp.closes, atr_period)
    boll = inp.boll if inp.boll is not None else ind.bollinger(inp.closes, 20, num_std)
    price = inp.closes[-1]
    lo, up = boll.lower[-1], boll.upper[-1]
    if np.isnan(lo): lo = price
    if np.isnan(up): up = price
    prev_lo, prev_up = boll.lower[-2], boll.upper[-2]
    touched_low = prev_lo < inp.lows[-2]
    touched_up = prev_up > inp.highs[-2]
    if touched_low and price > lo:
        items.append(SignalItem("波动-布林下轨收回", 1, "触下轨后收回"))
    elif price <= lo:
        items.append(SignalItem("波动-触及布林下轨", 1, "还在下轨附近"))
    elif touched_up and price < up:
        items.append(SignalItem("波动-布林上轨回落", 1, "触上轨后回落"))
    elif price >= up:
        items.append(SignalItem("波动-触及布林上轨", 1, "还在上轨附近"))
    prev_atr = atr_a[-11] if len(atr_a) > 11 and not np.isnan(atr_a[-11]) else atr_a[-1]
    if prev_atr > 0:
        shrink = (atr_a[-1] - prev_atr) / prev_atr
        if shrink < -0.3:
            items.append(SignalItem("波动-ATR收缩", 1, f"ATR收缩{shrink*100:.0f}%"))
    if not any("布林" in i.name for i in items):
        items.append(SignalItem("波动-布林", 0, "未触及边界"))
    return items


# ---------------- 5. 情绪（代理） ----------------

def emotion_signal(inp: SignalInput, fear_greed: Optional[float] = None) -> List[SignalItem]:
    items: List[SignalItem] = []
    if fear_greed is not None:
        if fear_greed <= 20:
            items.append(SignalItem("情绪-极度恐惧", 1, f"恐惧贪婪={fear_greed}"))
        elif fear_greed >= 80:
            items.append(SignalItem("情绪-极度贪婪", 1, f"恐惧贪婪={fear_greed}"))
        else:
            items.append(SignalItem("情绪", 0, f"恐惧贪婪={fear_greed}"))
        return items
    r = inp.rsi_arr if inp.rsi_arr is not None else ind.rsi(inp.closes, 14)
    r_now = r[-1] if len(r) and not np.isnan(r[-1]) else 50.0
    if r_now < 30:
        items.append(SignalItem("情绪-RSI恐慌(代理)", 1, f"RSI={r_now:.1f}"))
    elif r_now > 70:
        items.append(SignalItem("情绪-RSI狂热(代理)", 1, f"RSI={r_now:.1f}"))
    else:
        items.append(SignalItem("情绪", 0, f"RSI={r_now:.1f}中性"))
    return items


# ---------------- 9. 确认 ----------------

def confirm_signal(inp: SignalInput, breakout_level: Optional[float] = None) -> List[SignalItem]:
    items: List[SignalItem] = []
    if len(inp.closes) < 22:
        return [SignalItem("确认", 0, "数据不足")]
    closes = inp.closes
    price = closes[-1]
    h = float(np.max(closes[-21:-1] + ([closes[-2]] if len(closes) > 1 else []))) if len(closes) > 1 else price
    l = float(np.min(closes[-21:-1] + ([closes[-2]] if len(closes) > 1 else []))) if len(closes) > 1 else price
    if price > h:
        items.append(SignalItem("确认-收盘创新高", 1, f"收盘{price:.2f}突破前高{h:.2f}"))
    elif price < l:
        items.append(SignalItem("确认-收盘创新低", 1, f"收盘{price:.2f}跌破前低{l:.2f}"))
    else:
        items.append(SignalItem("确认", 0, f"在{min(h,l):.2f}-{max(h,l):.2f}内"))
    return items


# ---------------- 聚合入口 ----------------

def build_signal_items(inp: SignalInput, fear_greed: Optional[float] = None,
                       breakout_level: Optional[float] = None,
                       externals: Optional[Dict[str, dict]] = None) -> List[SignalItem]:
    """
    汇总全部可计算的信号项。
    externals: 调用方提供的第三方信号（真实情绪/跨市场/基本面/期权/时间），每项 {"hit":0/1,"detail":str}。
    """
    items: List[SignalItem] = []
    items.extend(structure_signal(inp))
    items.extend(momentum_signal(inp))
    items.extend(volume_signal(inp))
    items.extend(volatility_signal(inp))
    items.extend(emotion_signal(inp, fear_greed))
    items.extend(confirm_signal(inp, breakout_level))
    for cat, meta in (externals or {}).items():
        name = meta.get("name", cat)
        hit = 1 if meta.get("hit") else 0
        items.append(SignalItem(name, hit, meta.get("detail", "")))
    return items
