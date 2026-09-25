"""
Quant V2 组合管理
管理多标的持仓、账户、订单、成交
"""

from datetime import datetime
from itertools import count
from typing import Dict, List, Optional

from portfolio.account import Account
from portfolio.position import Position
from portfolio.order import Order
from portfolio.trade import Trade
from core.enums import Side


_ledger_counter = count(1)


class Portfolio:

    def __init__(self, initial_cash: float = 100000.0):
        self.account = Account(initial_cash=initial_cash, cash=initial_cash)
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self._record_initial(initial_cash)

    def _record_initial(self, initial_cash: float):
        from portfolio.ledger import LedgerEntry, LedgerEntryType
        entry = LedgerEntry(
            entry_id=f"L{next(_ledger_counter):06d}", entry_type=LedgerEntryType.INITIAL,
            timestamp=datetime.now(), cash_delta=initial_cash, note=f"初始资金 {initial_cash:.2f}",
        )
        self.account.ledger.append(entry)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def get_or_create_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def add_order(self, order: Order):
        self.orders.append(order)

    def add_trade(self, trade: Trade):
        self.trades.append(trade)

    def on_trade(self, trade: Trade):
        self.trades.append(trade)
        symbol = trade.symbol
        position = self.get_or_create_position(symbol)
        amount = trade.price * trade.qty

        if trade.side == Side.BUY:
            self.account.cash -= (amount + trade.commission)
            old_qty = position.qty
            old_cost = position.avg_price * old_qty
            new_qty = old_qty + trade.qty
            new_cost = old_cost + amount
            position.qty = new_qty
            position.avg_price = new_cost / new_qty if new_qty > 0 else 0.0
            position.available_qty = position.qty
        else:
            self.account.cash += (amount - trade.commission)
            old_qty = position.qty
            new_qty = old_qty - trade.qty
            position.qty = new_qty
            if new_qty == 0:
                position.avg_price = 0.0
            position.available_qty = position.qty
            pnl = (trade.price - position.avg_price) * trade.qty
            position.realized_pnl += pnl

        self._record_trade(trade)
        self._record_fee(trade)

    def _record_trade(self, trade: Trade):
        from portfolio.ledger import LedgerEntry, LedgerEntryType
        amount = trade.price * trade.qty
        cash_delta = -amount if trade.side == Side.BUY else amount
        pos_delta = trade.qty if trade.side == Side.BUY else -trade.qty
        entry = LedgerEntry(
            entry_id=f"L{next(_ledger_counter):06d}", entry_type=LedgerEntryType.TRADE,
            timestamp=trade.trade_time, symbol=trade.symbol, cash_delta=cash_delta,
            position_delta=pos_delta, price=trade.price, note=f"{trade.side.value} {trade.qty}@{trade.price:.4f}",
        )
        self.account.ledger.append(entry)

    def _record_fee(self, trade: Trade):
        from portfolio.ledger import LedgerEntry, LedgerEntryType
        fee_total = trade.fee_breakdown.total if trade.fee_breakdown else trade.commission
        entry = LedgerEntry(
            entry_id=f"L{next(_ledger_counter):06d}", entry_type=LedgerEntryType.FEE,
            timestamp=trade.trade_time, symbol=trade.symbol, cash_delta=-fee_total,
            fee=fee_total, note=f"手续费合计 {fee_total:.4f}",
        )
        self.account.ledger.append(entry)

    def update_market_value(self, symbol: str, last_price: float):
        if symbol in self.positions:
            position = self.positions[symbol]
            position.update_price(last_price)

    def calculate_market_value(self) -> float:
        return sum(pos.market_value for pos in self.positions.values() if pos.qty > 0)

    def calculate_equity(self) -> float:
        market_value = self.calculate_market_value()
        self.account.update_equity(market_value)
        return self.account.equity

    def calculate_drawdown(self) -> float:
        return 0.0

    def ledger_entries(self) -> list:
        return list(self.account.ledger)

    def summary(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("Portfolio Summary")
        lines.append("=" * 60)
        lines.append(f"Cash: {self.account.cash:.2f}")
        lines.append(f"Equity: {self.account.equity:.2f}")
        lines.append(f"Market Value: {self.calculate_market_value():.2f}")
        lines.append("")
        for symbol, position in self.positions.items():
            if position.qty > 0:
                lines.append(f"{symbol}: {position.qty} @ {position.avg_price:.2f} "
                             f"(market_value={position.market_value:.2f}, "
                             f"unrealized_pnl={position.unrealized_pnl:.2f})")
        lines.append("=" * 60)
        return "\n".join(lines)
