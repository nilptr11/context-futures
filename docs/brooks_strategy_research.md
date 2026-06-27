# Brooks 策略研究总览

日期：2026-06-27

本文是 Al Brooks 策略研究的唯一长期文档。

## 文档结构和维护边界

Brooks 相关文档只保留本文。

原因：

- 当前代码只能视为 Brooks-inspired 的研究实现，不能因为某些回测结果就宣称已经贯彻 Brooks。
- 分散的验证、遥测、激进风险文档容易让读者把局部结果误读成策略原则。
- Brooks 思想吸收、实现约束、证据边界和后续路线必须在同一处维护。

维护规则：

- 不再新增 Brooks 专题文档。
- 回测 CSV、临时分箱和扫描结果留在 `reports/` 或本地实验输出，不作为长期策略文档。
- 本文可以记录关键历史结果，但只能作为研究线索，不能作为“已经符合 Brooks”的证明。
- 若后续发现当前策略只是固定模型套用，应优先修改本文判断，再改代码。

## 核心判断

Brooks 的核心不是形态识别，也不是场景路由，而是交易前的市场阅读：

```text
市场上下文
  -> 证据
  -> 候选交易
  -> Invalidation
  -> 目标空间
  -> Trader's Equation
  -> 交易 / 不交易
```

因此，策略实现必须避免两类错误：

- 把 H2/L2、wedge、breakout、failed breakout 直接当作开仓信号。
- 为了增加交易数，直接打开更多 setup，而不检查目标空间、成本、胜率和结构止损。

## 官方材料复核后的补充理解

复核来源：

- Brooks Trading Course: How to trade price action manual
  - https://www.brookstradingcourse.com/how-to-trade-price-action-manual/
- Brooks Trading Course: Price action and candlestick charts
  - https://www.brookstradingcourse.com/how-to-trade-manual/candlestick-charts/
- Brooks Trading Course: Importance of institutional trading
  - https://www.brookstradingcourse.com/how-to-trade-manual/institutional-trading/
- Brooks Trading Course: Trading ranges
  - https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
- Brooks Trading Course: Beginners should enter with stop orders
  - https://www.brookstradingcourse.com/how-to-trade-manual/stop-orders/
- Brooks Trading Course: 10 best price action trading patterns
  - https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/

官方材料强化了几个约束：

1. Brooks 的核心是市场循环和交易结构，不是形态库。
   - 先判断市场处于 trend、channel、breakout 还是 trading range。
   - 再用 stop、target、position size 和 trade management 构造正期望交易。
   - 因此，`probability_score` 不能被当成独立预测模型，它必须解释为某个市场循环阶段下的条件概率估计。

2. 市场不是单边真相，而是多空机构都能赚钱的交易场。
   - 每一笔交易都有机构在对手方。
   - 高概率通常以差风险收益为代价，低概率也可能通过高回报成立。
   - 因此，策略不能只问“方向是否正确”，还必须问“这个 entry/stop/target 是否给出了合理的 Trader's Equation”。

3. 默认概率应该保守。
   - 多数时间，等距上下目标的概率接近均衡区间。
   - 只有强 breakout、强 trend continuation 等少数环境才应显著提高 continuation 概率。
   - 因此，当前启发式 `probability_score` 后续需要按 setup_kind、side、symbol、regime 校准，避免看起来精确但没有统计含义。

4. Trading range 不是简单的“均值回归策略”。
   - 宽区间可以 buy low / sell high / scalp。
   - 紧区间多数交易者应不交易，等待 breakout 或明确边缘。
   - 区间中部仍应默认禁止交易。
   - 因此，本文继续禁止把 range fade 做成网格化生产策略；若研究，只能作为边缘、失败突破、scalp target 的独立分支。

5. H2/L2、wedge、double top/bottom 的意义是“反方尝试失败后的压力变化”。
   - H2/L2 不只是第二次突破前高/前低。
   - 它背后是趋势中的反向尝试失败，反向交易者开始退出。
   - 因此，`pullback_min_legs` 只是近似，后续应补“反方失败强度”和“失败后速度”指标。

