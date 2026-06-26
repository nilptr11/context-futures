# Al Brooks Philosophy Reassessment

日期：2026-06-27

## 这次反思的结论

我们前一轮的方向只对了一半。

我们说“不要量化形态，要量化 Context”，这是对的。

但我们马上把 Context 做成：

```text
Trend -> Pullback
Breakout -> Breakout Pullback
Range -> Failed Breakout
```

这仍然太机械。它只是把“形态 if/else”升级成“场景 if/else”，还没有真正抓住 Brooks 的思想。

更接近 Brooks 的应该是：

```text
Market Hypothesis
  -> Evidence
  -> Probability
  -> Invalidation
  -> Trader's Equation
  -> Trade or No Trade
```

也就是说：

Brooks 不是在问：

```text
现在是什么状态，所以该用什么策略？
```

而是在问：

```text
谁在控制市场？
这个控制是否强？
如果我现在入场，哪些人会被迫跟随或退出？
我的风险、目标、胜率是否匹配？
如果市场证明我错了，在哪里错？
```

这是我们下一轮重构必须纠正的地方。

## 为什么“简单套场景”还是错的

我们把 Brooks 变成场景路由后，回测很快暴露问题：

| Router Branch | Result |
| --- | --- |
| trend pullback | 可用 |
| breakout pullback | 明显亏损 |
| failed breakout | 明显亏损 |
| all routes | 灾难性过度交易 |

这不是因为 Brooks 的 breakout pullback 或 failed breakout 思想错，而是因为我们把它们当成了“事件触发器”。

例如 failed breakout。

我们的第一版逻辑是：

```text
价格突破区间边界
又收回来
出现反向 K
交易
```

这仍然是形态化。

Brooks 语境下真正的问题应该是：

```text
这个区间是否足够真实？
突破前市场是否已经多次失败？
突破时是否吸引了足够多的错误方向交易者？
突破后是否没有 follow-through？
反向进入区间后，是否足以让突破交易者止损？
目标到区间中轴或另一侧是否有足够空间？
当前交易是否满足 trader's equation？
```

少了这些，failed breakout 就只是噪声反转。

## Brooks 的第一性原则

### 1. 市场不是形态集合，而是交易者行为

Brooks 的 price action 本质上是通过 K 线判断市场参与者行为：

- 谁在主动进攻；
- 谁在防守；
- 谁被套；
- 谁会止损；
- 谁会追单；
- 谁会在回调中进场。

量化翻译不是：

```text
识别 double top
识别 H2
识别 wedge
```

而是：

```text
识别哪一方控制市场，以及另一方是否被迫退出
```

我们应该把形态降级为 evidence，而不是 signal。

### 2. Context 是连续变量，不是枚举状态

我们现在用：

```text
TREND_UP
TRADING_RANGE
BREAKOUT_UP
CLIMAX_UP
```

这有用，但不够。

Brooks 的 Context 更像连续评分：

```text
trend_control = 0.72
range_pressure = 0.48
breakout_quality = 0.61
two_sided_trading = 0.35
climax_risk = 0.22
follow_through_strength = 0.67
```

然后交易不是由单个状态决定，而是由一组证据共同决定。

下一步应该从 FSM 转向：

```text
Context Scoreboard
```

状态机仍然可以保留，但只能作为可读标签，不应该作为唯一决策源。

### 3. Always-In 是控制权，不是趋势过滤器

我们之前把 Always-In 接近地实现成了趋势过滤。

更准确地说，Always-In 是：

```text
当前市场若必须选择方向，默认哪一方更有控制权？
```

它应该回答：

- 多头是否愿意在回调买入？
- 空头反弹是否很快失败？
- 反方向突破是否缺乏 follow-through？
- 价格是否持续拒绝进入另一方控制区？

因此 Always-In 不应该只是：

```text
EMA50 > EMA200
最近收盘在 EMA 上方
```

而应该包含：

```text
opposite_attempt_failure
pullback_holding_structure
follow_through_after_signal
time_above_value
breakout_failure_against_trend
```

### 4. Trading Range 不是“做震荡”，而是降低假设强度

Brooks 强调 trading range 很多，因为区间中大部分突破和方向判断都会失败。

对我们来说，正确翻译不是：

