# Al Brooks Core Strategy Taxonomy and Quant Metrics

日期：2026-06-27

## 范围说明

这份文档不是复刻 Brooks 课程的全部主观读盘细节，而是把 Brooks 官方公开材料中反复出现的核心思想，翻译成适合我们 Binance USD-M 合约量化框架的策略族和指标字典。

这里的“所有核心策略”按 **可量化策略族** 来列，而不是按 Brooks 课程里每一个细小术语逐条罗列。原因是很多 Brooks 术语本质上是同一件事在不同上下文中的表现，比如 H2、wedge bull flag、double bottom bull flag 都可能属于“顺势回调结束”的不同形态。

## 一句话总结

Al Brooks 的核心不是某个形态，而是：

```text
Context -> Market Cycle -> Always-In Direction -> Setup -> Signal Bar -> Entry -> Trader's Equation -> Management
```

量化上应翻译成：

```text
市场状态机 + 趋势/区间过滤 + 形态触发器 + K线质量评分 + 期望值/风险管理
```

## 核心思想 1：Price Action First

Brooks 的方法强调从价格本身读取供需、趋势、区间、突破、失败突破和跟随，而不是依赖新闻、预测或复杂指标。

量化含义：

- 指标只能辅助，不应该成为主信号。
- 任何信号必须先有价格上下文。
- 同一个 K 线形态在趋势、区间、通道末端的意义不同。

基础指标：

| Metric | Definition | Use |
| --- | --- | --- |
| `bar_range` | `high - low` | K 线波动幅度 |
| `body_size` | `abs(close - open)` | 实体强弱 |
| `body_pct` | `body_size / bar_range` | 趋势 K 或 doji 判断 |
| `close_location` | `(close - low) / bar_range` | 收盘位置 |
| `upper_tail_pct` | `(high - max(open, close)) / bar_range` | 上影压力 |
| `lower_tail_pct` | `(min(open, close) - low) / bar_range` | 下影支撑 |
| `range_atr` | `bar_range / ATR(n)` | 是否是 surprise bar |
| `trend_bar_bull` | `close > open and body_pct >= threshold and close_location >= threshold` | 强多 K |
| `trend_bar_bear` | `close < open and body_pct >= threshold and close_location <= threshold` | 强空 K |
| `doji_like` | `body_pct <= threshold` | 双向交易、犹豫 |

建议默认阈值：

- `strong_body_pct >= 0.55`
- `bull_close_location >= 0.70`
- `bear_close_location <= 0.30`
- `surprise_bar_range_atr >= 1.3`
- `doji_body_pct <= 0.25`

## 核心思想 2：Context Is More Important Than Pattern

Brooks 的形态不是孤立信号。一个强多 K 在 trading range 高位可能是买入高潮，在趋势早期可能是突破，在回调末端可能是顺势入场。

量化含义：

- 先判断 regime，再解释 signal。
- 每个策略必须声明适用 regime。
- 不能把所有形态放进一个全局信号池。

上下文指标：

| Metric | Definition | Use |
| --- | --- | --- |
| `ema20_slope` | `EMA20[t] - EMA20[t-k]` | 短期方向 |
| `ema50_slope` | `EMA50[t] - EMA50[t-k]` | 中期方向 |
| `ema50_gt_ema200` | `EMA50 > EMA200` | 多头大方向 |
| `closes_above_ema20_pct` | last N closes above EMA20 ratio | Always-In bull 评分 |
| `closes_below_ema20_pct` | last N closes below EMA20 ratio | Always-In bear 评分 |
| `directional_efficiency` | `abs(close[t]-close[t-n]) / sum(abs(diff(close)))` | 趋势效率 |
| `overlap_ratio` | K 线之间价格区间重叠比例 | 区间/噪声 |
| `ema_cross_count` | close 穿越 EMA 次数 | 震荡程度 |
| `swing_structure` | HH/HL 或 LH/LL 序列 | 趋势结构 |

## 核心思想 3：Market Cycle

Brooks 的核心框架之一是市场周期：

```text
TRADING_RANGE
  -> BREAKOUT
  -> TREND_BREAKOUT_PHASE
  -> PULLBACK
  -> TREND_CHANNEL_PHASE
  -> TWO_SIDED_TRADING
  -> TRADING_RANGE
```

