# Binance USD-M Futures Quant Starter

面向 Binance.com USD-M 永续合约的第一版量化工程骨架。

默认策略是 BTCUSDT/ETHUSDT 的 4h 突破趋势策略：

- 4h 收盘价突破过去 120 根 K 线高/低点入场。
- 4h EMA50/EMA200 过滤大方向。
- ATR(14) 计算初始止损和移动止损。
- 可选 Brooks 风格价格行为过滤：强信号 K、trading range、late climax。
- 支持 20x 杠杆设置，但仓位由“每笔风险占账户权益”决定，默认不会因为 20x 自动满仓。

## 项目结构

```text
src/bn_quant/
  binance_usdm.py   # Binance USD-M REST client
  strategies/
    base.py         # strategy protocol, trend filter, shared strategy helpers
    breakout_atr.py # Breakout + ATR + higher timeframe trend
    brooks/
      strategy.py   # Brooks breakout, pullback and price-action orchestration
      context.py    # market context, candidate routing and trader's equation scoring
      pullback.py   # H2/L2, wedge and EMA pullback signal detection
      setups.py     # breakout-pullback and failed-breakout setup detection
      trade_plan.py # Brooks structural stop/target planning
  execution/
    filters.py      # entry-side execution filters
  market_regime.py  # Brooks-style market cycle and Always-In scoring
  trade_plan.py     # generic signal stop/target helpers
  backtest.py       # Event-driven backtester
  indicators.py     # EMA/ATR
  precision.py      # tick/step rounding helpers
  config.py         # TOML config loader
scripts/
  fetch_klines.py   # download futures klines to CSV
  fetch_funding.py  # download historical funding rates to CSV
  backtest.py       # run strategy backtest from CSV files
  grid_search.py    # run train/test parameter grid
  walk_forward.py   # run fixed-parameter single-strategy walk-forward validation
  walk_forward_multi.py # run active-strategy walk-forward validation
  paper_runner.py   # persistent paper runner with portfolio risk controls
  live_rest_runner.py # dry-run/live REST polling runner
tests/
  test_core.py
```

## 快速开始

```bash
cd /Users/admin/Documents/Codex/2026-06-26/duao/outputs/binance_futures_quant
PYTHONPATH=src python3 scripts/fetch_klines.py --symbol BTCUSDT --interval 4h --start 2021-01-01 --end 2026-06-26 --out data/BTCUSDT-4h.csv
PYTHONPATH=src python3 scripts/fetch_funding.py --symbol BTCUSDT --start 2021-01-01 --end 2026-06-26 --out data/BTCUSDT-funding.csv
PYTHONPATH=src python3 scripts/backtest.py --config config.toml --fast-csv data/BTCUSDT-4h.csv --slow-csv data/BTCUSDT-4h.csv --funding-csv data/BTCUSDT-funding.csv --symbol BTCUSDT
```

## API key

实盘/查询私有接口需要环境变量：

```bash
export BINANCE_FUTURES_KEY="..."
export BINANCE_FUTURES_SECRET="..."
```

建议：

- API key 不开提现权限。
- 开 IP 白名单。
- 先用小资金、逐仓、低风险参数跑。
- 每个策略单独 key 或子账户。

## 20x 杠杆说明

配置里 `leverage = 20` 只是把交易所杠杆设置为 20x。真正下单数量仍由以下约束共同决定：

- `risk_fraction`：单笔最大亏损占权益比例，默认 0.01。
- `max_symbol_notional_fraction`：单一标的最大名义仓位，默认 1.0 倍权益。
- `stop_atr_multiple`：止损距离。

也就是说，20x 是保证金效率，不是风险预算。当前默认 `risk_fraction = 0.01`，即单笔最大亏损约 1% 权益；第一版不建议把 `max_symbol_notional_fraction` 直接调到 20。

## 不做网格交易

这里不会做合约网格交易，也不会逆势补仓或马丁加仓。项目里的历史 `grid_results*.csv` 是参数敏感性扫描结果，不是网格交易策略。当前策略只在趋势突破后开仓，单方向一个仓位，靠 ATR 止损退出。

## Price Action 过滤器

配置中默认启用：

```toml
enable_price_action_filters = true
```

当前实现的是 Brooks 风格 Phase 1 过滤器：

- 强多/强空信号 K。
- 最近 K 线重叠和来回穿越过多时视为 trading range，禁止新开仓。
- 价格距离 EMA50 超过 ATR 阈值时视为 late climax，避免追在趋势末端。

它是可切换过滤层，不是完整 Brooks 主观交易系统。关闭方式：