```text
Range -> 均值回归策略
```

而是：

```text
Range -> 降低趋势假设置信度
Range -> 禁止区间中部交易
Range -> 只考虑边缘、失败突破、足够 R/R
```

换句话说，Range 的默认动作应该是：

```text
No Trade
```

只有在非常具体的条件下，才允许 failed breakout。

### 5. Breakout 的关键不是突破，而是“之后发生了什么”

Brooks 对 breakout 的判断依赖：

- 突破 K 的强度；
- 是否远离区间；
- 是否有 follow-through；
- pullback 是否浅；
- 是否快速回到区间；
- 失败后谁被困住。

我们第一版 breakout pullback 失败，是因为只量化了：

```text
突破
回踩
信号 K
```

但没有量化：

```text
breakout quality
follow-through quality
old range re-entry depth
measured move room
failed breakout risk
```

所以它交易了太多“看起来像 breakout pullback、实际上只是区间噪声”的位置。

### 6. Trader's Equation 应该在入场前，而不是回测后

我们现在大多是在回测后看：

```text
profit factor
win rate
drawdown
```

Brooks 的思维方式更像是在每笔交易前问：

```text
如果我买入，止损在哪里？
合理目标在哪里？
胜率大概是否足以支撑这个 R/R？
这笔交易的最小目标是否足够支付手续费、滑点和 funding？
```

量化上应该新增：

```text
pre_trade_expected_r
distance_to_target_r
distance_to_invalidation_r
cost_r
minimum_required_win_probability
```

如果交易在入场前不满足 trader's equation，就不应该开仓。

### 7. 出场是 Brooks 体系的一部分，不是附属风控

我们把 `2R target` 加进去后结果明显改善，这说明之前的问题不只在入场。

Brooks 不会只问“哪里入场”，还会问：

- 目标是否是 measured move；
- 前高/前低是否会吸引获利了结；
- 区间中轴是否是磁铁位；
- trend channel 末端是否该降低目标；
- follow-through 失败是否该提前退出。

所以后续不应再只优化 entry。

策略结构应该是：

```text
Context -> Setup -> Entry -> Initial Stop -> Target Model -> Exit/Scale Model
```

而不是：

```text
Entry Signal -> ATR Stop -> Trail
```

## 对我们当前系统的批评

### 1. MarketRegime 过早离散化

现在的 `MarketRegime` 有用，但它把连续证据压缩成状态标签。

问题：

- `TREND_UP` 内部有强趋势、弱趋势、通道趋势、末端趋势；
- `TRADING_RANGE` 内部有宽区间、窄区间、突破模式、趋势后的盘整；
- `BREAKOUT_UP` 有有效突破和陷阱突破。

下一步应保留状态标签，但决策主要使用 scores。

### 2. Router 过早绑定策略

当前 Router 逻辑是：

```text
ContextState -> SetupKind
```

这仍然太硬。

更好的结构：

```text
ContextScoreboard -> CandidateSetups -> SetupScore -> TraderEquation -> TradeDecision
```

每个 setup 都应该自己打分，且必须通过 trader's equation。

### 3. Failed Breakout 没有理解“谁被困住”

failed breakout 的 alpha 不来自“价格回来了”。

它来自：

```text
错误方向交易者入场
市场不给 follow-through
他们被迫退出
反向交易者接管
```

我们需要量化 trapped trader。

可用近似：

- 突破后 N 根无 follow-through；
- 突破 K 之后快速收回；
- 收回时反向 K 强；
- 回到区间后继续反向 follow-through；
- crypto 中可加 funding/OI/taker buy-sell 作为拥挤度证据。

### 4. Breakout Pullback 没有验证突破质量

breakout pullback 的前提不是“发生过突破”，而是“突破足以改变市场共识”。

可用近似：

- breakout bar range >= `1.3 ATR`;
- close location 极强；
- 第二根 follow-through；
- 回调不超过突破 K 一半或不深回旧区间；
- 回踩后 signal bar 有足够目标空间；
- old resistance/support 转换成功。

### 5. 加密衍生品证据还没有进入 Context

Brooks 主要读 price action。

Crypto 有额外 evidence：

- funding；
- open interest；
- taker buy/sell volume；
- CVD proxy；
- liquidation stream。

