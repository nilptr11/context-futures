# context-futures

面向 Binance USD-M 永续合约的策略研究、回测和报告框架。

本仓库以清晰分层和职责边界为优先目标，不保留旧脚本和旧配置的兼容行为。策略只负责产生信号；执行层负责把信号转换为持仓和交易；回测层负责历史事件循环；报告层负责收益、回撤、月度收益和交易明细分析。

## 目录结构

```text
configs/        # 可复用策略配置和研究配置
docs/           # 长期维护研究文档
reports/        # 本地生成的回测 CSV/临时分析输出
src/context_futures/
  domain/        # 市场、信号、仓位、组合、报告、交易规则领域对象
  config/        # 严格嵌套 TOML 配置模型
  indicators/    # EMA/ATR、价格行为、市场状态
  strategies/    # 只负责信号生成
  engine/        # 执行推进、风控 sizing、滑点、止损止盈、资金费率
  backtesting/   # 单标的和共享账户历史回测循环
  binance/       # Binance USD-M HTTP、endpoint、行情抓取和交易规则适配
  reporting/     # 回撤、月度收益、CSV 输出
  cli/           # 命令行入口
```

核心依赖方向：

```text
cli -> binance / backtesting / reporting
backtesting -> strategies / engine / domain / config
strategies -> domain / indicators / config
engine -> domain / config
binance -> domain
reporting -> domain
```

`binance/` 是唯一允许理解 Binance 原始字段、签名、endpoint 和 `exchangeInfo` 结构的模块。策略、引擎、回测和报告只使用内部领域对象。

## 环境

```bash
uv sync
uv run pytest
```

运行时代码只依赖 Python 标准库；开发工具由 `uv` 统一管理。

## 命令

获取 K 线：

```bash
uv run cf-fetch-klines --symbol BTCUSDT --interval 4h --start 2024-01-01 --end 2024-06-01 --out data/BTCUSDT-4h.csv
```

获取资金费率：

```bash
uv run cf-fetch-funding --symbol BTCUSDT --start 2024-01-01 --end 2024-06-01 --out data/BTCUSDT-funding.csv
```

单标的回测：

```bash
uv run cf-backtest \
  --config configs/examples/single_breakout_atr.toml \
  --symbol BTCUSDT \
  --fast-csv data/BTCUSDT-4h.csv \
  --slow-csv data/BTCUSDT-4h.csv \
  --funding-csv data/BTCUSDT-funding.csv \
  --trades-out reports/trades.csv \
  --monthly-out reports/monthly.csv \
  --brooks-out reports/brooks_buckets.csv \
  --brooks-decisions-out reports/brooks_decisions.csv \
  --brooks-decisions-summary-out reports/brooks_decision_summary.csv \
  --brooks-research-setups
```

共享账户组合回测：

```bash
uv run cf-portfolio-backtest \
  --config configs/strategies/brooks/price_action_portfolio.toml \
  --data-dir data \
  --funding-dir data \
  --symbols BTCUSDT ETHUSDT \
  --monthly-out reports/portfolio_monthly.csv \
  --trades-out reports/portfolio_trades.csv \
  --brooks-out reports/portfolio_brooks_buckets.csv \
  --brooks-decisions-out reports/portfolio_brooks_decisions.csv \
  --brooks-decisions-summary-out reports/portfolio_brooks_decision_summary.csv \
  --brooks-research-setups
```

## 配置

只支持嵌套 TOML 配置。旧的 flat strategy keys 会被明确拒绝。

```toml
[strategy]
id = "breakout_4h"
name = "breakout_atr"
symbols = ["BTCUSDT"]
fast_interval = "4h"
slow_interval = "4h"

[strategy.breakout]
window = 120
atr_period = 14

[strategy.trade]
stop_atr_multiple = 1.5
trail_atr_multiple = 2.5

[strategy.trend]
fast_ema = 50
slow_ema = 200

[strategy.price_action]
enabled = true
```

多策略配置使用 `[[strategies]]`，示例见 `configs/strategies/brooks/price_action_portfolio.toml`。

## 策略边界

策略模块只返回 `Signal | None`。策略层不能计算仓位、修改组合状态、应用滑点、扣资金费率、下单或写报告。

当前可用策略名：

- `breakout_atr`
- `brooks_breakout`
- `brooks_pullback`
- `brooks_price_action`

## 报告

回测会生成：

- 最终权益和总收益率
- 最大回撤
- 交易数量、胜率、利润因子
- 资金费率合计
- 权益曲线
- 月度收益
- 带 `SignalDiagnostics` 的交易明细

CSV 输出函数位于 `context_futures.reporting`。

长期研究结论和方案放在 `docs/`；`reports/` 只放回测生成的 CSV 和临时输出。

## 实盘交易

实盘和 paper runner 已在架构清理中删除，因为它们重复实现了回测执行逻辑。后续应基于 `context_futures.engine.ExecutionEngine` 和 `context_futures.binance` 重建。
