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
- 缺少 market-cycle transition、channel strength、breakout failure speed 等可解释子项。

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
- 反方向失败证据仍偏弱，后续需要补。

### 2. Context 是连续证据，不是交易开关

`ContextState` 只能是标签，不能写成：

```text
if state == X:
    trade
```

当前 `brooks_price_action` 已从旧 router 改为：

```text
ContextScoreboard
  -> 候选 Setup
  -> 上下文 / Setup / 信号 / 位置分数
  -> 目标空间和成本
  -> 概率分数和 Edge 分数
  -> 接受或拒绝
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
- 当前候选评分仍需补完整 trapped trader、follow-through 和结构目标。

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
- 当前实现还没有充分 trapped trader evidence。

### 7. 入场前先定义在哪里错

Brooks 的交易必须有 invalidation。

实现要求：

- 顺势回调用结构高低点做 invalidation。
- 不能只因为 ATR 止损方便就忽略结构。
- 结构止损太远时跳过交易，而不是硬做。

当前实现：

- 已实现顺势回调结构止损。
- 回测执行优先使用 signal 计划价格。
- breakout/failed breakout 还没有结构化 invalidation。

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
- 当前目标空间仍偏固定 R，应逐步补 support/resistance、measured move、magnet 目标。

## 当前实现

当前主策略是 `brooks_price_action`。

它取代了旧 `brooks_context_router`，不再保留兼容 alias。旧模型：

```text
ContextState -> SetupKind -> Signal
```

新模型：

```text
MarketContext -> 候选交易 -> Trader's Equation -> TradeDecision
```

当前默认可用分支：

- `trend_pullback`：当前研究起点，但仍需继续用 Brooks 语义校准。

当前研究候选：

- `breakout_pullback`：只作为研究候选；即使历史回测改善，也必须按多空、标的、market cycle 和 follow-through 重新证明。
- `failed_breakout`：暂不启用，必须先证明 trapped traders。

当前已完成工程基础：

- `SignalDiagnostics` 保存 Brooks 决策分数。
- `Trade` 保留 `entry_reason`、`exit_reason`、`setup_kind` 和诊断分数。
- `context_futures.reporting.write_trades_csv` 展平诊断字段。
- `ExecutionEngine` 统一执行结构止损、目标价、费用、滑点和 funding。

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

- `breakout_pullback`：补 breakout quality、follow-through、retest quality、target room。
- measured move target：用于目标空间和出场过滤。
- crypto crowding evidence：用于 late/crowded 风险惩罚。

### 暂不启用

- `failed_breakout`：证据链不足。
- trading range fade：容易退化成区间网格。
- major trend reversal / climax reversal：逆势误判风险高，先做过滤器或退出逻辑。

## 历史回测线索和证据边界

以下结果只说明当前实现和当前配置在本地数据上的历史表现，不证明策略已经贯彻 Brooks 思想。

### 常规风险配置

当前参考配置：

- `configs/strategies/brooks/price_action_portfolio.toml`
- BTCUSDT `1h/4h`
- ETHUSDT `30m/4h`
- `risk_fraction = 0.02`

本地历史复核线索：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-26 | 48.46% | -6.68% | 33 | 60.61% | 2.513 |
| 2025-01-01 到 2026-06-27 | 28.17% | -5.84% | 18 | 66.67% | 2.872 |

证据边界：

- 交易数太少，不能证明长期稳定性。
- 只说明 `trend_pullback` 作为研究起点有继续分析价值。
- 不证明 breakout/failed breakout 可以启用。
- 不证明当前 `probability_score` 是真实概率。

### 激进风险配置

`configs/strategies/brooks/aggressive_15pct.toml` 只作为风险放大实验，不作为 Brooks 策略证明。

2025-01-01 到 2026-06-27 共享账户回测：

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
- 每个分数必须能拆成 Brooks 语义：market cycle、control、failed attempt、follow-through、location、target room、crowding。
- 任何分数如果跨 setup_kind 或 regime 后表现非单调，先拆分样本，不直接调高/调低权重。

后续研究方式：

1. 将 `probability_score` 拆成可解释子项。
2. 单独分析 setup 构成：深度、腿数、EMA 触碰、double test、wedge、反方失败速度。
3. 按 `setup_kind`、side、symbol、regime、market-cycle transition 分桶。
4. 分析不同 target 模型：固定 R、measured move、range midpoint、range edge、major high/low magnet。
5. 再决定是否调整 `decision_min_probability_score` 或 `decision_min_edge_score_r`。

## 后续路线

1. 暂以 `trend_pullback` 为研究起点，不急着增加更多 setup。
2. 先补 market-cycle telemetry：trend、channel、breakout、trading range、transition。
3. 将 `breakout_pullback` 拆成多空、标的、regime、follow-through 分桶验证。
4. 为 failed breakout 补完整 trapped trader 证据链，尤其是突破失败速度、回到区间后的反向强度和拥挤证据。
5. 重建 research 模块，用代码生成 setup performance、score calibration、target model 报告，而不是恢复旧脚本。
6. 接入更可靠的历史 OI/taker/liquidation 数据后，再验证 crypto crowding evidence。
7. 所有策略增强必须同时通过 Brooks 逻辑检查和未来函数检查。

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
```

如果任一问题答不清楚，就不进入策略核心。