我们应将其量化成状态机：

| Regime | Meaning | Long Bias | Short Bias |
| --- | --- | ---: | ---: |
| `TRADING_RANGE` | 重叠多、EMA 反复穿越、方向效率低 | 低 | 低 |
| `BREAKOUT_UP` | 向上突破区间/高点，强多 K | 高 | 禁止 |
| `BREAKOUT_DOWN` | 向下突破区间/低点，强空 K | 禁止 | 高 |
| `TREND_UP` | 持续 HH/HL，收盘多数在 EMA 上方 | 高 | 禁止 |
| `TREND_DOWN` | 持续 LH/LL，收盘多数在 EMA 下方 | 禁止 | 高 |
| `CHANNEL_UP` | 上涨但回调变深，双向交易增加 | 中 | 低 |
| `CHANNEL_DOWN` | 下跌但反弹变深，双向交易增加 | 低 | 中 |
| `BREAKOUT_MODE` | 收敛、inside bar、tight range，等待方向 | 条件 | 条件 |
| `CLIMAX_UP` | 连续强涨、远离 EMA、潜在买入高潮 | 降低 | 观察 |
| `CLIMAX_DOWN` | 连续强跌、远离 EMA、潜在卖出高潮 | 观察 | 降低 |

状态机指标：

| Metric | Definition |
| --- | --- |
| `range_height_atr` | `(rolling_high - rolling_low) / ATR` |
| `breakout_distance_atr` | `abs(close - range_boundary) / ATR` |
| `follow_through_bars` | 突破后同向强 K 数 |
| `pullback_depth_atr` | 从趋势高/低点回撤的 ATR 倍数 |
| `bars_since_breakout` | 距离突破的 K 数 |
| `two_sided_score` | doji、重叠、EMA 穿越、上下影的综合分 |
| `climax_score` | 连续趋势 K、远离 EMA、ATR 扩张综合分 |

## 核心思想 4：Always-In Direction

Always-In 不是永远持仓，而是判断强趋势市场中的默认方向。它适合趋势，不适合 trading range。

量化含义：

- Always-In Bull 时，只允许做多策略族。
- Always-In Bear 时，只允许做空策略族。
- No Always-In 时，降低仓位或不交易。

Always-In Bull 指标：

| Metric | Bull Condition |
| --- | --- |
| `ema_stack` | `EMA20 > EMA50 > EMA200` 或至少 `EMA50 > EMA200` |
| `ema_slope` | EMA20/EMA50 上行 |
| `close_above_ema_pct` | 最近 N 根收盘在 EMA20/EMA50 上方比例高 |
| `swing_structure` | 最近 swing highs/lows 呈 HH/HL |
| `pullback_holds` | 回调未跌破关键 swing low |
| `bear_breakout_failures` | 空头突破后缺乏 follow-through |
| `not_trading_range` | 区间评分低 |

Always-In Bear 对称。

建议评分：

```text
always_in_bull_score =
  0.25 * ema_stack_score
  + 0.20 * close_above_ema_score
  + 0.20 * swing_structure_score
  + 0.20 * follow_through_score
  + 0.15 * not_range_score
```

默认：

- `score >= 0.70`: Always-In
- `0.55 <= score < 0.70`: weak trend, 只做高质量 pullback
- `< 0.55`: no trend, 不追突破

## 核心思想 5：Trader's Equation

Brooks 强调交易必须满足胜率、风险、收益的平衡。不是形态好看就交易。

量化公式：

```text
expected_R = win_prob * avg_win_R - (1 - win_prob) * avg_loss_R - cost_R
```

策略准入指标：

| Metric | Use |
| --- | --- |
| `win_rate` | 胜率 |
| `avg_win_R` | 平均盈利 R |
| `avg_loss_R` | 平均亏损 R |
| `profit_factor` | 总盈利 / 总亏损 |
| `expectancy_R` | 单笔期望 R |
| `max_drawdown` | 最大回撤 |
| `trade_count` | 样本数量 |
| `time_in_market` | 持仓暴露 |
| `fee_slippage_R` | 成本占 R 比例 |
| `funding_R` | 资金费率占 R 比例 |

我们用于 Binance 合约时，策略必须同时通过：

