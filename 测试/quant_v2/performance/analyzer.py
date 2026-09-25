"""
Quant V2 绩效分析器

基于净值曲线与成交记录计算完整绩效指标：
- 收益：总收益、年化收益
- 风险：年化波动、最大回撤、回撤持续
- 风险调整：夏普、索提诺、卡玛
- 交易统计：胜率、盈亏比、换手
- 基准对比：alpha、beta、信息比率
"""

from dataclasses import dataclass
from typing import List, Optional


TRADING_DAYS_PER_YEAR = 252


@dataclass
class PerformanceMetrics:
    total_return: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    turnover: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0


class PerformanceAnalyzer:
    def __init__(self, equity_curve: List[dict], trades: list,
                 benchmark_curve: Optional[List[dict]] = None,
                 risk_free_rate: float = 0.02):
        self.equity_curve = equity_curve
        self.trades = trades
        self.benchmark_curve = benchmark_curve
        self.risk_free_rate = risk_free_rate
        self._metrics: Optional[PerformanceMetrics] = None

    def compute(self) -> PerformanceMetrics:
        if self._metrics is not None:
            return self._metrics

        equity = [e["equity"] for e in self.equity_curve]
        if not equity:
            self._metrics = PerformanceMetrics()
            return self._metrics

        initial = equity[0]
        final = equity[-1]
        total_return = (final / initial - 1.0) if initial else 0.0

        daily_returns = []
        for i in range(1, len(equity)):
            prev = equity[i - 1]
            daily_returns.append(equity[i] / prev - 1.0 if prev != 0 else 0.0)

        n = len(daily_returns)
        annual_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / max(n, 1)) - 1 if total_return > -1 else -1.0

        annual_vol = self._calc_annual_volatility(daily_returns)
        max_dd, dd_duration = self._calc_max_drawdown(equity)

        rf_daily = self.risk_free_rate / TRADING_DAYS_PER_YEAR
        sharpe = self._calc_sharpe(daily_returns, rf_daily, annual_vol)
        sortino = self._calc_sortino(daily_returns, rf_daily)
        calmar = annual_return / abs(max_dd) if max_dd > 0 else 0.0

        wins, plr, n_pairs = self._calc_trade_stats(self.trades)
        win_rate = wins / n_pairs if n_pairs else 0.0
        turnover = self._calc_turnover(self.trades, equity)

        benchmark_return, alpha, beta, ir = self._calc_benchmark_metrics(daily_returns, self.benchmark_curve)

        self._metrics = PerformanceMetrics(
            total_return=total_return, annual_return=annual_return,
            annual_volatility=annual_vol, sharpe_ratio=sharpe,
            sortino_ratio=sortino, calmar_ratio=calmar,
            max_drawdown=max_dd, max_drawdown_duration=dd_duration,
            win_rate=win_rate, profit_loss_ratio=plr, total_trades=len(self.trades),
            turnover=turnover, benchmark_return=benchmark_return,
            alpha=alpha, beta=beta, information_ratio=ir,
        )
        return self._metrics

    def _calc_annual_volatility(self, daily_returns):
        if len(daily_returns) < 2:
            return 0.0
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        return variance ** 0.5 * (TRADING_DAYS_PER_YEAR ** 0.5)

    def _calc_max_drawdown(self, equity):
        peak = equity[0]
        max_dd = 0.0
        cur_dur = 0
        max_dur = 0
        for e in equity:
            if e > peak:
                peak = e
                cur_dur = 0
            else:
                cur_dur += 1
                dd = (peak - e) / peak if peak else 0.0
                if dd > max_dd:
                    max_dd = dd
                    max_dur = cur_dur
        return max_dd, max_dur

    def _calc_sharpe(self, daily_returns, rf_daily, annual_vol):
        excess = [r - rf_daily for r in daily_returns]
        if len(excess) < 2:
            return 0.0
        mean_ex = sum(excess) / len(excess)
        if mean_ex <= 0:
            return 0.0
        vol = self._std(daily_returns) * (TRADING_DAYS_PER_YEAR ** 0.5)
        if vol == 0:
            return 0.0
        return (mean_ex * TRADING_DAYS_PER_YEAR) / vol

    def _calc_sortino(self, daily_returns, rf_daily):
        excess = [r - rf_daily for r in daily_returns]
        mean_ex = sum(excess) / len(excess) if excess else 0.0
        if mean_ex <= 0:
            return 0.0
        downside = [r - rf_daily for r in daily_returns if (r - rf_daily) < 0]
        if not downside:
            return 0.0
        downside_dev = (sum(d * d for d in downside) / len(downside)) ** 0.5
        if downside_dev == 0:
            return 0.0
        return (mean_ex * TRADING_DAYS_PER_YEAR) / (downside_dev * (TRADING_DAYS_PER_YEAR ** 0.5))

    def _calc_trade_stats(self, trades):
        buy_queue = []
        trade_pnls = []
        for t in trades:
            if t.side.name == "BUY":
                buy_queue.append((t.price, t.qty))
            else:
                remaining = t.qty
                while remaining > 0 and buy_queue:
                    buy_price, buy_qty = buy_queue[0]
                    matched = min(buy_qty, remaining)
                    pnl = (t.price - buy_price) * matched
                    trade_pnls.append(pnl)
                    remaining -= matched
                    if matched >= buy_qty:
                        buy_queue.pop(0)
                    else:
                        buy_queue[0] = (buy_price, buy_qty - matched)
        if trade_pnls:
            wins = sum(1 for p in trade_pnls if p > 0)
            gains = [p for p in trade_pnls if p > 0]
            losses = [-p for p in trade_pnls if p < 0]
            avg_gain = sum(gains) / len(gains) if gains else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            plr = avg_gain / avg_loss if avg_loss > 0 else (float("inf") if avg_gain > 0 else 0.0)
            plr = plr if plr not in (float("inf"), -float("inf")) else 0.0
            return wins, plr, len(trade_pnls)
        return 0, 0.0, 0

    def _calc_turnover(self, trades, equity):
        if not trades or not equity:
            return 0.0
        total_turnover = sum(abs(t.price * t.qty) for t in trades)
        avg_equity = sum(equity) / len(equity)
        return total_turnover / avg_equity if avg_equity else 0.0

    def _calc_benchmark_metrics(self, daily_returns, benchmark_curve):
        if not benchmark_curve or not daily_returns:
            return 0.0, 0.0, 0.0, 0.0
        bench = [b["equity"] for b in benchmark_curve]
        bench_returns = []
        for i in range(1, len(bench)):
            bench_returns.append(bench[i] / bench[i-1] - 1.0 if bench[i-1] != 0 else 0.0)
        n = min(len(daily_returns), len(bench_returns))
        if n == 0:
            return 0.0, 0.0, 0.0, 0.0
        strat = daily_returns[:n]
        bench = bench_returns[:n]
        benchmark_return = bench[-1]
        mean_b = sum(bench) / n
        mean_s = sum(strat) / n
        cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(strat, bench)) / n
        var_b = sum((b - mean_b) ** 2 for b in bench) / n
        beta = cov / var_b if var_b != 0 else 0.0
        rf_daily = self.risk_free_rate / TRADING_DAYS_PER_YEAR
        excess_strat = mean_s - rf_daily
        alpha = (excess_strat - beta * (mean_b - rf_daily)) * TRADING_DAYS_PER_YEAR
        active = [s - b for s, b in zip(strat, bench)]
        mean_active = sum(active) / n
        vol_active = self._std(active)
        ir = (mean_active * TRADING_DAYS_PER_YEAR) / (vol_active * (TRADING_DAYS_PER_YEAR ** 0.5)) if vol_active > 0 else 0.0
        return benchmark_return, alpha, beta, ir

    def _std(self, values):
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return (sum((x - mean) ** 2 for x in values) / (len(values) - 1)) ** 0.5

    def to_dataframe(self):
        import pandas as pd
        rows = []
        peak = self.equity_curve[0]["equity"] if self.equity_curve else 0
        prev = None
        for e in self.equity_curve:
            eq = e["equity"]
            dr = eq / prev - 1.0 if (prev is not None and prev != 0) else 0.0
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak else 0.0
            rows.append({"datetime": e["datetime"], "equity": eq, "daily_return": dr, "drawdown": -dd})
            prev = eq
        return pd.DataFrame(rows)

    def metrics_to_dict(self) -> dict:
        m = self.compute()
        return {"total_return": m.total_return, "annual_return": m.annual_return,
                "annual_volatility": m.annual_volatility, "sharpe_ratio": m.sharpe_ratio,
                "sortino_ratio": m.sortino_ratio, "calmar_ratio": m.calmar_ratio,
                "max_drawdown": m.max_drawdown, "max_drawdown_duration": m.max_drawdown_duration,
                "win_rate": m.win_rate, "profit_loss_ratio": m.profit_loss_ratio,
                "total_trades": m.total_trades, "turnover": m.turnover,
                "benchmark_return": m.benchmark_return, "alpha": m.alpha,
                "beta": m.beta, "information_ratio": m.information_ratio}

    def summary(self) -> str:
        m = self.compute()
        lines = []
        lines.append("=" * 60)
        lines.append("Performance Metrics Summary")
        lines.append("=" * 60)
        lines.append("  --- 收益指标 ---")
        lines.append(f"  总收益率:          {m.total_return:.2%}")
        lines.append(f"  年化收益率:        {m.annual_return:.2%}")
        lines.append(f"  基准收益率:        {m.benchmark_return:.2%}")
        lines.append("  --- 风险指标 ---")
        lines.append(f"  年化波动率:        {m.annual_volatility:.2%}")
        lines.append(f"  最大回撤:          {m.max_drawdown:.2%}")
        lines.append(f"  回撤持续天数:      {m.max_drawdown_duration}")
        lines.append("  --- 风险调整收益 ---")
        lines.append(f"  夏普比率:          {m.sharpe_ratio:.4f}")
        lines.append(f"  索提诺比率:        {m.sortino_ratio:.4f}")
        lines.append(f"  卡玛比率:          {m.calmar_ratio:.4f}")
        lines.append("  --- 交易统计 ---")
        lines.append(f"  总交易数:          {m.total_trades}")
        lines.append(f"  胜率:              {m.win_rate:.2%}")
        lines.append(f"  盈亏比:            {m.profit_loss_ratio:.4f}")
        lines.append(f"  换手率:            {m.turnover:.4f}")
        lines.append("  --- 基准对比 ---")
        lines.append(f"  Alpha:             {m.alpha:.4f}")
        lines.append(f"  Beta:              {m.beta:.4f}")
        lines.append(f"  信息比率:          {m.information_ratio:.4f}")
        lines.append("=" * 60)
        return "\n".join(lines)