6. Measured move、support/resistance、magnet 是目标空间，不只是出场装饰。
   - 目标应回答“市场下一步最可能测试哪里”。
   - 如果目标空间不足，即使 setup 好也不应交易。
   - 因此，`target_room_r` 应继续保留为硬门槛，并逐步从固定 R 转向结构目标和 magnet 目标。

对当前文档的调整结论：

- 文档主线应坚持“context > setup > trader's equation”，但当前代码仍需要持续审计是否真的做到。
- 需要加强“市场循环动态”和“交易结构 trade-off”，避免把 Brooks 精髓压扁成固定加权评分。
- 后续新增特征必须能回答：它是在识别市场循环、机构控制权、反方失败、目标空间，还是风险收益结构。

## 交易原则

### 0. 市场循环先于 setup

Brooks 的 price action 先读市场循环，再读具体 setup。

```text
trend / channel / breakout / trading range
  -> 当前阶段中的主导交易结构
  -> entry / stop / target 是否成立
```

实现要求：

- `regime` 不能只是趋势过滤器，必须解释当前市场循环阶段。
- `probability_score` 必须依附于 `setup_kind + side + symbol + regime`，不能被解释成全局胜率。
- 同一个形态在 trend、channel、trading range 中含义不同，不能共用同一套无条件权重。

当前实现：

- 已有 `MarketRegimePoint` 和 `ContextState`。
- 已有 `setup_kind` 诊断字段。
- 已有第一版 market structure read：support/resistance、range midpoint、range position、breakout transition、two-sided transition。
- 仍缺 channel strength、breakout failure speed 等更细子项。

### 1. 先判断谁在控制市场

Brooks 的第一问题不是“有没有形态”，而是：

```text
多头还是空头在控制？
控制权强不强？
反方尝试是否失败？
```

实现要求：

- `Always-In` 必须表示控制权，不只是 EMA 趋势过滤。
- 多空控制权要有差值，不能只看单边分数。
- 反方向失败、follow-through、time above/below value 后续要进入评分。

当前实现：

- 已有 `always_in_bull_score` / `always_in_bear_score`。
- 已有 `control_gap`。
- pullback 已记录 double test / wedge push，failed breakout 已记录 trap score / range quality。
- 反方向失败后的速度、time above/below value 和 liquidation 证据仍需继续补。

### 2. Context 是连续证据，不是交易开关

`ContextState` 只能是标签，不能写成：

```text
if state == X:
    trade
```

当前 `brooks_price_action` 已从旧 router 改为：

```text
MarketContext
  -> SetupEvaluation
  -> PlannedTrade
  -> TradeCandidate
  -> Trader's Equation
  -> TradeDecision
  -> Signal / BrooksDecisionRecord
```

### 3. 形态只是证据，不是信号

H2、L2、wedge、double test、breakout、failed breakout 都只能产生候选交易。

```text
形态 -> 候选交易 -> Trader's Equation -> 交易 / 不交易
```

当前实现：

- `PullbackSignal` 和 `SetupSignal` 只进入候选交易。
- `Signal` 只在 `TradeDecision.accepted` 后生成。

### 4. Trading Range 默认 No Trade

Brooks 对 trading range 的提醒不是“做均值回归”，而是“多数方向判断会失败”。

实现要求：

- trend pullback 不允许在 range 中自动开仓。
- range 中只允许非常具体的边缘/失败突破候选。
- 区间中部交易默认禁止。

当前实现：

- `candidate_kinds_for_context` 对 trend pullback 有 range gate。
- failed breakout 默认关闭。
- 测试已保护 range 默认不会产生 trend pullback 候选。

### 5. Breakout 看后续，而不是看突破本身

breakout 的关键是：

```text
breakout 后是否有 follow-through？
是否改变市场共识？
回踩是否守住？
```

实现要求：