- 样本外 `expectancy_R > 0`
- `profit_factor > 1.25`
- `max_drawdown` 在组合风险预算内
- 扣除手续费、滑点、funding 后仍为正
- 不依赖极少数单笔大盈利

## Brooks 核心策略族总表

下面是 Brooks 核心思想可以引出的主要策略族，以及量化实现指标。

| # | Strategy Family | Brooks Idea | Regime | Direction | Binance Quant Priority |
| ---: | --- | --- | --- | --- | --- |
| 1 | Strong Breakout Entry | Breakout + follow-through | `BREAKOUT_UP/DOWN` | 顺势 | 高 |
| 2 | Breakout Pullback | 突破后回踩/反抽 | `TREND` 初期 | 顺势 | 很高 |
| 3 | H2/L2 Pullback Continuation | 二次回调入场 | `TREND/CHANNEL` | 顺势 | 很高 |
| 4 | Small Pullback Trend | 小回调强趋势 | `TREND` | 顺势 | 中高 |
| 5 | Moving Average Pullback | EMA 附近回调结束 | `TREND/CHANNEL` | 顺势 | 高 |
| 6 | Wedge Flag Continuation | 三推回调旗形 | `TREND/CHANNEL` | 顺势 | 高 |
| 7 | Double Bottom/Top Flag | 双底/双顶旗形 | `TREND/CHANNEL` | 顺势 | 高 |
| 8 | Failed Breakout Reversal | 区间假突破 | `TRADING_RANGE` | 反向回区间 | 中 |
| 9 | Trading Range Fade | Buy low, sell high | `TRADING_RANGE` | 双向 | 低，中后期 |
| 10 | Breakout Mode Entry | 收敛后等待突破 | `BREAKOUT_MODE` | 条件顺势 | 中 |
| 11 | Major Trend Reversal | 趋势反转 | `CLIMAX/CHANNEL_END` | 逆原趋势 | 中低 |
| 12 | Wedge Reversal | 三推耗尽反转 | `CLIMAX/CHANNEL_END` | 逆原趋势 | 中 |
| 13 | Final Flag Reversal | 最后一段旗形失败 | `CLIMAX` | 逆原趋势 | 中低 |
| 14 | Climactic Exhaustion Reversal | 高潮耗尽 | `CLIMAX` | 逆原趋势 | 低 |
| 15 | Micro Double Top/Bottom | 微型双顶/双底 | 任意但需上下文 | 条件 | 信号过滤 |
| 16 | Two-Bar Reversal | 两根 K 反转 | 任意但需上下文 | 条件 | 信号过滤 |
| 17 | Inside/Outside Bar Breakout | ii/ioi/OB 突破 | `BREAKOUT_MODE` | 条件 | 中 |
| 18 | Measured Move Target Strategy | 等距目标/磁铁位 | 趋势或突破 | 出场/过滤 | 高 |
| 19 | Gap / Body Gap Continuation | 缺口或实体缺口 | 强趋势 | 顺势 | 中 |
| 20 | Failed Failure / Trap | 二次失败陷阱 | 区间/趋势切换 | 条件 | 中 |

## 策略 1：Strong Breakout Entry

Brooks 对突破的要求不是“碰到高点就买”，而是突破质量和 follow-through。

适用：

- `BREAKOUT_UP`
- `BREAKOUT_DOWN`
- tight trading range 后的方向选择

多头条件：

1. 过去 N 根形成清晰阻力位：rolling high、range high、swing high。
2. 当前 K 收盘突破阻力。
3. 突破距离达到 `breakout_buffer_atr`。
4. 突破 K 是强多 K。
5. 下一根或当前确认窗口有 follow-through。
6. 不在 late climax。

量化指标：

| Metric | Suggested Rule |
| --- | --- |
| `breakout_level` | `max(high[-N:-1])` |
| `breakout_distance_atr` | `(close - breakout_level) / ATR >= 0.10-0.25` |
| `breakout_body_pct` | `>= 0.55` |
| `close_location` | `>= 0.70` for long, `<= 0.30` for short |
| `range_atr` | `>= 1.0` |
| `follow_through_close` | next close above breakout bar midpoint/high |
| `failed_breakout` | close back inside range within M bars |

