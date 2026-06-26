# Al Brooks Core Deep Research and Strategy Adjustment

日期：2026-06-27

## 结论先行

我们不应该把 Brooks 简化成“强 K 过滤”或“突破后等一根 follow-through”。这只是很小一部分。

Brooks 核心更像一个市场状态机：

1. Trading range
2. Breakout
3. Trend breakout phase
4. Pullback
5. Trend channel phase
6. Increasing two-sided trading
7. Back to trading range

因此，我们当前最应该调整的方向是：

**从纯突破策略，转向 4h 识别市场状态 + 1h 做顺势回调入场。**

也就是：

- 4h 判断是否有 Always-In 方向。
- 4h 判断是否处于 trading range，处于 range 时不做趋势追单。
- 1h 等 Brooks 风格回调结束信号。
- 优先做 H2/L2 或 breakout pullback，而不是追所有 breakout。

## Brooks 核心一：Market Cycle

Brooks 的交易不是形态列表，而是市场周期判断。

官方 trading range 资料明确描述了趋势和交易区间之间的循环：趋势通常从 breakout 开始，pullback 出现后从 breakout phase 转向 trend channel phase，随后双向交易增加并演化成 trading range。

量化翻译：

```text
TRADING_RANGE
  -> breakout with strong bar / follow-through
BREAKOUT_PHASE
  -> first pullback
TREND_CHANNEL
  -> two-sided trading increases
TRADING_RANGE
```

我们当前的问题：

- `breakout_atr` 只看突破和 EMA 方向。
- `brooks_breakout` 只看突破 + follow-through。
- 两者都没有显式建模 market cycle。

应该新增：

- `MarketRegime`
  - `TRADING_RANGE`
  - `BREAKOUT_UP`
  - `BREAKOUT_DOWN`
  - `TREND_UP`
  - `TREND_DOWN`
  - `CHANNEL_UP`
  - `CHANNEL_DOWN`
  - `BREAKOUT_MODE`

## Brooks 核心二：Always In

Always In 不是“永远持仓”，而是强趋势环境下的方向判断。

官方论坛中对 Always In 的一个重要描述是：它适用于强趋势，不适用于 trading range；通常从 breakout 开始，之后趋势阶段适合在 pullback 入场。

量化翻译：

Always-In Bull：

- 有强 breakout 或连续趋势 K；
- EMA50 > EMA200；
- 最近 pullback 没有破坏趋势结构；
- 价格多数时间在 EMA 上方；
- 不是 tight trading range。

Always-In Bear 对称。

对我们策略的影响：

- 不应该只用 EMA50/EMA200 作为趋势过滤。
- 应该用 Always-In 状态决定是否允许顺势交易。
- 进入 Always-In 后，更好的入场不是追每次突破，而是等 pullback。

## Brooks 核心三：Trading Range 优先级很高

Brooks 对 trading range 的判断非常重要，因为大量突破都会失败。

官方 Ask Al 内容强调，在 trading range 日里应假设没有突破，尤其是大部分 price action 都是区间时，强二腿也可能只是陷阱。

量化翻译：

Trading range 的特征：

- K 线重叠多；
- 收盘价反复穿越中轴/EMA；
- breakout 后很快收回区间；
- 上下影多，实体弱；
- 趋势 K 后没有 follow-through。

我们应该做：

- 4h 处于 `TRADING_RANGE` 时，不允许趋势突破策略开仓。
- 不做区间高抛低吸。
- 不做网格。
- 不在区间中间交易。

## Brooks 核心四：H1/H2, L1/L2 是 Pullback 语言

H1/H2/L1/L2 的机械定义容易误解。官方论坛讨论里也反复强调：概念比绝对标签更重要。

可量化近似：

H1：

- 牛趋势中出现回调；
- 第一根 K 突破前一根 high；
- 表示第一次尝试恢复上行。

H2：

- H1 尝试失败或不强；
- 市场再次回调；
- 第二次突破前一根 high；
- 通常比 H1 更有确认。

L1/L2 对称。

对我们策略的意义：

- H2/L2 更适合做 **趋势回调入场**。
- 它不是震荡网格，也不是逆势抄底。
- 它要求先有 Always-In 趋势方向。

## Brooks 核心五：Countertrend 不是主方向

官方术语表对 countertrend 的解释很直接：与当前趋势方向相反的交易，对大多数交易者是亏损策略。

对我们系统的意义：

- 不做主要反转策略。
- 不做“跌多了买、涨多了空”。
- 不在强趋势中做均值回归。
- 反转策略最多作为未来独立研究，不进入当前阶段。

## Brooks 核心六：Breakout 需要 Follow-through

Brooks 对突破的判断不是“突破价格就买/卖”，而是看突破质量和后续跟随。

我们已经实现了 `brooks_breakout`：

- 前一根 K 突破；
- 突破 K 质量合格；
- 当前 K 有 follow-through；
- 当前 K 收盘后才给信号。

当前结果：

| Strategy | BTC Return | BTC DD | BTC Trades | ETH Return | ETH DD | ETH Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| brooks_breakout | 3.83% | -7.57% | 20 | 19.10% | -8.62% | 26 |

解读：