```toml
enable_price_action_filters = false
```

## Brooks 实现纪律

后续 Brooks 相关实现必须先对齐 [Brooks Alignment Checklist](reports/brooks_alignment_checklist.md)。
当前 Brooks 思想和未来函数审计见 [Brooks and Lookahead Audit](reports/brooks_and_lookahead_audit.md)。

核心约束：

- Context 先于形态；
- 形态只生成候选交易，不直接生成交易；
- Trading Range 默认 No Trade；
- Breakout 必须看 follow-through；
- Failed Breakout 必须证明 trapped traders；
- 入场前必须先定义 invalidation；
- 最终交易必须通过 Trader's Equation；
- crypto 衍生品数据只能作为 context evidence，不能直接变成开仓信号。

## 多策略

策略配置分两层：

- `name`：策略类型，例如 `breakout_atr`。
- `id`：策略实例，例如 `breakout_pa`、`breakout_raw`。
- `symbols`：可选，限制该策略实例只处理指定交易对；不设置时使用 runner 命令行传入的全部 symbols。

默认单策略使用 `[strategy]`。需要并行 paper 多策略时，使用一个或多个 `[[strategies]]`；一旦存在 `[[strategies]]`，支持多策略的 runner 会使用它们替代单个 `[strategy]`。

示例：

```toml
[[strategies]]
id = "breakout_pa"
name = "breakout_atr"
fast_interval = "4h"
slow_interval = "4h"
breakout_window = 120
atr_period = 14
stop_atr_multiple = 1.5
trail_atr_multiple = 2.5
trend_fast_ema = 50
trend_slow_ema = 200
enable_price_action_filters = true

[[strategies]]
id = "brooks_breakout_4h"
name = "brooks_breakout"
fast_interval = "4h"
slow_interval = "4h"
breakout_window = 120
atr_period = 14
stop_atr_multiple = 1.5
trail_atr_multiple = 2.5
trend_fast_ema = 50
trend_slow_ema = 200
enable_price_action_filters = true
brooks_breakout_buffer_atr = 0.10
brooks_follow_through_close_location_min = 0.55
brooks_follow_through_close_location_max = 0.45
```

Paper runner 的持仓状态按 `strategy_id:symbol` 隔离，因此两个策略可以同时观察同一个标的；组合级总名义仓位仍然共享同一个账户级上限。

可以直接参考 `config.multi.example.toml`。当前多策略并行主要由 `paper_runner.py` 支持；研究脚本如 `backtest.py`、`walk_forward.py` 默认仍读取单个 `[strategy]`，用于单策略评估。

如果不同品种需要不同入场周期，可以参考 `config.brooks_pullback_20x_mixed.example.toml`：

- BTCUSDT 使用 `brooks_pullback` 的 `1h` 入场。
- ETHUSDT 使用 `brooks_pullback` 的 `30m` 入场，并把 ATR/EMA/lookback 按时间尺度放大。
- 风控使用 20x 杠杆设置，但名义仓位上限为 `5x` 单标的、`8x` 总组合，不直接满 20x。

也可以参考 `config.brooks_price_action_20x_mixed.example.toml` 使用新的 Brooks price action 主策略。它不再是“Context -> Setup”的简单路由，而是：

```text
Market Context -> Candidate Trade -> Trader's Equation -> Trade Decision
```

默认仍只启用已验证的 `trend_pullback` 候选；`breakout_pullback` 和 `failed_breakout` 已实现为候选生成器，但需要研究配置显式启用，并且必须通过统一的 context/setup/signal/target/edge 分数门槛。

当前注册的策略类型：

- `breakout_atr`：原 4h ATR 突破策略，可选择是否启用 price action 过滤。
- `brooks_breakout`：Brooks 风格确认式突破，要求突破 K 合格后，下一根 K 有 follow-through 才入场。
- `brooks_pullback`：Brooks 风格顺势回调策略，用 4h market regime/Always-In 做方向过滤，用 1h H2/L2 近似、EMA 触碰和强信号 K 入场。
- `brooks_price_action`：新的 Brooks 核心策略。形态只生成候选交易，最终由 Context Scoreboard 和 Trader's Equation 决定是否入场。

`brooks_pullback` 的建议起点：