适合我们：

- 已有 `brooks_breakout`，可以继续保留。
- 不应作为唯一主策略，因为 BTC 上交易太少。

## 策略 2：Breakout Pullback

这是比直接追突破更适合合约量化的 Brooks 策略族。

逻辑：

```text
强突破 -> 市场进入 Always-In -> 第一次回踩突破位/EMA -> 顺势信号 K -> 入场
```

多头条件：

1. 最近发生有效向上突破。
2. 突破后至少一根 follow-through。
3. 回调到 breakout level、EMA20/EMA50、或前高附近。
4. 回调没有跌回原区间太深。
5. 出现强多信号 K 或 H1/H2。

量化指标：

| Metric | Suggested Rule |
| --- | --- |
| `valid_prior_breakout` | 最近 M 根内有突破并 follow-through |
| `pullback_to_level_dist_atr` | `abs(low - breakout_level) / ATR <= 0.5` |
| `pullback_depth_atr` | `0.8 <= depth <= 3.0` |
| `inside_old_range_pct` | 回到旧区间幅度不能太深 |
| `signal_bar_quality` | 强多/强空 K |
| `entry_trigger` | high 突破信号 K high，空头相反 |

我们优先级：

- 很高。
- 适合 `4h context + 1h entry`。

## 策略 3：H2/L2 Pullback Continuation

H1/H2/L1/L2 是 Brooks 回调语言。量化时不要执着标签，重点是“趋势中的一腿或两腿回调后恢复”。

多头 H2 近似：

1. Always-In Bull。
2. 价格从 swing high 回撤。
3. 第一次上破前一根 high 视为 H1。
4. H1 后没有强 follow-through 或再次回调。
5. 第二次上破前一根 high 视为 H2。
6. H2 信号 K 质量合格。

量化指标：

| Metric | Suggested Rule |
| --- | --- |
| `trend_context` | `always_in_bull_score >= 0.70` |
| `pullback_depth_atr` | `>= 0.8` |
| `pullback_bars` | `2-12` on 1h; `1-6` on 4h |
| `h1_count` | pullback 内第一次 high[0] > high[-1] |
| `h2_count` | 第二次 high[0] > high[-1] |
| `lower_low_count` | 回调 legs 近似 |
| `ema_touch` | low 接近 EMA20/50 |
| `signal_close_location` | 多头 `>= 0.60-0.70` |

我们优先级：

- 最高。
- 这是下一步 `brooks_pullback` 的核心。

## 策略 4：Small Pullback Trend

强趋势中回调很浅，价格持续在 EMA 一侧，市场不给深回调。

适用：

- strong Always-In trend
- breakout phase early
- micro channel

多头条件：

1. 连续多根 K 低点不破前低，或仅小幅回调。
2. 大多数收盘在 EMA20 上方。
3. 回调不超过 `0.8 ATR` 或不触及 EMA20。
4. 出现小回调结束信号。

量化指标：

| Metric | Rule |
| --- | --- |
| `micro_channel_len` | 连续 higher lows 数 |
| `pullback_max_depth_atr` | `< 0.8` |
| `bars_above_ema20_pct` | `>= 0.75` |
| `ema_gap_atr` | `abs(close - EMA20) / ATR` |
| `small_pullback_count` | 趋势中浅回调次数 |

风险：

- 容易在高潮后追高。
- 必须有 climax 过滤。

## 策略 5：Moving Average Pullback

Brooks 常用 EMA 作为价格行为参考线，尤其在趋势中看回调到均线附近的反应。

多头条件：

1. Always-In Bull。
2. 回调触及或接近 EMA20/EMA50。
3. 触及 EMA 后没有强空 follow-through。
4. 出现强多信号 K。

量化指标：

| Metric | Rule |
| --- | --- |
| `dist_to_ema20_atr` | `abs(low - EMA20) / ATR <= 0.3-0.6` |
| `dist_to_ema50_atr` | 深回调用 EMA50 |
| `ema_rejection_tail` | 下影线占比高 |
| `failed_ema_break` | 跌破 EMA 后快速收回 |
| `signal_bar_quality` | 强多/强空 |

我们优先级：

- 高。
- 可作为 H2/L2 的加分项，不必独立成策略。