- 它明显更保守。
- 对 ETH 有潜力。
- 对 BTC 过于保守，错过了一些早期趋势。

因此，`brooks_breakout` 不应该替代主策略，而应该作为一个独立策略实例并行 paper。

## 我们现有策略的问题

### breakout_atr

优点：

- 简单；
- 交易次数适中；
- 样本外收益不错；
- 容易控制风险。

问题：

- 仍然是突破追单；
- 容易追到 late breakout；
- 对 trading range 过滤不够；
- 不利用 pullback 入场。

### breakout_atr + price action filter

优点：

- 过滤弱信号 K；
- 减少交易次数。

问题：

- 对 BTC 训练集回撤变差；
- 单根 K 线强弱过滤不够表达 Brooks 全部上下文；
- 仍然不是真正的 Brooks pullback 逻辑。

### brooks_breakout

优点：

- 符合“突破 + follow-through”；
- 更保守；
- 交易质量更高。

问题：

- 交易太少；
- BTC 收益太低；
- 它只覆盖 Brooks 的 breakout 部分，不覆盖 pullback 部分。

## 推荐策略：Brooks Pullback Continuation

我认为下一步最合适的策略不是继续优化突破，而是新增：

```text
brooks_pullback
```

核心：

- 4h 判断 Always-In 方向；
- 4h 排除 trading range；
- 1h 等趋势中的 pullback；
- pullback 结束后，用 H2/L2 近似信号入场；
- ATR 止损；
- 组合风控沿用现有框架。

### 多头规则

4h 上下文：

1. `MarketRegime == TREND_UP or CHANNEL_UP`
2. `EMA50 > EMA200`
3. 不是 trading range
4. 不是 late climax

1h 回调：

1. 最近价格从高点回撤至少 `1 ATR`
2. 回调接近 1h EMA20 或 EMA50
3. 回调至少出现两次下推尝试，近似 H2 背景
4. 出现强多头信号 K，或 high 突破前一根 high

入场：

- H2 触发后入场；
- 止损放在 pullback low 下方，或 `1.5 ATR`；
- 不补仓。

### 空头规则

对称：

- 4h Always-In Bear；
- 1h 反弹到 EMA；
- 两次上推失败；
- L2 或强空头 K 触发。

## 为什么这比缩到 15m 更好

我们已经快速测试过 15m：

| Scenario | Train Return | Test Return | Test DD | Test Trades |
| --- | ---: | ---: | ---: | ---: |
| 15m Brooks follow-through | -1.00% | -6.94% | -11.79% | 61 |
| 15m breakout + PA | -14.20% | -1.27% | -17.08% | 142 |

15m 的问题：

- 噪声太高；
- funding/手续费/滑点压力更大；
- Brooks 语境更主观，机械化误差更大；
- 容易过度交易。

1h 的优势：

- 比 4h 更快；
- 比 15m 噪声低；
- 更适合做回调入场；
- 可以保留 4h 的 regime 过滤。

## 建议实施顺序

### Phase A: Market Regime 模块

新增：

- `src/bn_quant/market_regime.py`

输出：

- `TRADING_RANGE`
- `BREAKOUT_UP`
- `BREAKOUT_DOWN`
- `TREND_UP`
- `TREND_DOWN`
- `CHANNEL_UP`
- `CHANNEL_DOWN`

先用固定规则，不做参数扫描。

### Phase B: Pullback Detector

新增：

- `src/bn_quant/pullback.py`

实现：

- 回调深度；
- 是否接近 EMA20/EMA50；
- two-legged pullback 近似；
- H2/L2 触发。

### Phase C: BrooksPullbackStrategy

新增策略注册：

```python
"brooks_pullback": BrooksPullbackStrategy
```

多策略 paper runner 中并行：

- `breakout_4h_pa`
- `brooks_breakout_4h`
- `brooks_pullback_1h`

### Phase D: 1h 数据验证

需要下载：

- BTCUSDT 1h
- ETHUSDT 1h

验证：

- 训练/样本外；
- walk-forward；
- 与当前 4h 策略组合并行 paper；
- 不做参数网格。

## 当前建议

下一步不应该继续调 `brooks_breakout`。

应该实现：

```text
MarketRegime + BrooksPullbackStrategy
```

这是更接近 Al Brooks 核心的方法。

## 参考来源

- Brooks Trading Course, Price Action Fundamentals: https://www.brookstradingcourse.com/trade-price-action/
- Brooks Trading Course, Price Action Glossary: https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
- Brooks Trading Course, Trading Ranges: https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
- Brooks Trading Course, 10 Best Price Action Trading Patterns: https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
- Brooks Trading Course, Brooks Price Action Abbreviations: https://www.brookstradingcourse.com/brooks-price-action-abbreviations/
- Brooks Trading Course forum, H1/H2/L1/L2 discussion: https://www.brookstradingcourse.com/support-forum/01-terminology/h1-h2-l1-l2-etc/paged/2/
- Brooks Trading Course forum, Always In discussion: https://www.brookstradingcourse.com/support-forum/13-always-in/always-in-confusion/
- Brooks Ask Al, Trading Range Days: https://www.brookstradingcourse.com/ask-al/trading-range-day-two-legs-swing/