但这些不能直接变成信号。

它们应该回答：

```text
这个 breakout 是否拥挤？
这个 trend 是否由新仓推动？
这个反转是否是强平/止损驱动？
这个方向是否 late?
```

## 下一轮正确重构方向

### 从 FSM 改成 Context Scoreboard

新增或重构：

```text
context_scoreboard.py
```

输出：

```text
trend_control_bull
trend_control_bear
range_pressure
breakout_quality_up
breakout_quality_down
follow_through_quality
pullback_quality
exhaustion_risk
trapped_long_risk
trapped_short_risk
target_room_r
cost_r
```

### 每个 setup 只产生 Candidate，不直接产生 Signal

例如：

```text
CandidateSetup(
    kind="breakout_pullback",
    side=LONG,
    context_score=0.72,
    setup_score=0.68,
    signal_score=0.75,
    invalidation_price=...,
    target_price=...,
    expected_r=...
)
```

然后统一由：

```text
TradeDecisionEngine
```

决定是否交易。

### 新的入场门槛

不再是：

```text
if setup:
    trade
```

而是：

```text
if context_score >= threshold
and setup_score >= threshold
and signal_score >= threshold
and expected_r > 0
and target_room_r >= 1.5
and cost_r acceptable:
    trade
```

### 先不扩大场景，先提高决策质量

我们现在最容易犯的错误是：

```text
再加更多 Brooks setup
```

但更正确的是：

```text
让每一个 setup 先具备完整的 Context + Trader's Equation
```

因此下一步不应新增更多形态。

应该先改：

1. `ContextScoreboard`
2. `CandidateSetup`
3. `TradeDecisionEngine`
4. `TargetModel`
5. `InvalidationModel`

## 对当前策略的重新定位

### `brooks_pullback`

现在它不是完整 Brooks 策略。

它只是：

```text
Trend Context + Pullback Candidate
```

可继续保留，但应该改造成 Candidate 生成器。

### `brooks_price_action`

它取代了上一版 `brooks_context_router`。

它不再使用：

```text
ContextState -> SetupKind -> Signal
```

而是使用：

```text
MarketContext -> Candidate Trade -> Trader's Equation -> TradeDecision
```

这次重构已经完成第一步：

- `ContextScoreboard` 负责读盘和方向控制权评分；
- `TradeCandidate` 负责承载形态证据；
- `TradeDecision` 统一检查 context、setup、signal、target room、cost 和 edge；
- `brooks_price_action` 默认只启用已验证的 trend pullback 候选。

旧 `brooks_context_router` 策略名不再保留为兼容 alias。

### `breakout_pullback` 和 `failed_breakout`

不能直接启用。

下一步需要补：

- trapped trader evidence；
- follow-through evidence；
- measured move target；
- cost-adjusted expected R；
- crypto crowding evidence。

## 最终结论

用户这句判断是对的：

```text
我们应该回头仔细分析 Brooks 的思想，而不是简单套场景。
```

前一轮 Router 的失败不是坏事，它说明：

```text
Context 不是标签；
Pattern 不是信号；
Setup 不是交易；
状态路由不等于 Brooks；
交易必须通过 Context + Probability + Risk/Reward。
```

下一轮真正的重构方向应该是：

```text
Context Scoreboard
  -> Candidate Setup
  -> Trader's Equation
  -> Trade Decision
  -> Target / Invalidation / Management
```

而不是：

```text
Market State
  -> Strategy
  -> Trade
```

## 参考来源

- Brooks Trading Course, Price Action Fundamentals: https://www.brookstradingcourse.com/trade-price-action/
- Brooks Trading Course, Price Action Glossary: https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
- Brooks Trading Course, Trading Ranges: https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
- Brooks Trading Course, 10 Best Price Action Trading Patterns: https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
- Brooks Trading Course, Brooks Price Action Abbreviations: https://www.brookstradingcourse.com/brooks-price-action-abbreviations/
- Brooks Trading Course forum, Always In discussion: https://www.brookstradingcourse.com/support-forum/13-always-in/always-in-confusion/
- Brooks Ask Al, Trading Range Days: https://www.brookstradingcourse.com/ask-al/trading-range-day-two-legs-swing/