## 策略 6：Wedge Flag Continuation

趋势中的回调经常以三推结构出现。三推回调结束后，顺趋势入场。

多头 wedge bull flag：

1. Always-In Bull。
2. 回调出现三个向下推进点。
3. 第三推没有明显加速下破，或出现失败。
4. 出现多头信号 K。

量化指标：

| Metric | Rule |
| --- | --- |
| `push_count` | swing low 数量约等于 3 |
| `push_spacing` | pushes 之间至少间隔 2 根 K |
| `momentum_divergence_proxy` | 第三推 range/volume/move 不再扩张 |
| `third_push_failure` | 新低后收回 |
| `signal_break` | 突破信号 K high |

我们优先级：

- 高。
- 可以集成进 `pullback_score`。

## 策略 7：Double Bottom/Top Flag Continuation

趋势中的双底/双顶旗形不是反转，而是顺势继续。

多头 double bottom bull flag：

1. Always-In Bull。
2. 回调中两次测试相近低点。
3. 第二次测试不强破，或破后收回。
4. 多头信号 K 触发。

量化指标：

| Metric | Rule |
| --- | --- |
| `low1_low2_distance_atr` | `abs(low1-low2)/ATR <= 0.5` |
| `second_test_failure` | 第二低点收盘不创新低或收回 |
| `bars_between_tests` | `>= 2` |
| `signal_bar_quality` | 强多 |
| `entry_above_signal` | 突破信号 K high |

我们优先级：

- 高。
- 适合与 H2 合并。

## 策略 8：Failed Breakout Reversal

Trading range 中大部分突破容易失败。假突破回到区间，是 Brooks 常见交易思路。

多头失败下破：

1. 当前 regime 是 `TRADING_RANGE`。
2. 价格跌破 range low。
3. 没有 follow-through。
4. 很快收回 range 内。
5. 出现多头信号 K。

量化指标：

| Metric | Rule |
| --- | --- |
| `range_regime_score` | `>= threshold` |
| `breakout_beyond_range_atr` | `0.1-0.8`，不能太远 |
| `bars_outside_range` | `<= 3` |
| `close_back_inside` | close 回区间内 |
| `opposite_signal_bar` | 强反向 K |
| `target` | range midpoint or opposite side |

我们优先级：

- 中。
- 当前阶段不优先，因为它是区间反向策略，和我们趋势主线不同。

## 策略 9：Trading Range Fade

Brooks 对区间的基本原则是低买高卖，中间少交易。

多头：

1. regime 是 `TRADING_RANGE`。
2. 价格在 range low 附近。
3. 下破失败或形成强多信号。
4. 目标是 range midpoint 或 range high。

量化指标：

| Metric | Rule |
| --- | --- |
| `range_position` | `(close - range_low)/(range_high-range_low)` |
| `near_low` | `range_position <= 0.20` |
| `near_high` | `range_position >= 0.80` |
| `middle_zone` | `0.35-0.65` 禁止交易 |
| `range_height_atr` | 需要足够覆盖手续费和滑点 |
| `failed_breakout_score` | 优先交易假突破 |

我们优先级：

- 低。
- 用户已经明确不想做网格，区间 fade 也容易变成“主观网格化”，暂不进入主系统。

## 策略 10：Breakout Mode Entry

当市场收敛、inside bars、tight trading range 时，进入 breakout mode。方向未定，只等突破。

条件：

1. 波动收缩。
2. 多根 inside/overlap K。
3. 上下边界清晰。
4. 突破后只做有 follow-through 的方向。

量化指标：

| Metric | Rule |
| --- | --- |
| `atr_compression` | ATR percentile 低 |
| `inside_bar_count` | ii/ioi 或连续 inside |
| `range_height_atr` | 较小但可突破 |
| `overlap_ratio` | 高 |
| `breakout_confirmation` | 强 K + follow-through |

我们优先级：

- 中。
- 可作为 `breakout_atr` 的上下文增强。

## 策略 11：Major Trend Reversal

Brooks 的主要反转通常不是单根 K 线反转，而是：

```text
强趋势 -> 通道突破 -> 测试极点 -> 失败 -> 反向突破
```

多头 MTR：

