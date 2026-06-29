# Brooks 当前实现

内容基准：2026-06-27

本文维护 Brooks 相关代码边界、运行产物和组合研究约定。

## 主策略

当前主策略是 `brooks_price_action`。

它取代了旧 `brooks_context_router`，不再保留兼容 alias。旧模型：

```text
ContextState -> SetupKind -> Signal
```

新模型：

```text
MarketContext
  -> setup scanner
  -> PlannedTrade
  -> TradeCandidate
  -> Trader's Equation
  -> TradeDecision
```

## 代码边界

- `context.py`：只负责 market read、market cycle、overlay、主方向和 setup 是否值得扫描。
- `structure.py`：只负责 support/resistance、range midpoint/edge、market-cycle transition 和 magnet target，不检测 setup。
- `scanner.py`：统一扫描 trend pullback、breakout pullback、failed breakout，并产出 `SetupEvaluation`；真实交易和研究日志共用这一层。
- `trade_plan.py`：负责 structural stop、target model 和 target room。
- `evidence.py`：负责 `EvidenceLedger`，让 control、context、setup、signal、location、target、crowding 和 Trader's Equation 证据成为一等对象。
- `decision.py`：负责 `ContextScoreboard`、`TradeCandidate`、`TraderEquation` 和 `TradeDecision`；context score 和 probability proxy 由 evidence ledger 汇总，structure/trapped trader 证据在校准前只进入候选 telemetry。
- `diagnostics.py`：把 context/candidate 转成可落盘 telemetry。
- `journal.py`：把 `SetupEvaluation` 转成 `BrooksDecisionRecord`。
- `strategy.py`：只做编排：读盘、扫描、选择 accepted candidate 并生成 `Signal`。

## 当前分支

当前默认可用分支：

- `trend_pullback`：当前研究起点，但仍需继续用 Brooks 语义校准。
- `trend_pullback` 允许在 trend、channel、breakout continuation 中进入候选；channel 是趋势的通道阶段，不应被简单排除，但仍必须通过 range、climax、always-in、pullback setup 和 Trader's Equation 门槛。

当前研究候选：

- `breakout_pullback`：只作为研究候选；即使历史回测改善，也必须按多空、标的、market cycle 和 follow-through 重新证明。
- `failed_breakout`：暂不启用；代码已有 trap/range/two-sided 证据，但必须先证明 trapped traders 证据链在样本中有效。
- `channel` 不单独作为 setup；它是 market cycle。channel pullback 可以由 `trend_pullback` 扫描，但后续仍需单独分桶验证 channel strength、两边交易性和目标空间。

## 已完成工程基础

- `MarketRead` 显式表达 market cycle、overlay、候选 setup 和主交易方向。
- `SetupEvaluation` 显式表达每个 setup 被扫描、拒绝或接受的原因。
- `MarketCycle` 只表达市场环境：trend、channel、breakout、breakout mode、trading range、neutral、unknown。
- `MarketOverlay` 表达附加风险事件；当前 `CLIMAX` 是 overlay，不再作为独立 market cycle。
- `UNKNOWN` 只表示缺数据；`NEUTRAL` 表示有数据但没有清晰 Brooks 优势。
- `BrooksMarketStructure` 保存 support/resistance、midpoint、range position、breakout/two-sided transition 和 long/short magnet target。
- `EvidenceLedger` 保存每个分数的证据项、类别、权重和贡献，避免分数成为不可解释的黑箱。
- `TraderEquation` 显式表达 probability proxy、target room、cost 和 edge。
- `SignalDiagnostics` 保存 Brooks 决策分数、structure telemetry 和 crowding telemetry。
- `Trade` 保留 `entry_reason`、`exit_reason`、`setup_kind` 和诊断分数。
- `context_futures.reporting.write_trades_csv` 展平诊断字段。
- `BrooksDecisionRecord` 可记录每个研究候选的 market read、setup、Trader's Equation 和接受/拒绝原因。
- `ExecutionEngine` 统一执行结构止损、目标价、费用、滑点和 funding。

## 诊断 telemetry

当前诊断 telemetry 已包括：

- raw regime、market cycle、market overlay、context state、context direction。
- range/two-sided/breakout 分数。
- control score、control gap、trend alignment、follow-through、anti-range、anti-climax。
- support、resistance、midpoint、range position、breakout transition、two-sided transition、magnet target score。
- pullback depth、leg count、double test、wedge、breakout quality、breakout retest、failed breakout trap、range quality。
- target model、stop distance、Trader's Equation cost。
- funding/taker/OI/external crowding。

## 标准 artifact

`cf-backtest` 和 `cf-portfolio-backtest` 的正式结果统一写入标准 artifact 目录。旧的 `--brooks-*`、`--symbol-year-*` 等一次性 CSV 输出参数已经移除；后续需要 decision journal 或更细 Brooks 分桶时，应作为 artifact schema 的新表扩展，而不是回到散落参数。

标准 artifact 包含 `manifest.json`、`summary.json`、`summary.md`、`equity_curve.csv`、`trades.csv`、`period_returns.csv`、`account_results.csv`、`strategy_contribution.csv` 和 `symbol_contribution.csv`。其中 `period_returns.csv` 表达年度和总窗口收益，`account_results.csv` 表达每个独立账户或共享账户的指标，`strategy_contribution.csv` / `symbol_contribution.csv` 用于观察贡献。

`cf-portfolio-backtest` 默认同时产出 independent 和 shared 两种账户口径。independent 是每个 `strategy_id + symbol` 一个账户，每个账户使用配置中的 `risk.initial_equity` 或 `--initial-equity` 覆盖值；shared 是所有策略共享同一个账户，初始资金使用同一个 `risk.initial_equity` 或 `--initial-equity` 覆盖值。只想跑单一口径时显式传 `--account-mode independent` 或 `--account-mode shared`。

## Universe Matrix

全币种和全时间组合的策略优化使用 `cf-universe-backtest`，不要把矩阵直接写进 `price_action_portfolio.toml`。组合配置只保留已经通过矩阵筛选的稳定组合；矩阵 runner 才负责扫描 `data/parquet/binance_usdm/` 下全部币种、`5m/15m/30m/1h/4h` 的 `slow >= fast` 组合，并输出：

- `*_detail.csv`：每个 profile / symbol / fast / slow / window 一行，包含 `cost_usdt`、`final_usdt`、收益、回撤、交易数、胜率、PF 和 funding。
- `*_pivot.csv`：按 symbol/timeframe 横向展开 2023、2024、2025、2026 YTD 和 `2023_now`。
- `*_rankings.csv`：按总窗口表现和年度稳定性排序，辅助筛选候选组合。

`brooks_trend_only` profile 使用当前 `price_action_portfolio.toml` 的第一条策略作为参数模板，但会按时间尺度缩放周期类参数：例如 1h 图上的 ATR 14，换到 30m 会变为 ATR 28；4h 慢图上的 EMA 50/200，换到 1h 慢图会变为 200/800。这样矩阵比较的是相近市场时间跨度下的 Brooks 逻辑，而不是简单套用固定 bar 数。