- 突破 K 不能单独成为信号。
- breakout pullback 必须有突破质量、回踩质量、目标空间。
- 没有 follow-through 的 breakout 更接近 failed breakout 证据链。

当前状态：

- breakout pullback 可作为研究候选，但不应默认生产启用。
- 当前候选评分已纳入 breakout quality、retest、follow-through、market-structure magnet 和 breakout transition。
- 仍需按多空、标的、market cycle 验证这些证据是否单调有效。

### 6. Failed Breakout 必须证明 trapped traders

Failed breakout 的 alpha 不来自“价格回来了”，而来自错误方向交易者被困。

实现要求：

- range 边界真实。
- 突破后缺乏 follow-through。
- 回到区间后有反向强度。
- 目标到区间中轴或另一边有足够空间。
- 加密永续中应加入 funding/OI/taker/liquidation 作为拥挤度证据。

当前状态：

- failed breakout 默认关闭。
- 当前实现已有 `failed_breakout_trap`、`failed_breakout_range_quality` 和 two-sided transition 证据。
- 这些证据仍只是候选层 proxy，必须通过 decision journal 分桶验证后才能启用。

### 7. 入场前先定义在哪里错

Brooks 的交易必须有 invalidation。

实现要求：

- 顺势回调用结构高低点做 invalidation。
- 不能只因为 ATR 止损方便就忽略结构。
- 结构止损太远时跳过交易，而不是硬做。

当前实现：

- 已实现顺势回调结构止损。
- 回测执行优先使用 signal 计划价格。
- breakout/failed breakout 已使用 setup window high/low 作为结构止损基础。
- 更高阶的 invalidation，例如 breakout level reclaim/loss、major higher low/lower high，仍需继续研究。

### 8. Trader's Equation 必须在最终入口

交易不是“信号出现”，而是：

```text
概率 * 回报 - 风险 - 成本 > 阈值
```

实现要求：

- context、setup、signal、location、target room、cost 都要进入决策。
- 单个指标不能绕过决策层。
- 不优化单一胜率；高胜率低 R 和低胜率高 R 必须用同一 Trader's Equation 比较。
- 回测调参不能把 `decision_min_edge_score_r` 变成摆设。

当前状态：

- 已有 `probability_score` 和 `edge_score_r`。
- 当前 `probability_score` 仍是启发式 proxy，不是真实概率，需要用样本统计校准。
- 目标空间保留 measured move、breakout measured move、range midpoint/edge 和 fixed R fallback。
- support/resistance magnet 当前只作为 market-structure telemetry；在没有分桶校准前，不允许改变 `probability_score`、目标价或持仓路径。
- 目标选择使用最近有效目标；`target_room_r` 是否足够由 `TradeDecision` 统一拒绝，不能为了满足最小 R 自动跳到更远目标。

## 当前实现

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

当前代码边界：

- `context.py`：只负责 market read、market cycle、overlay、主方向和 setup 是否值得扫描。
- `structure.py`：只负责 support/resistance、range midpoint/edge、market-cycle transition 和 magnet target，不检测 setup。
- `scanner.py`：统一扫描 trend pullback、breakout pullback、failed breakout，并产出 `SetupEvaluation`；真实交易和研究日志共用这一层。
- `trade_plan.py`：负责 structural stop、target model 和 target room。
- `evidence.py`：负责 `EvidenceLedger`，让 control、context、setup、signal、location、target、crowding 和 Trader's Equation 证据成为一等对象。
- `decision.py`：负责 `ContextScoreboard`、`TradeCandidate`、`TraderEquation` 和 `TradeDecision`；context score 和 probability proxy 由 evidence ledger 汇总，structure/trapped trader 证据在校准前只进入候选 telemetry。
- `diagnostics.py`：把 context/candidate 转成可落盘 telemetry。
- `journal.py`：把 `SetupEvaluation` 转成 `BrooksDecisionRecord`。
- `strategy.py`：只做编排：读盘、扫描、选择 accepted candidate 并生成 `Signal`。

