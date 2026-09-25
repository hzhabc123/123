"""
Quant V2 风险管理模块
扩展风控规则：回撤控制、日亏损限制、连续亏损控制等
"""

from dataclasses import dataclass
from typing import Optional, List

from portfolio.portfolio import Portfolio
from signals.trading_signal import Signal


@dataclass
class RiskConfig:
    max_position_ratio: float = 0.3
    max_total_position_ratio: float = 0.9
    max_drawdown: float = 0.2
    drawdown_warning: float = 0.15
    max_daily_loss: float = 5000.0
    max_daily_loss_ratio: float = 0.02
    max_consecutive_losses: int = 5
    consecutive_loss_cool_down: int = 3
    max_single_trade_amount: float = 50000.0
    max_single_trade_ratio: float = 0.1
    max_leverage: float = 1.0


class RiskCheckResult:
    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason

    @staticmethod
    def success() -> "RiskCheckResult":
        return RiskCheckResult(passed=True)

    @staticmethod
    def fail(reason: str) -> "RiskCheckResult":
        return RiskCheckResult(passed=False, reason=reason)


class RiskManager:
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self.peak_equity: float = 0.0
        self.current_drawdown: float = 0.0
        self.daily_pnl: float = 0.0
        self.consecutive_losses: int = 0
        self.is_trading_suspended: bool = False
        self.trade_results: List[float] = []

    def validate_signal(self, signal: Signal, portfolio: Portfolio) -> RiskCheckResult:
        if self.is_trading_suspended:
            return RiskCheckResult.fail("交易已停止（触发风控规则）")

        current_equity = portfolio.account.equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        self.current_drawdown = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        if self.current_drawdown >= self.config.max_drawdown:
            self.is_trading_suspended = True
            return RiskCheckResult.fail(f"回撤超过阈值: {self.current_drawdown:.2%} >= {self.config.max_drawdown:.2%}")
        if self.current_drawdown >= self.config.drawdown_warning:
            print(f"[RISK WARNING] 回撤预警: {self.current_drawdown:.2%}")

        if self.daily_pnl < -self.config.max_daily_loss:
            self.is_trading_suspended = True
            return RiskCheckResult.fail(f"日亏损超限: {self.daily_pnl:.2f} < -{self.config.max_daily_loss:.2f}")

        daily_loss_ratio = abs(self.daily_pnl) / self.peak_equity if self.peak_equity > 0 else 0
        if daily_loss_ratio >= self.config.max_daily_loss_ratio and self.daily_pnl < 0:
            self.is_trading_suspended = True
            return RiskCheckResult.fail(f"日亏损比例超限: {daily_loss_ratio:.2%} >= {self.config.max_daily_loss_ratio:.2%}")

        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self.is_trading_suspended = True
            return RiskCheckResult.fail(f"连续亏损次数超限: {self.consecutive_losses} >= {self.config.max_consecutive_losses}")

        if signal.is_buy:
            trade_amount = signal.price * (signal.target_qty or 100)
            if trade_amount > self.config.max_single_trade_amount:
                return RiskCheckResult.fail(f"单笔交易金额超限: {trade_amount:.2f} > {self.config.max_single_trade_amount:.2f}")
            trade_ratio = trade_amount / current_equity if current_equity > 0 else 0
            if trade_ratio > self.config.max_single_trade_ratio:
                return RiskCheckResult.fail(f"单笔交易比例超限: {trade_ratio:.2%} > {self.config.max_single_trade_ratio:.2%}")
            position = portfolio.get_position(signal.symbol)
            if position:
                current_position_value = position.qty * signal.price
                new_position_value = current_position_value + trade_amount
                position_ratio = new_position_value / current_equity if current_equity > 0 else 0
                if position_ratio > self.config.max_position_ratio:
                    return RiskCheckResult.fail(f"单标的仓位超限: {position_ratio:.2%} > {self.config.max_position_ratio:.2%}")
            current_total_value = portfolio.calculate_market_value()
            new_total_value = current_total_value + trade_amount
            total_position_ratio = new_total_value / current_equity if current_equity > 0 else 0
            if total_position_ratio > self.config.max_total_position_ratio:
                return RiskCheckResult.fail(f"总仓位超限: {total_position_ratio:.2%} > {self.config.max_total_position_ratio:.2%}")
        return RiskCheckResult.success()

    def record_trade_result(self, pnl: float):
        self.trade_results.append(pnl)
        self.daily_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def reset_daily(self):
        self.daily_pnl = 0.0

    def reset_suspension(self):
        self.is_trading_suspended = False
        print("[RISK] 交易停止已解除")

    def summary(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("Risk Manager Summary")
        lines.append("=" * 60)
        lines.append(f"Peak Equity: {self.peak_equity:.2f}")
        lines.append(f"Current Drawdown: {self.current_drawdown:.2%}")
        lines.append(f"Daily PnL: {self.daily_pnl:.2f}")
        lines.append(f"Consecutive Losses: {self.consecutive_losses}")
        lines.append(f"Trading Suspended: {self.is_trading_suspended}")
        lines.append(f"Total Trades: {len(self.trade_results)}")
        if self.trade_results:
            win_count = sum(1 for pnl in self.trade_results if pnl > 0)
            lines.append(f"Win Rate: {win_count / len(self.trade_results):.2%}")
        lines.append("=" * 60)
        return "\n".join(lines)
