---
title: Quant V2 接口与签名
version: 2.0
tags: [量化, 接口, 签名, API, DataManager, BacktestEngine, 策略基类, 风控, 仓位]
summary: 各层核心类的构造签名、关键方法参数与返回，方便开发时直接调用或实现扩展。
---

# Quant V2 接口与签名

> 所有签名与真实代码一致，未实现项会标注“规划中”。

## 1. 数据层

### AbstractDataSource（`data/data_source.py`）

```python
class AbstractDataSource(ABC):
    name: str
    def __init__(self, token: Optional[str] = None, **kwargs): ...
    def _check_auth(self, required=True, message="") -> None:   # 失败抛 DataSourceAuthError
    @staticmethod _to_bar(...) -> Bar
    @abstractmethod
    def fetch_daily(self, symbol: str, start: date, end: date, adjust="qfq") -> List[Bar]: ...
    @abstractmethod
    def price_to_fetch(self, symbol: str) -> Bar: ...
    def fetch_daily_sorted(self, *a, **k) -> List[Bar]: ...
```

- `adjust`: `qfq` 前复权 / `hfq` 后复权 / `""` 不复权
- 异常：`DataSourceError`、`DataSourceAuthError`（缺 apikey）

### DataManager（`data/data_manager.py`）

```python
dm = DataManager({"akshare": AkshareDataSource()})
dm.register(name, source) -> DataManager
dm.set_default(source_or_name)
dm.get_bars(symbol, start, end, adjust="qfq", source=None, use_cache=True) -> List[Bar]
dm.get_many_bars(symbols, start, end, ...) -> Dict[str, List[Bar]]
dm.latest_price(symbol) -> Bar
dm.clear_cache()
```

- 缓存键：`(源名, symbol, start, end, adjust)`，命中缓存返回同一对象
- 未注册默认源时 `get_bars` 抛 `ValueError`；未注册指定源抛 `KeyError`

### 适配器
- `AkshareDataSource`（免费，无需 token，A股日线）— 见 `data/akshare_source.py`
- `GmDataSource`（掘金 GM，需 apikey）— 见 `data/gm_source.py`
- 代码规范：`_normalize_symbol("600519")=="sh600519"`、`_gm_symbol("600519")=="SHSE.600519"`

## 2. 策略层

### BaseStrategy（`strategy/base_strategy.py`）

```python
class BaseStrategy:
    def __init__(self, name="BaseStrategy", **params)
    def set_portfolio(portfolio)      # 引擎绑定，供查询真实持仓
    def initialize(self)             # 可选重写，参数校验/初始化
    def on_bar(self, bar: Bar):      # 【必须实现】核心逻辑
    def on_trade(self, trade)        # 可选，成交回调
    def on_order(self, order)        # 可选，订单回调
    def set_bar_context(bar, index, history)  # 引擎注入，防前视
    def buy(symbol, price, qty=100, reason="") -> Signal
    def sell(symbol, price, qty=100, reason="") -> Signal
    def get_signals() -> List[Signal]
    def get_history_bars(n) -> List[Bar]
    def get_current_price() -> float
```

**写策略规范**：
1. `on_bar` 内因果关系必须仅基于 `self.closes`/`self.state.history`（已注入历史），**禁止读未来 bar**。
2. 通过 `buy()/sell()` 产生信号，返回后由引擎收集（`get_signals` 清空）。
3. 用 `self.portfolio.get_position(symbol)` 查询真实持仓（引擎绑定后非 None）。
4. 波段类数值（如 ATR）建议用 `collections.deque(maxlen=N)` 增量维护。

### 内置策略（`strategy/`）
| 策略 | 参数 | 逻辑 |
|---|---|---|
| `DonchianStrategy` | entry_period=20, exit_period=10, atr_period=20, atr_multiplier=2 | 突破N日高开多、跌破N日低平仓、ATR止损 |
| `MACrossStrategy` | short=5, long=20, atr=14, mult=2 | 金叉开多、死叉平多、ATR移动止损 |
| `BollingerStrategy` | period=20, num_std=2 | 跌破下轨开多、回归中轨平多 |
| `RSIStrategy` | period=14, oversold=30, exit_rsi=50 | RSI<超卖开多、>中线上方平多（Wilder RSI） |
| `TurtleStrategy` | entry=20, exit=10, atr=20, mult=2 | 突破开多、2N止损、跌破低点平多 |
| `MomentumStrategy` | lookback=20, threshold=0 | 动量转正开多、转负平仓 |

## 3. 风控层

### RiskConfig + RiskManager（`risk/risk_manager.py`）

```python
@dataclass RiskConfig:
    max_position_ratio=0.3        # 单标的最大仓位
    max_total_position_ratio=0.9  # 总仓位
    max_drawdown=0.2              # 最大回撤触发
    drawdown_warning=0.15
    max_daily_loss=5000.0
    max_daily_loss_ratio=0.02
    max_consecutive_losses=5
    max_single_trade_amount=50000.0   # 单笔金额上限（高价股注意）
    max_single_trade_ratio=0.1
    max_leverage=1.0

risk_manager = RiskManager(config=RiskConfig(...))
result = rm.validate_signal(signal, portfolio) -> RiskCheckResult(passed, reason)
rm.record_trade_result(pnl)
rm.reset_daily() / rm.reset_suspension()
```