当前默认可用分支：

- `trend_pullback`：当前研究起点，但仍需继续用 Brooks 语义校准。
- `trend_pullback` 允许在 trend、channel、breakout continuation 中进入候选；channel 是趋势的通道阶段，不应被简单排除，但仍必须通过 range、climax、always-in、pullback setup 和 Trader's Equation 门槛。

当前研究候选：

- `breakout_pullback`：只作为研究候选；即使历史回测改善，也必须按多空、标的、market cycle 和 follow-through 重新证明。
- `failed_breakout`：暂不启用；代码已有 trap/range/two-sided 证据，但必须先证明 trapped traders 证据链在样本中有效。
- `channel` 不单独作为 setup；它是 market cycle。channel pullback 可以由 `trend_pullback` 扫描，但后续仍需单独分桶验证 channel strength、两边交易性和目标空间。

当前已完成工程基础：

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

当前诊断 telemetry 已包括：

- raw regime、market cycle、market overlay、context state、context direction。
- range/two-sided/breakout 分数。
- control score、control gap、trend alignment、follow-through、anti-range、anti-climax。
- support、resistance、midpoint、range position、breakout transition、two-sided transition、magnet target score。
- target model、stop distance、Trader's Equation cost。
- funding/taker/OI/external crowding。

`cf-backtest` 和 `cf-portfolio-backtest` 支持三类 Brooks 研究输出：

- `--brooks-out`：基于已成交 trades 的 bucket summary。
- `--brooks-decisions-out`：基于候选评估的 decision journal，包含 accepted/rejected 和拒绝原因。
- `--brooks-decisions-summary-out`：基于 decision journal 的聚合研究表，按 market cycle、raw regime、setup、side、decision reason 等维度汇总。
- `--brooks-research-setups`：只影响 decision journal，额外探测当前配置中禁用的 setup 分支，并用 `setup_enabled=false` 标记。

这些报告只用于分桶研究，不能单独作为策略启用或参数放松依据。`--brooks-decisions-out` 不是执行复盘，不代表账户在已有仓位时一定会再次尝试开仓；它用于研究市场阅读、候选 setup 和 Trader's Equation 的拒绝路径。
`--brooks-research-setups` 不改变回测交易，不等于启用 breakout、failed breakout 或任何生产分支。

## 加密市场证据

Crypto 数据只能作为上下文证据，不能直接创造交易。

当前已支持：

- funding：削弱同方向拥挤。
- taker buy ratio：识别同方向主动成交拥挤。
- open interest change：辅助判断新仓拥挤。

当前仍缺：

- liquidation spike / stop-run 证据。
- 更长历史的 OI/taker 数据。
- 对 failed breakout 中 trapped traders 的统计验证。

接入纪律：

- funding 高只能说明拥挤或 late risk。
- OI 增减必须结合价格方向解释。
- taker imbalance 只能削弱追随拥挤方向，不能给反向交易直接加分。
- liquidation 要判断是 climax、stop-run，还是普通波动。

## 策略族优先级

### 第一优先级

- `trend_pullback`：当前优先研究路径，不等同于已经完整贯彻 Brooks。
- `brooks_price_action` 的结构止损和 Trader's Equation：继续完善。
- setup 专属校准：按 setup_kind、side、symbol、regime 分桶。

### 第二优先级

- `breakout_pullback`：验证 breakout quality、follow-through、retest quality、transition 和 target room 的分桶表现。
- measured move / structure magnet target：继续用于目标空间和出场过滤，并验证不同 target model。
- crypto crowding evidence：用于 late/crowded 风险惩罚。

### 暂不启用

- `failed_breakout`：证据链不足。
- trading range fade：容易退化成区间网格。
- major trend reversal / climax reversal：逆势误判风险高，先做过滤器或退出逻辑。

## 历史回测线索和证据边界

以下结果只说明当前实现和当前配置在本地数据上的历史表现，不证明策略已经贯彻 Brooks 思想。