```toml
[[strategies]]
id = "brooks_pullback_1h"
name = "brooks_pullback"
fast_interval = "1h"
slow_interval = "4h"
atr_period = 14
stop_atr_multiple = 1.5
trail_atr_multiple = 2.5
profit_target_r_multiple = 2.0
trend_fast_ema = 50
trend_slow_ema = 200
brooks_always_in_threshold = 0.80
brooks_range_score_max = 0.55
brooks_climax_score_max = 0.80
brooks_pullback_entry_ema = 20
brooks_pullback_lookback = 12
brooks_pullback_min_depth_atr = 1.2
brooks_pullback_max_depth_atr = 4.0
brooks_pullback_ema_touch_atr = 0.6
brooks_pullback_require_ema_touch = true
brooks_pullback_min_legs = 2
brooks_pullback_min_signal_score = 0.75
```

回测 `brooks_pullback` 时需要同时准备 `1h` 快周期和 `4h` 慢周期数据。
单策略回测可以直接参考 `config.brooks_pullback.example.toml`。

`brooks_price_action` 的核心决策参数：

```toml
brooks_enable_trend_pullback = true
brooks_enable_breakout_pullback = false
brooks_enable_failed_breakout = false
brooks_breakout_min_quality_score = 0.50
brooks_breakout_min_retest_score = 0.45
brooks_breakout_min_control_score = 0.55
brooks_breakout_min_control_gap = 0.45
brooks_breakout_bear_max_bull_control = 0.60
brooks_breakout_bull_probability_base = 0.16
brooks_breakout_bear_probability_base = 0.10
brooks_breakout_bear_min_probability_score = 0.78
brooks_breakout_bear_min_edge_score_r = 0.35
brooks_failed_breakout_min_trap_score = 0.45
brooks_failed_breakout_min_break_distance_atr = 0.35
brooks_failed_breakout_entry_edge_zone = 0.45
brooks_failed_breakout_min_range_quality_score = 0.50
brooks_failed_breakout_min_reversal_score = 0.45
brooks_failed_breakout_max_opposite_control = 0.68
brooks_failed_breakout_min_two_sided_score = 0.35
brooks_failed_breakout_min_probability_score = 0.68
brooks_failed_breakout_min_edge_score_r = 0.50
brooks_trading_range_edge_zone = 0.25
brooks_decision_min_context_score = 0.55
brooks_decision_min_setup_score = 0.45
brooks_decision_min_signal_score = 0.60
brooks_decision_min_target_room_r = 1.50
brooks_decision_min_probability_score = 0.52
brooks_decision_min_edge_score_r = 0.00
brooks_decision_cost_r = 0.05
brooks_structural_stop_buffer_atr = 0.10
brooks_structural_stop_min_atr = 0.80
brooks_structural_stop_max_atr = 4.50
brooks_measured_move_target_fraction = 1.00
brooks_funding_crowding_threshold = 0.0
brooks_funding_extreme_threshold = 0.0003
brooks_funding_crowding_context_penalty = 0.25
brooks_funding_crowding_probability_penalty = 0.15
brooks_taker_buy_crowding_threshold = 0.58
brooks_taker_sell_crowding_threshold = 0.42
brooks_taker_crowding_extreme_distance = 0.18
brooks_open_interest_crowding_threshold = 0.002
brooks_open_interest_crowding_extreme = 0.020
brooks_external_crowding_context_penalty = 0.10
brooks_external_crowding_probability_penalty = 0.08
```

`brooks_price_action` 会优先使用结构化交易计划：

- 顺势回调的 invalidation 放在回调结构低点/高点外侧，并加 ATR buffer。
- Breakout pullback / failed breakout 启用后也必须生成结构化 stop/target plan，不能只凭场景触发。
- `brooks_price_action` 会收集同一根 K 上所有合格候选，按 edge/probability/context/setup 选择最佳候选，而不是按场景顺序抢先下单。
- Breakout pullback 现在要求突破方向有足够控制权和控制权差值；空头突破还会额外限制多头控制权，避免强多背景下机械追空。
- Breakout pullback 的多空概率先验已拆分；空头突破使用更低先验和更高最低 probability/edge 门槛。
- Failed breakout 仍不应默认启用；它必须证明区间边界质量、突破距离、区间边缘入场、反向触发和 trapped trader evidence。
- Failed breakout 使用更高的专用 probability/edge 门槛，因为它经常是逆趋势或区间交易，不能和顺势回调用同一条最低交易方程。
- 若结构止损距离低于 `brooks_structural_stop_min_atr`，会扩到最低 ATR 距离。
- 若结构止损距离超过 `brooks_structural_stop_max_atr`，候选交易会被丢弃。
- 目标价取 measured move 目标和配置 R 倍数目标中更近的有效目标，不用过远目标虚增 `target_room_r`。
- Funding 只作为同方向拥挤证据进入 Context Scoreboard；它不会创造候选交易，只会削弱 late/crowded 方向的 context 和 probability。
- OI/taker buy-sell 也只作为同方向主动成交和新仓拥挤证据；paper/live 使用 Binance 近期统计接口，回测只有在 K 线 CSV 包含 `taker_buy_volume` 时才使用 taker evidence。