> ⚠️ **高价股坑**：茅台 100 股 ≈ 15 万 > 默认 `max_single_trade_amount=50000`，回测会被全部拦截。真实高价股回测请在 `RiskConfig` 放宽该值（见 `scripts/real_backtest.py`）。

### PositionSizer（`risk/position_sizer.py`）

```python
create_sizer(type, **kw)   # 'fixed' | 'percent' | 'atr'
FixedSizer(qty=100.0)
PercentSizer(percent=0.1, min_amount=1000.0)
ATRSizer(risk_percent=0.02, atr_multiplier=2.0, atr_period=20, min_qty=100.0)
# 统一方法
sizer.calculate_qty(symbol, price, portfolio, bar=None) -> float
# ATR 仓位公式：qty = (equity*risk_percent) / (atr*multiplier)，向下取整到100股
```

### StopManager（`risk/stop_manager.py`）

```python
create_fixed_stop(entry_price, direction, stop_percent=0.02, **kw)
create_atr_stop(entry_price, direction, atr, atr_multiplier=2.0, **kw)
create_trailing_stop(entry_price, direction, trailing_percent=0.03, **kw)
# manager
sm.add_stop_order(stop_order) / sm.remove_stop_order(symbol)
sm.update(symbol, price) -> "SELL"|"COVER"|None   # 触发返回动作
sm.get_stop_price(symbol)
```

## 4. 经纪层

### FeeModel（`broker/fee_model.py`）

```python
create_fee_model("china_stock"|"us_stock"|"crypto", **kw) -> FeeModel
model.calculate(side, price, qty, notional=None) -> FeeBreakdown
# FeeBreakdown: commission/stamp_tax/transfer_fee/sec_fee/ta_fee/slippage_cost/impact_cost
#   .total = 各规费合计（不含滑点）; .all_in_cost = total + 滑点 + 冲击
```

A股默认：佣金 0.03%(最低5元,双向) + 印花税 0.05%(仅卖) + 过户费 0.001%(双向) + 滑点 0.01%。

### OrderMatcher（`broker/matcher.py`）

```python
matcher = OrderMatcher(volume_limit_ratio=0.1, use_price_limit=True)
matcher.match(order, bar) -> (OrderStatus, fill_price, fill_qty, reject_reason)
```

撮合规则见 `docs/03_backtest_assumptions.md`。

### BacktestBroker（`broker/backtest_broker.py`）

```python
broker = BacktestBroker(fee_model=None, matcher=None, on_trade_callback=None)
order = broker.create_order(symbol, side, order_type, price, qty, stop_price=0, strategy_id="")
broker.submit_order(order)
broker.match_orders(bar) -> List[Trade]
broker.cancel_order(order_id) -> bool
broker.pending_orders(symbol=None) -> List[Order]
broker.all_orders() / broker.get_order(order_id)
```

## 5. 引擎层

### BacktestEngine（`engine/backtest_engine.py`）

```python
engine = BacktestEngine(
    strategy, portfolio,
    broker=None, risk_manager=None, position_sizer=None,
    symbol="", lookback=500,
)
result = engine.run(bars) -> dict
# result: {bars, trades, orders, final_equity, total_return, rejected}
engine.get_equity_curve() -> List[dict{datetime,equity,cash,market_value,close}]
engine.get_all_trades() / get_all_orders()
engine.analyzer() -> PerformanceAnalyzer
engine.rejected_signals  # 风控/资金拒绝的信号列表
```

## 6. 事件层（`event/event_engine.py`）

```python
engine = EventEngine()  # 或 get_default_engine()
engine.subscribe(EventType.BAR, callback, priority=0)   # 优先级高者先
engine.unsubscribe(EventType.BAR, callback) -> bool
engine.put(Event(event_type, data, sender=""))          # 同步派发
engine.emit(event_type, data, sender="")
engine.handled_count / subscriptions() / clear_all()
```

单个处理器异常不影响其它处理器。

## 7. 绩效层（`performance/analyzer.py`）

```python
analyzer = PerformanceAnalyzer(equity_curve, trades, benchmark_curve=None, risk_free_rate=0.02)
metrics = analyzer.compute() -> PerformanceMetrics  # 缓存，二次调用直接返回
analyzer.to_dataframe() -> pd.DataFrame  # datetime/equity/daily_return/drawdown
analyzer.metrics_to_dict() -> dict       # 16 个指标
analyzer.summary() -> str
```

`PerformanceMetrics` 字段见 `docs/07_performance_optimizer.md`。

## 8. 报错/异常体系（`core/exceptions.py`）

- `QuantError` 基类
- `DataError` / `DataNotFoundError` / `DataFormatError`
- `BrokerError` / `InsufficientFunds` / `OrderRejected`
- `RiskRejected`
- `PositionError` / `InsufficientPosition`
- `StrategyError` / `ConfigError` / `PersistenceError`