组合回测数据目录采用结构化布局：

```text
data/<exchange_market>/<dataset>/<SYMBOL>/<YEAR>/<SYMBOL>-<interval>.csv
data/<exchange_market>/<dataset>/<SYMBOL>/<YEAR>/<SYMBOL>-funding.csv
```

当前通用 Binance USD-M 研究数据集为 `data/binance_usdm/perpetual_futures/`，已按 BTCUSDT、ETHUSDT、NEARUSDT 和 2024/2025/2026 拆分。每个标的维护 `15m`、`1h`、`4h` 和 funding；ETH 额外保留 `30m` 以支持当前配置。数据按市场和数据集维护，不按策略维护；回测年份由 `--start` / `--end` 控制，更新数据时只更新最新年份目录。

### 常规风险配置

当前参考配置：

- `configs/strategies/brooks/price_action_portfolio.toml`
- BTCUSDT `1h/4h`
- ETHUSDT `30m/4h`
- `risk_fraction = 0.02`

本地历史复核线索：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-27 | 48.46% | -6.68% | 33 | 60.61% | 2.513 |
| 2025-01-01 到 2026-06-27 | 28.17% | -5.84% | 18 | 66.67% | 2.872 |

证据边界：

- 交易数太少，不能证明长期稳定性。
- 只说明 `trend_pullback` 作为研究起点有继续分析价值。
- 不证明 breakout/failed breakout 可以启用。
- 不证明当前 `probability_score` 是真实概率。

### Breakout Pullback 研究配置

`configs/strategies/brooks/breakout_pullback_research.toml` 只作为 breakout pullback 研究配置。

该配置在常规配置基础上启用 breakout pullback，并收紧 breakout quality、retest quality、control score、control gap、bear probability 和 bear edge 门槛。

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-27 | 67.15% | -8.05% | 64 | 53.12% | 1.964 |
| 2025-01-01 到 2026-06-27 | 34.26% | -7.38% | 38 | 52.63% | 1.896 |

研究结论：

- breakout pullback 有独立研究价值，但当前利润因子和胜率弱于 `trend_pullback`。
- 直接宽松启用 breakout pullback 会明显放大回撤；严格配置更适合作为研究起点。
- 空头 breakout 样本更少，不能因为少数高 R 交易就放松阈值。
- 该配置不能替代 `price_action_portfolio.toml` 作为当前维护默认配置。

### 激进风险配置

`configs/strategies/brooks/aggressive_15pct.toml` 只作为风险放大实验，不作为 Brooks 策略证明。

当前结构化数据集 `data/binance_usdm/perpetual_futures/`，2025-01-01 到 2026-06-27 共享账户回测：

| 指标 | 数值 |
| --- | ---: |
| 初始权益 | 100.00 |
| 最终权益 | 6707.49 |
| 总收益率 | 6607.49% |
| 最大回撤 | -59.10% |
| 交易数 | 101 |
| 胜率 | 56.44% |
| 利润因子 | 1.641 |
| 资金费率 | 11.62 |

本轮重构复盘结论：

- `aggressive_15pct` 是高风险回归基线；新架构必须先复现或接近旧收益路径，再讨论是否继续引入 Brooks 结构证据。
- 错误重构曾把未校准的 structure/setup 证据直接加入 `probability_score`，并让 structure magnet 改变目标选择，导致回测退化到最终权益 `1466.55`、回撤 `-66.60%`、交易数 `133`、胜率 `50.38%`、利润因子 `1.290`。
- 修复后只回到 `5602.93` 的剩余差距来自 channel 被错误排除在 trend pullback 之外；2026-02-10 的两笔 NEARUSDT channel pullback 高质量交易被跳过。
- Brooks 语义下 channel 仍是趋势结构的一种表现；把 channel 纳入 `trend_pullback` 扫描后，101 笔交易 entry/exit/setup 与归档报告完全匹配，PnL 汇总为 `6607.48623732`。
- 后续任何 Brooks 新证据必须先以 telemetry 和 decision journal 分桶验证；未校准前不得改变 Trader's Equation、target selection 或 position path。

