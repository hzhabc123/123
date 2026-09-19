# P0 共享接口契约（子 Agent 必须遵守）

## 1. 文件落点

所有代码写入 `/Coze/Drive/扣子/quant_run/`，目录结构对应 `测试/quant/`：

```
quant_run/
├── config/settings.py            # 保留；新增字段
├── config/config.yaml            # 新增：运行配置（P0-7）
├── data/
│   ├── bar.py                    # Bar 新增 flags 字段（P0-1）
│   ├── calendar.py               # 新增（P0-1）
│   └── ...
├── strategy/
│   ├── base_strategy.py          # 增加 bar_index/current_bar 防前视（P0-2）
│   └── ...
├── broker/
│   ├── order.py                  # 新增独立 Order 类（P0-3）
│   ├── broker.py                 # 接口扩展
│   ├── fee_model.py              # 新增（P0-4）
│   └── backtest_broker.py        # 重写撮合循环（P0-3 + P0-4）
├── portfolio/
│   ├── ledger.py                 # 新增（P0-5）
│   ├── account.py                # 增 ledger 字段
│   ├── portfolio.py              # 增 corporate_action 方法
│   └── ...
├── risk/risk_manager.py          # 暂时保留，P1-1 再扩展
├── performance/
│   ├── __init__.py               # 新增目录（P0-6）
│   └── analyzer.py
├── engine/backtest_engine.py     # 适配新接口
└── tests/
    ├── test_p0_4_cost.py
    ├── test_p0_3_match.py
    ├── test_p0_5_ledger.py
    ├── test_p0_6_metrics.py
    └── test_p0_7_repro.py
```

## 2. 核心新类型（各子 Agent 必须使用相同签名）

### 2.1 数据层（子任务 A 定义）

```python
# data/bar.py 新增字段
@dataclass(slots=True)
class BarFlags:
    is_suspended: bool = False   # 停牌
    is_st: bool = False          # ST/*ST
    is_delisted: bool = False    # 退市
    limit_up: bool = False       # 涨停
    limit_down: bool = False     # 跌停
    is_ex_dividend: bool = False # 除权除息日

@dataclass(slots=True)
class Bar:
    symbol: str
    datetime: datetime
    open: float; high: float; low: float; close: float
    volume: float = 0.0
    amount: float = 0.0
    flags: BarFlags = field(default_factory=BarFlags)  # 新增
    adj_factor: float = 1.0                            # 复权因子（新增，默认 1.0 不复权）
```

```python
# data/calendar.py
class TradingCalendar:
    def is_trading_day(self, dt: date) -> bool: ...
    def next_trading_day(self, dt: date) -> date: ...
    def add_trading_days(self, dt: date, n: int) -> date: ...
```

实现：使用 A 股 2024-2026 工作日作为最简实现（节假日近似用周一-周五）。

### 2.2 订单与费用（子任务 B 定义）

```python
# broker/order.py（替代 portfolio/order.py 的 Order，后者保留为兼容）
class OrderSide(Enum): BUY = "BUY"; SELL = "SELL"
class OrderType(Enum): MARKET = "MARKET"; LIMIT = "LIMIT"; STOP = "STOP"
class OrderStatus(Enum): PENDING = "PENDING"; PARTIAL = "PARTIAL"; FILLED = "FILLED"; CANCELLED = "CANCELLED"; REJECTED = "REJECTED"

@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float            # 限价单价格；市价单为信号价
    stop_price: float = 0.0 # 止损触发价
    volume: int = 0
    filled_volume: int = 0
    filled_avg_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    create_time: datetime = None
    update_time: datetime = None
    reject_reason: str = ""
```

```python
# broker/fee_model.py
@dataclass
class FeeBreakdown:
    commission: float = 0.0   # 佣金
    stamp_tax: float = 0.0    # 印花税（仅卖出）
    transfer_fee: float = 0.0 # 过户费
    slippage_cost: float = 0.0
    impact_cost: float = 0.0
    @property
    def total(self) -> float: ...

class FeeModel(ABC):
    @abstractmethod
    def calculate(self, order: Order, fill_price: float, fill_volume: int, bar: Bar) -> FeeBreakdown: ...

class ChinaAFeeModel(FeeModel):
    """A 股费用：佣金双向 + 印花税卖出 0.05% + 过户费 0.001% + 滑点"""
    def __init__(self, commission_rate=0.0003, min_commission=5.0,
                 stamp_tax_rate=0.0005, transfer_fee_rate=0.00001,
                 slippage_rate=0.0001): ...
```