如果希望测试更完整但仍受控的 Brooks 候选集，可以参考 `config.brooks_expanded_20x.example.toml`。该配置使用 20x 合约设置和 3% 单笔风险预算，默认启用 `trend_pullback` 与 `breakout_pullback`，但仍关闭尚未通过验证的 `failed_breakout`。

多策略 walk-forward 可使用：

```bash
PYTHONPATH=src python3 scripts/walk_forward_multi.py \
  --config config.brooks_expanded_20x.example.toml \
  --data-dir data/monthly_2025_now \
  --funding-dir data/monthly_2025_now \
  --equity 100 \
  --out reports/walk_forward_expanded_20x_100u.csv
```

## Funding 回测

历史资金费率通过 `scripts/fetch_funding.py` 下载，回测时用 `--funding-csv` 或 `--funding-dir` 计入。多头在正 funding 时付费，空头在正 funding 时收款；资金费率现金流会进入每笔交易 pnl、最终权益和最大回撤。

## Dry-run 实盘扫描

```bash
PYTHONPATH=src python3 scripts/live_rest_runner.py --config config.toml --symbol BTCUSDT --equity 1000
```

真实下单需要同时满足：

```bash
export CONFIRM_LIVE_TRADING=I_UNDERSTAND_RISK
PYTHONPATH=src python3 scripts/live_rest_runner.py --config config.toml --symbol BTCUSDT --equity 1000 --place-orders
```

默认会设置逐仓和配置里的杠杆，然后按最新 4h K 线生成一次交易计划。它不是常驻 daemon，适合先接 cron 或进程管理器前做人工验证。

当前下单实现按 Binance 单向持仓模式设计。Hedge Mode 需要显式补 `positionSide`，并且部分 reduce-only 参数规则不同。

## Paper Runner

常驻 paper runner 不会下真实订单，会把状态写入 JSON：

```bash
PYTHONPATH=src python3 scripts/paper_runner.py --config config.toml --symbols BTCUSDT ETHUSDT --state state/paper_state.json --once
```

去掉 `--once` 后按 `--poll-seconds` 持续轮询：

```bash
PYTHONPATH=src python3 scripts/paper_runner.py --config config.toml --symbols BTCUSDT ETHUSDT --state state/paper_state.json --poll-seconds 60
```

组合级风控：

- 单标的名义仓位不超过 `max_symbol_notional_fraction * equity`。
- 总名义仓位不超过 `max_total_notional_fraction * equity`。
- 每笔数量按 `risk_fraction * equity / stop_distance` 计算。
- 同一策略实例的同一标的同一时间只持一个方向。
- 只处理新的已收盘 K 线，重启后不会重复处理同一根 K 线。

## 测试

```bash
cd /Users/admin/Documents/Codex/2026-06-26/duao/outputs/binance_futures_quant
PYTHONPATH=src python3 -m unittest discover -s tests
```

## 参数敏感性扫描

先下载 BTC/ETH 的 4h K 线和 funding 数据到同一个目录，文件名使用 `BTCUSDT-4h.csv`、`ETHUSDT-4h.csv`、`BTCUSDT-funding.csv`、`ETHUSDT-funding.csv`，然后运行：

```bash
PYTHONPATH=src python3 scripts/grid_search.py --config config.toml --data-dir data --funding-dir data --out reports/grid_results.csv
```

默认训练集是 `2021-01-01` 到 `2025-01-01`，样本外是 `2025-01-01` 到 `2026-06-26`。

## Decision Score 分析

Brooks price action 会把 Context/Setup/Signal/Edge 分数写入交易记录。可以用分箱分析检查这些分数是否真的对应更好的交易结果：

```bash
PYTHONPATH=src python3 scripts/analyze_trade_scores.py --config config.brooks_price_action_20x_mixed.example.toml --data-dir data --funding-dir data --out reports/decision_score_bins.csv
```

当前分析结论见 [Decision Score Telemetry](reports/decision_score_telemetry.md)。

## Walk-forward

固定使用当前配置，不重新寻优：

```bash
PYTHONPATH=src python3 scripts/walk_forward.py --config config.toml --data-dir data --funding-dir data --out reports/walk_forward_funding.csv
```

默认窗口：

- 2021-2023 训练，2024 测试。
- 2022-2024 训练，2025 测试。
- 2023-2025 训练，2026 YTD 测试。