分年独立回测线索：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 | 资金费率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2025-01-01 | 73.85% | -50.81% | 59 | 45.76% | 1.131 | -6.71 |
| 2025-01-01 到 2026-01-01 | 1809.23% | -43.31% | 71 | 57.75% | 1.585 | 2.25 |
| 2026-01-01 到 2026-06-27 | 251.32% | -56.38% | 30 | 53.33% | 1.665 | 0.49 |

结论：

- 可作为研究配置。
- 不应直接用于实盘。
- 该结果主要说明风险预算可以放大收益和回撤，不证明策略具备稳定月收益 50%-100% 的生产能力。
- 不能用该结果反向合理化放松 Brooks 条件。

## 决策分数研究

现有样本观察：

- `context_score` 有正向意义，但不是线性越高越好。
- `probability_score >= 0.75` 目前更有优势，但样本不足。
- `edge_score_r` 高分区有优势，中间区间非单调。
- `setup_score` 公式需要重审，可能混合了不同 pullback 类型。

解释纪律：

- `probability_score` 在校准前只能叫概率 proxy，不能当作真实胜率。
- `EvidenceLedger` 只能说明当前公式如何合成分数，不能自动证明证据有效。
- 每个分数必须能拆成 Brooks 语义：market cycle、control、failed attempt、follow-through、location、target room、crowding。
- 任何分数如果跨 setup_kind 或 regime 后表现非单调，先拆分样本，不直接调高/调低权重。

后续研究方式：

1. 用 `EvidenceLedger` 按证据项导出分桶报告，验证 control、follow-through、location、crowding 等子项是否单调。
2. 单独分析 setup 构成：深度、腿数、EMA 触碰、double test、wedge、反方失败速度。
3. 用 decision journal 分析 accepted/rejected 的分布，再按 `setup_kind`、side、symbol、regime、market-cycle transition 分桶。
4. 分析不同 target 模型：固定 R、measured move、range midpoint、range edge、major high/low magnet。
5. 再决定是否调整 `decision_min_probability_score` 或 `decision_min_edge_score_r`。

## 后续路线

1. 暂以 `trend_pullback` 为研究起点，不急着增加更多 setup。
2. 先用 decision journal 研究 no-trade、channel、breakout、breakout mode、trading range、neutral、overlay 的分布。
3. 将 `breakout_pullback` 拆成多空、标的、regime、follow-through 分桶验证。
4. 验证 failed breakout 的 trapped trader 证据链：trap score、range quality、two-sided transition、回到区间后的反向强度和拥挤证据。
5. 验证 structure telemetry：range midpoint、range edge、support/resistance magnet、measured move 和 fixed R fallback；只有证明单调有效后，magnet 才能进入目标选择。
6. 用代码生成 setup performance、score calibration、target model 报告，而不是恢复旧脚本。
7. 接入更可靠的历史 OI/taker/liquidation 数据后，再验证 crypto crowding evidence。
8. 所有策略增强必须同时通过 Brooks 逻辑检查和未来函数检查。

## 实现纪律

每次新增功能前先写清楚：

```text
Brooks 逻辑依据：
这个改动回答 control/context/trapped traders/follow-through/invalidation/trader's equation 中的哪一个？

市场循环检查：
这个改动在 trend/channel/breakout/trading range 中分别代表什么？是否错误地跨 regime 共用同一含义？

分数解释检查：
这个分数是未校准 proxy 还是真实统计概率？它能否按 setup_kind/side/symbol/regime 分桶验证？

未来函数检查：
这个改动在 idx 时刻能否真实获得？

回归验收检查：
aggressive_15pct 在 2025-01-01 到 2026-06-27 是否仍能复现或接近 6707.49 final equity、101 trades、56.44% win rate、1.641 profit factor？
```

如果任一问题答不清楚，就不进入策略核心。
