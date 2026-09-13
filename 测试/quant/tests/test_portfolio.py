from datetime import datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
from portfolio.portfolio import Portfolio
from portfolio.trade import Trade
from portfolio.order import Direction


portfolio = Portfolio(
    initial_cash=100000
)

trade = Trade(
    trade_id="T001",
    order_id="O001",
    symbol="301313",
    direction=Direction.BUY,
    price=20,
    volume=100,
    trade_time=datetime.now()
)

portfolio.on_trade(trade)

portfolio.update_market_value(
    symbol="301313",
    last_price=22
)

print("现金:", portfolio.account.cash)

print("总资产:", portfolio.account.total_asset)

print(
    portfolio.positions["301313"]
)