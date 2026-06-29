# context-futures

面向 Binance USD-M 永续合约的策略研究、回测、报告和实盘框架。

## 目录结构

```text
configs/        # 可复用策略配置和研究配置
data/backtests/ # 本地生成的标准回测 artifact
docs/           # 长期维护研究文档
src/context_futures/
  domain/        # 市场、信号、仓位、组合、报告、交易规则领域对象
  config/        # 严格嵌套 TOML 配置模型
  data/          # 数据读取、可见性规则和 parquet 存储
  features/      # EMA/ATR、价格行为、市场状态
  strategies/    # 策略协议、baseline 策略和 Brooks 策略域
  execution/     # 执行推进、风控 sizing、滑点、止损止盈、资金费率
  backtest/      # 单标的、独立账户和共享账户历史回测循环
  binance/       # Binance USD-M HTTP、endpoint、行情抓取和交易规则适配
  reporting/     # 回撤、月度收益、CSV 输出
  cli/           # 命令行入口
```

核心依赖方向：

```text
cli -> binance / backtest / reporting
backtest -> strategies / execution / data / domain / config
strategies -> domain / features / config
execution -> domain / config
binance -> domain
reporting -> domain
```

`binance/` 是唯一允许理解 Binance 原始字段、签名、endpoint 和 `exchangeInfo` 结构的模块。策略、执行、回测和报告只使用内部领域对象。

## 环境

```bash
uv sync
uv run pytest
```

运行时通过 `pyarrow` 读取 parquet 研究数据；开发工具由 `uv` 统一管理。

## 命令

回测默认读取 point-in-time parquet 数据集：

```text
data/parquet/binance_usdm
```

单标的回测：

```bash
uv run cf-backtest \
  --config configs/examples/single_breakout_atr.toml \
  --symbol BTCUSDT \
  --data-root data/parquet/binance_usdm \
  --start 2024-01-01 \
  --end 2024-06-01 \
  --artifact-root data/backtests
```

多策略组回测默认同时产出两种账户口径：

- independent：每个 `strategy_id + symbol` 一个账户，每个账户使用配置中的 `risk.initial_equity` 或
  `--initial-equity` 覆盖值。
- shared：所有策略共享同一个账户，账户初始资金使用同一个 `risk.initial_equity` 或 `--initial-equity` 覆盖值。

```bash
uv run cf-portfolio-backtest \
  --config configs/strategies/brooks/trend_continuation_portfolio.toml \
  --data-root data/parquet/binance_usdm \
  --initial-equity 100 \
  --start 2023-01-01 \
  --end 2026-06-28 \
  --artifact-root data/backtests
```

只想跑单一口径时使用 `--account-mode independent` 或 `--account-mode shared`：

```bash
uv run cf-portfolio-backtest \
  --config configs/strategies/brooks/trend_continuation_portfolio.toml \
  --data-root data/parquet/binance_usdm \
  --account-mode shared \
  --initial-equity 100 \
  --start 2024-01-01 \
  --end 2024-03-01 \
  --artifact-root data/backtests
```

回测数据目录只支持 parquet 分区布局：

```text
data/parquet/binance_usdm/klines/interval=<interval>/symbol=<SYMBOL>/year=<YEAR>/part.parquet
data/parquet/binance_usdm/funding/symbol=<SYMBOL>/year=<YEAR>/part.parquet
```

例如：

```text
data/parquet/binance_usdm/klines/interval=1h/symbol=BTCUSDT/year=2025/part.parquet
data/parquet/binance_usdm/klines/interval=4h/symbol=BTCUSDT/year=2025/part.parquet
data/parquet/binance_usdm/funding/symbol=BTCUSDT/year=2025/part.parquet
```

数据按市场和数据类型维护，不按策略维护；任意策略都可以复用同一数据集。每条记录必须通过 `available_at` 或数据集默认规则确定回测可见时间。

每次回测都会写入标准 artifact 目录：

```text
data/backtests/<run_id>/
  manifest.json
  summary.json
  summary.md
  equity_curve.csv
  trades.csv
  period_returns.csv
  account_results.csv
  strategy_contribution.csv
  symbol_contribution.csv
```

`manifest.json` 记录配置、数据目录、账户模式、风险参数、git commit 和配置 hash；`summary.md` 是可直接复制的人工报告。

全币种、全时间组合研究矩阵：

```bash
uv run cf-universe-backtest \
  --profile brooks_trend_continuation_baseline \
  --data-root data/parquet/binance_usdm \
  --start 2023-01-01 \
  --end 2026-06-28 \
  --equity 100 \
  --workers 3 \
  --artifact-root data/backtests
```

`cf-universe-backtest` 会自动发现数据目录中的币种，并对 `5m`、`15m`、`30m`、`1h`、`4h`
生成 `slow >= fast` 的时间组合。artifact 中包含：

```text
matrix_detail.csv    # 每个币种/时间组合/年份一行
matrix_pivot.csv     # 每个币种/时间组合一行，横向展开各年份和总窗口
matrix_rankings.csv  # 按 2023_now 表现和年度稳定性排序
```

这个矩阵用于筛选币种和周期，再把稳定组合沉淀进 `trend_continuation_portfolio.toml`；不要把全量矩阵直接塞进组合配置。

内置 universe profile 位于 `configs/universe_profiles/`。profile 负责声明研究模板和启用的 Brooks setup；代码不会按 profile 名硬编码特殊逻辑。

策略 TOML 中通用 ATR 周期放在 `[strategy.market]` 或 `[strategies.market]`。baseline 的 `[*.breakout]`
只保留突破窗口，baseline 的 `[*.price_action]` 只作为过滤器配置；Brooks 的 setup 参数位于
`[*.brooks.setups.*]`，结构读取参数位于 `[*.brooks.structure]`。