### 2.3 账本（子任务 B 定义）

```python
# portfolio/ledger.py
class LedgerEntryType(Enum):
    TRADE = "TRADE"
    FEE = "FEE"
    DIVIDEND = "DIVIDEND"     # 现金分红
    BONUS_SHARE = "BONUS_SHARE" # 送股
    SPLIT = "SPLIT"           # 拆股
    INITIAL = "INITIAL"       # 初始资金

@dataclass
class LedgerEntry:
    entry_id: str
    entry_type: LedgerEntryType
    timestamp: datetime
    symbol: str = ""
    cash_delta: float = 0.0
    position_delta: int = 0
    price: float = 0.0
    fee: float = 0.0
    note: str = ""
```

### 2.4 绩效（子任务 C 定义）

```python
# performance/analyzer.py
@dataclass
class PerformanceMetrics:
    total_return: float
    annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # 天数
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    turnover: float
    benchmark_return: float
    alpha: float
    beta: float
    information_ratio: float

class PerformanceAnalyzer:
    def __init__(self, equity_curve: list, trades: list,
                 benchmark_curve: list = None, risk_free_rate: float = 0.02): ...
    def compute(self) -> PerformanceMetrics: ...
    def to_dataframe(self): ...  # 每日净值序列
```

### 2.5 可复现（子任务 C 定义）

```python
# config/run_hash.py
def compute_run_hash(config_path: str, data_files: list) -> str:
    """对 config.yaml 内容 + 数据文件 SHA256 拼接后再 SHA256"""

# 引擎启动时写 manifest.json：
# {
#   "run_id": "uuid",
#   "run_hash": "...",
#   "config_sha256": "...",
#   "data_sha256": {"301313.txt": "..."},
#   "started_at": "ISO",
#   "finished_at": "ISO",
#   "metrics_sha256": "..."
# }
```

## 3. 接口兼容要求

- 原 `portfolio.order.Order` / `Direction` / `OrderStatus` **保留**，新增 `broker/order.py` 不复用。
- `BacktestBroker.execute_signal` 保留为简化入口，内部转成新 `Order` 流程；同时新增 `submit_order / cancel_order` 接口。
- `Strategy` 返回的 `Signal` 保留，引擎内部把 `Signal` 翻译成 `Order` 提交给 broker。
- `Portfolio.on_trade` 保留原签名，新增 `record_ledger` 内部调用，保持对老测试的兼容。
- `RiskManager.validate(signal)` 签名不变，P1-1 再扩展。
- `main.py` 最终能 `python main.py` 一键跑通，输出绩效报告。

## 4. 测试要求

- 全部使用 pytest，`tests/test_p0_*.py`
- 每个 P0 子任务至少 5 个测试用例，覆盖正常路径 + 边界 + 异常
- 测试不依赖真实数据文件：用 `Bar(...)` 构造 mock 数据
- 测试必须能在 Python 3.10+ 环境通过 `pytest tests/` 全部运行
- 依赖：`pytest`、`pandas`、`numpy`（环境中已有）

## 5. 文档要求

每个子任务完成后在 `/Coze/Drive/扣子/quant_run/docs/p0/` 写一个 `{task_id}_{topic}.md`，包含：
- 设计决策（ADR 风格，问题/选项/决定）
- 关键代码片段
- 测试命令与结果
- 验收证据（贴 pytest 输出）

## 6. 子任务分工

- **子任务 A（数据 + 防前视 + 可复现 = P0-1 + P0-2 + P0-7）**
  修改：`data/bar.py`, `data/calendar.py`(新), `data/tdx_txt_data_source.py`, `strategy/base_strategy.py`, `config/config.yaml`(新), `config/run_hash.py`(新)
- **子任务 B（订单撮合 + 费用 + 账本 = P0-3 + P0-4 + P0-5）**
  新增：`broker/order.py`(新), `broker/fee_model.py`(新), `portfolio/ledger.py`(新)
  修改：`broker/backtest_broker.py`, `portfolio/portfolio.py`, `portfolio/account.py`, `engine/backtest_engine.py`
- **子任务 C（绩效指标 + 集成 = P0-6）**
  新增：`performance/__init__.py`, `performance/analyzer.py`, `tests/test_p0_*.py`
  修改：`engine/backtest_engine.py`(集成绩效), `main.py`(输出一键报告 + manifest)

子任务 C 必须在 A、B 完成后执行（依赖其类型）。子任务 A 和 B 可并行。