1. 原来是 bear trend。
2. 价格突破下降通道。
3. 回测或新低失败。
4. 形成 higher low 或 double bottom。
5. 向上突破 neckline/swing high。

量化指标：

| Metric | Rule |
| --- | --- |
| `prior_trend_strength` | 原趋势强度 |
| `channel_break` | close 突破趋势线/EMA 结构 |
| `test_extreme` | 回测前低/前高 |
| `failed_new_low` | 新低后收回或无 follow-through |
| `higher_low` | 第二低点高于第一低点 |
| `reversal_breakout` | 突破反向 swing high |

我们优先级：

- 中低。
- 可以未来研究，但不进入第一阶段实盘。

## 策略 12：Wedge Reversal

三推趋势末端可能产生反转，尤其是配合高潮、通道末端和支撑阻力位。

多头 wedge reversal：

1. 原来是 bear trend。
2. 出现三个向下推进。
3. 第三推发生在支撑/测量目标附近。
4. 第三推失败，出现强多信号。

量化指标：

| Metric | Rule |
| --- | --- |
| `three_pushes` | 三个 swing lows/highs |
| `push_momentum_decay` | 推进幅度或 ATR 衰减 |
| `near_support_resistance` | 靠近前低、测量目标、整数位 |
| `climax_score` | 高 |
| `reversal_signal_bar` | 强反向 K |

我们优先级：

- 中。
- 可作为退出/减仓信号优先于开反向仓。

## 策略 13：Final Flag Reversal

趋势末端的最后一个小旗形突破失败，可能成为反转起点。

指标：

| Metric | Rule |
| --- | --- |
| `late_trend` | bars since breakout 很多、远离 EMA |
| `small_flag_after_climax` | 高潮后小整理 |
| `flag_breakout_failure` | 顺趋势突破失败 |
| `opposite_break` | 反向突破 flag |
| `follow_through` | 反向跟随确认 |

我们优先级：

- 中低。
- 适合作为“不再追趋势”的过滤器。

## 策略 14：Climactic Exhaustion Reversal

高潮反转是高风险策略。Brooks 会区分强趋势延续和高潮后反转。量化容易误判。

指标：

| Metric | Rule |
| --- | --- |
| `consecutive_trend_bars` | 连续同向强 K |
| `distance_from_ema_atr` | 远离 EMA20/50 |
| `atr_expansion` | 当前 ATR 高于过去分位 |
| `tail_against_trend` | 末端出现长反向影线 |
| `failed_follow_through` | 高潮后无继续 |
| `opposite_trend_bar` | 强反向 K |

我们优先级：

- 低。
- 当前只用于过滤 late entry，不用来主动反向开仓。

## 策略 15：Micro Double Top/Bottom

微型双顶/双底是短期失败测试，常用于信号 K 过滤。

指标：

| Metric | Rule |
| --- | --- |
| `micro_low_distance_atr` | 两个低点距离很近 |
| `micro_high_distance_atr` | 两个高点距离很近 |
| `bars_between` | 1-5 根 |
| `second_test_close` | 第二次测试后反向收盘 |

我们优先级：

- 作为信号过滤器，不单独成策略。

## 策略 16：Two-Bar Reversal

两根 K 的方向突变。单独使用噪声很高，必须依赖上下文。

多头：

1. 第一根是空头 K。
2. 第二根是强多 K。
3. 第二根收盘接近高点，并吞没或收复前一根主体。

指标：

| Metric | Rule |
| --- | --- |
| `bar1_bear_strength` | 第一根空头强度 |
| `bar2_bull_strength` | 第二根多头强度 |
| `body_reclaim_pct` | 第二根收复第一根实体比例 |
| `context_score` | 必须在 pullback low/range low/support |

我们优先级：

- 信号过滤器。

## 策略 17：Inside/Outside Bar Breakout

inside bar、ii、ioi、outside bar 都可以表示压缩和 breakout mode，但方向要等突破。

指标：

| Metric | Rule |
| --- | --- |
| `inside_bar` | high <= prev_high and low >= prev_low |
| `ii_pattern` | 连续 inside |
| `outside_bar` | high > prev_high and low < prev_low |
| `compression_score` | 波动收缩综合分 |
| `trigger` | 突破 mother bar high/low |
| `confirmation` | follow-through |

我们优先级：

- 中。
- 可作为 breakout setup 的一部分。

## 策略 18：Measured Move Target Strategy

Brooks 很重视 measured move 和磁铁位。对我们来说，它最适合做目标、止盈、过滤和减仓。

指标：

| Metric | Rule |
| --- | --- |
| `range_height` | `range_high - range_low` |
| `measured_move_up` | `breakout_level + range_height` |
| `measured_move_down` | `breakout_level - range_height` |
| `leg1_length` | 第一段趋势长度 |
| `projection_target` | pullback low/high + leg1_length |
| `target_distance_atr` | 距目标还有多少 ATR |

用法：

- 入场前，若距离测量目标太近，不追。
- 到达测量目标附近，减仓或收紧止损。
- fake breakout 后，目标设为 range midpoint。

我们优先级：

- 高。
- 应该尽快加入出场逻辑。

## 策略 19：Gap / Body Gap Continuation

加密货币连续交易，没有传统股票开盘缺口，但可以使用 body gap / micro gap 的概念。

指标：

| Metric | Rule |
| --- | --- |
| `body_gap_up` | 当前实体低点高于前 N 根实体高点 |
| `body_gap_down` | 当前实体高点低于前 N 根实体低点 |
| `gap_holds` | 回调未关闭 body gap |
| `trend_strength` | Always-In 同向 |

我们优先级：

- 中。
- 适合作为强趋势加分项。

## 策略 20：Failed Failure / Trap

Brooks 经常强调失败信号的失败本身很重要。比如空头做假突破失败后，多头反而更强。

指标：

| Metric | Rule |
| --- | --- |
| `first_signal_direction` | 初始突破方向 |
| `signal_failure` | M 根内回到触发价反侧 |
| `opposite_breakout` | 反向突破失败信号 K |
| `trap_strength` | 反向 K 强度 + follow-through |

我们优先级：

- 中。
- 可作为 trading range 或 pullback 中的增强信号。

## 策略分层：我们该先做什么

### 第一优先级：适合当前框架，且符合用户不做网格的要求

| Strategy | Why |
| --- | --- |
| `brooks_pullback` | 最接近 Brooks 核心，也适合 4h + 1h |
| `breakout_pullback` | 比直接追突破更稳 |
| `h2_l2_continuation` | 顺势，非网格，交易频率比 4h breakout 更高 |
| `ema_pullback` | 易量化，可作为 H2/L2 加分项 |
| `measured_move_exit` | 改善止盈和避免 late entry |

### 第二优先级：作为过滤器或并行策略

| Strategy | Use |
| --- | --- |
| `brooks_breakout` | 保留，作为高质量突破策略 |
| `small_pullback_trend` | 强趋势时补充 |
| `wedge_flag_continuation` | 回调评分项 |
| `double_bottom/top_flag` | 回调评分项 |
| `breakout_mode` | 提升突破策略上下文 |

### 暂不优先

| Strategy | Reason |
| --- | --- |
| `trading_range_fade` | 容易变成区间网格化，与当前偏好冲突 |
| `major_trend_reversal` | 逆势，量化误判风险高 |
| `climax_reversal` | 高风险，先做过滤器 |
| `final_flag_reversal` | 更适合退出，不适合当前主动反向开仓 |

## 建议指标模块

为了把 Brooks 思想纳入框架，应拆成以下模块。

### `bar_features`

已有一部分，建议扩展：

```text
body_pct
close_location
upper_tail_pct
lower_tail_pct
range_atr
is_bull_trend_bar
is_bear_trend_bar
is_doji
is_inside_bar
is_outside_bar
```

### `market_regime`

新增：

```text
regime
range_score
trend_score
breakout_score
always_in_bull_score
always_in_bear_score
climax_score
two_sided_score
```

### `support_resistance`

新增：

```text
rolling_high
rolling_low
swing_highs
swing_lows
range_high
range_low
range_mid
breakout_level
measured_move_targets
round_number_distance
```

### `pullback`

新增：

```text
pullback_depth_atr
pullback_bars
leg_count
h1_l1_count
h2_l2_count
ema_touch
wedge_push_count
double_test_score
pullback_signal_quality
```

### `entry_quality`

新增：

```text
setup_score
signal_bar_score
context_score
follow_through_score
late_entry_penalty
expected_R
```

### `trade_management`

新增：

```text
initial_stop_price
actual_risk_R
target_1R
target_2R
measured_move_target
trail_by_swing
trail_by_ema
time_stop_bars
```

## Brooks 到我们框架的映射

| Brooks Concept | Quant Module | Strategy Impact |
| --- | --- | --- |
| Market cycle | `market_regime.py` | 决定允许哪些策略 |
| Always-In | `market_regime.py` | 决定方向 |
| Trading range | `market_regime.py` | 禁止趋势追单 |
| Breakout | `strategy.py` / `support_resistance.py` | 突破策略 |
| Follow-through | `entry_quality.py` | 确认突破 |
| Pullback | `pullback.py` | 主策略核心 |
| H2/L2 | `pullback.py` | 回调触发 |
| Wedge | `pullback.py` | 回调评分 |
| Double bottom/top flag | `pullback.py` | 回调评分 |
| Climax | `market_regime.py` | 避免追高杀低 |
| Measured move | `trade_management.py` | 止盈/过滤 |
| Trader's equation | `backtest.py` | 策略准入 |

## 推荐的下一版策略定义

### `brooks_pullback`

时间框架：

- `slow_interval = 4h`
- `fast_interval = 1h`

方向：

- 只做 4h Always-In 方向。

多头入场：

1. 4h `always_in_bull_score >= 0.70`
2. 4h `regime in {TREND_UP, CHANNEL_UP, BREAKOUT_UP}`
3. 4h `range_score < threshold`
4. 4h `climax_score < threshold`
5. 1h `pullback_depth_atr >= 0.8`
6. 1h `ema_touch == true` 或 `breakout_level_retest == true`
7. 1h `h2_count >= 1` 或 `wedge_push_count >= 3` 或 `double_bottom_flag_score >= threshold`
8. 1h signal bar 是强多 K
9. 预期收益至少 `1.5R`

空头对称。

止损：

- 多头：`min(pullback_low - buffer, entry - 1.5 ATR)`
- 空头：`max(pullback_high + buffer, entry + 1.5 ATR)`

止盈：

- 首选 measured move 或 2R。
- 到 1R 后可移动到 breakeven 或前一 swing。
- late channel phase 降低目标。

## 推荐回测准入标准

| Metric | Minimum |
| --- | ---: |
| sample-out return | `> 0` |
| profit factor | `> 1.25` |
| trades in test | `>= 20` across BTC+ETH |
| max drawdown | `< 15%` at 1% risk |
| expectancy | `> 0.05R` after cost |
| average loss | close to planned 1R |
| largest winner dependency | top 3 trades not responsible for all profit |

## 结论

Brooks 的策略核心可以浓缩为四个可实现方向：

1. **趋势突破**：已经有 `brooks_breakout`，保留但不是主力。
2. **顺势回调**：下一阶段主力，尤其是 `4h Always-In + 1h H2/L2`。
3. **区间失败突破**：未来可以做，但不应该优先，因为容易偏向网格/震荡交易。
4. **反转策略**：先作为退出和过滤器，不作为当前主动开仓策略。

下一步最合理的实施目标：

```text
market_regime.py
pullback.py
BrooksPullbackStrategy
1h BTC/ETH 数据验证
```

## 参考来源

- Brooks Trading Course, Price Action Fundamentals: https://www.brookstradingcourse.com/trade-price-action/
- Brooks Trading Course, Price Action Glossary: https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
- Brooks Trading Course, Trading Ranges: https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
- Brooks Trading Course, 10 Best Price Action Trading Patterns: https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
- Brooks Trading Course, Brooks Price Action Abbreviations: https://www.brookstradingcourse.com/brooks-price-action-abbreviations/
- Brooks Trading Course forum, H1/H2/L1/L2 discussion: https://www.brookstradingcourse.com/support-forum/01-terminology/h1-h2-l1-l2-etc/paged/2/
- Brooks Trading Course forum, Always In discussion: https://www.brookstradingcourse.com/support-forum/13-always-in/always-in-confusion/
- Brooks Ask Al, Trading Range Days: https://www.brookstradingcourse.com/ask-al/trading-range-day-two-legs-swing/
