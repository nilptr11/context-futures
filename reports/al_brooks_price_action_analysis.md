# Al Brooks Price Action Analysis for This Quant Framework

日期：2026-06-26

## 目标

把 Al Brooks 价格行为学拆成可量化的模块，服务当前 Binance USD-M 4h 趋势系统。

原则：

- 不做合约网格交易。
- 不逆势补仓。
- 不马丁。
- 不把主观术语硬编码成过度拟合的规则。
- 先用价格行为做过滤和上下文判断，再考虑新入场模型。

## Brooks 框架的核心

Brooks 的价格行为不是单一形态，而是“市场状态 + 信号 K + 后续跟随 + 风险收益”的组合判断。

核心维度：

| Brooks 概念 | 对我们有用的量化含义 |
| --- | --- |
| Trend | 只顺着主要方向交易，避免逆势摸顶摸底 |
| Trading Range | 降低交易频率，避免在区间高位追多、低位追空 |
| Breakout | 不是突破价位就够，还要看突破 K 线质量和 follow-through |
| Breakout Pullback | 突破后回踩不破，再恢复方向，通常比第一根突破更稳 |
| Always In | 用连续强趋势 K 判断当前市场方向，而不是必须始终持仓 |
| H1/H2, L1/L2 | 趋势中的一腿/二腿回调结束信号，可转成顺势回调入场 |
| Wedge / Climax | 趋势末端风险，减少追在过度延伸后的入场 |
| Measured Move | 用于判断突破后空间是否足够，过滤赔率不足的交易 |

## 不适合直接机械化的部分

这些内容不能直接拿来硬编码：

- “看起来像强趋势”这类主观判断。
- 完整 H1/H2/L1/L2 标签体系，人工标注和机械标注会有偏差。
- 交易区间内高抛低吸。Brooks 可以用于手动 scalp，但合约 20x 下不适合我们的系统。
- 宽止损 scale-in。它在 Brooks 手动交易里有语境，但不适合当前组合风控。
- 主观重大支撑阻力。可以用算法近似，但不能依赖人工线。

## 可以先量化的模块

### 1. Bar Strength

衡量单根 K 线是否是高质量信号 K。

字段：

- `range = high - low`
- `body = abs(close - open)`
- `body_pct = body / range`
- `close_location = (close - low) / range`
- `upper_tail_pct = (high - max(open, close)) / range`
- `lower_tail_pct = (min(open, close) - low) / range`
- `range_atr = range / ATR`

候选规则：

- 强多头 K：`close > open`，`body_pct >= 0.55`，`close_location >= 0.70`，`range_atr >= 0.8`
- 强空头 K：`close < open`，`body_pct >= 0.55`，`close_location <= 0.30`，`range_atr >= 0.8`
- 弱信号 K：body 小、上下影长、close 在中间，跳过突破信号。

用途：

- 当前突破策略只看 close 是否突破 N 根高低点。
- 可以改成：突破必须伴随强信号 K，或下一根有 follow-through。

### 2. Trading Range Detector

Brooks 强调交易区间里大量突破会失败。我们应该用它过滤追突破。

候选指标：

- `overlap_ratio`：最近 N 根 K 线中，相邻 K 线区间重叠比例。
- `range_height_atr`：N 根最高点到最低点的距离 / ATR。
- `close_chop`：收盘价上下穿 EMA 的次数。
- `failed_breakouts`：最近 N 根 K 线突破区间后又收回区间的次数。

候选判定：

- `overlap_ratio >= 0.65`
- `close_chop >= 4`
- `range_height_atr <= 6`

交易动作：

- 如果是 tight trading range：不交易。
- 如果是 broad trading range：不做区间高位突破追多、低位突破追空。
- 对当前系统最简单的处理：`regime == TRADING_RANGE` 时禁止新开仓。

### 3. Breakout Follow-through

Brooks 思路里，突破后没有跟随就是风险信号。

候选规则：

- 多头突破后，下一根 K 线不能大幅收回突破位。
- 至少 1 根 follow-through K：
  - close 高于突破位；
  - close 在 K 线范围上半部；
  - 不是明显 bear reversal bar。

改造方式：

- 方案 A：突破 K 收盘后不开仓，等待下一根 4h follow-through 再进。
- 方案 B：突破 K 可以进，但仓位减半；有 follow-through 后补足。

第一版建议用方案 A，简单、可测、减少假突破。

### 4. Breakout Pullback

突破后回踩原区间边界，再恢复突破方向。

量化定义：

- 先出现有效突破；
- 之后 1-5 根 K 线回踩 breakout level 附近；
- 回踩不重新收回区间内部太多；
- 再出现顺势强 K 或收盘重新远离 breakout level。

用途：

- 替代“突破即追”的一部分交易。
- 对 4h crypto 更适合，因为能减少 funding 和手续费噪声。

### 5. H2 / L2 顺势回调

不建议完整复制 Brooks bar counting，但可以做可操作近似。

多头 H2 近似：

- 高级别趋势向上；
- 价格回调到 EMA 附近或 ATR 通道中部；
- 回调至少两次尝试下跌失败；
- 出现强多头 K，且 high 突破上一根 high。

空头 L2 近似：

- 高级别趋势向下；
- 价格反弹到 EMA 附近；
- 反弹至少两次尝试上涨失败；
- 出现强空头 K，且 low 跌破上一根 low。

用途：

- 当前系统只做突破。
- H2/L2 可以成为第二类入场：趋势中回调入场。
- 但第一版只做过滤，不直接加新入场，避免复杂度过快上升。

### 6. Climax / Late Trend Filter

Brooks 经常警惕趋势末端追单。

量化指标：

- 最近 M 根内连续同向大 K 数量过多；
- price 与 EMA 偏离超过 `k * ATR`；
- 出现第三次推升/下跌但动能减弱；
- 大阳线后没有 follow-through。

用途：

- 如果多头已经连续 3 段上冲，且突破 K 远离 EMA，降低仓位或不追。
- 对 20x 合约尤其重要。

## 对当前框架的落地顺序

当前策略：

- `BreakoutAtrStrategy`
- 4h K 线
- EMA50/EMA200 趋势过滤
- 120 根突破
- ATR 止损/移动止损
- BTC/ETH
- `risk_fraction = 0.01`

建议分三步改：

### Phase 1: 只加过滤器

新增 `src/bn_quant/price_action.py`：

- `bar_features(candle, atr)`
- `is_strong_bull_bar(...)`
- `is_strong_bear_bar(...)`
- `overlap_ratio(candles)`
- `is_trading_range(candles, atr_values)`
- `is_late_trend_climax(candles, atr_values, side)`
- `has_follow_through(candles, breakout_level, side)`

修改 `BreakoutAtrStrategy.signal_at`：

- 突破信号必须通过强信号 K 过滤；
- 如果处于 trading range，跳过；
- 如果 late climax，跳过或半仓；
- 暂不改止损和仓位。

### Phase 2: 改为确认式突破

新增信号状态：

- 第一次突破只记录 pending breakout；
- 下一根 K 线确认 follow-through 后入场；
- 如果下一根收回区间，取消信号。

这会减少交易次数，但更符合 Brooks 对假突破的警惕。

### Phase 3: 增加顺势回调入场

新增 `PullbackContinuationStrategy` 或在现有策略中加 `entry_mode`：

- `breakout`
- `breakout_pullback`
- `h2_l2_pullback`

先只在 paper runner 跑，不直接实盘。

## 不推荐做的改动

- 不做区间内高抛低吸。
- 不做 scale-in 扛单。
- 不做固定间隔网格。
- 不把 wedge / H2 / L2 全部一次性塞进策略。
- 不用参数扫描找“最优 Brooks 阈值”。

## 第一版具体规则建议

先实现最小规则：

多头突破允许条件：

1. EMA50 > EMA200。
2. close 突破过去 120 根 high。
3. 当前 K 是强多头 K：
   - `body_pct >= 0.55`
   - `close_location >= 0.70`
   - `range_atr >= 0.8`
4. 最近 40 根不是 tight trading range：
   - `overlap_ratio < 0.65`
   - `close_chop < 6`
5. 不是明显 late climax：
   - `abs(close - EMA50) <= 4 * ATR`

空头对称。

这不是 Brooks 全量体系，只是把最可靠的上下文过滤接入当前趋势系统。

## Phase 1 实施结果

已新增：

- `src/bn_quant/price_action.py`
- `StrategyConfig.enable_price_action_filters`
- 强信号 K 过滤
- trading range 过滤
- late climax 过滤

当前默认启用，但可以在配置里关闭：

```toml
enable_price_action_filters = false
```

BTC/ETH 4h、`risk_fraction = 0.01`、计入 funding 的初步结果：

| Symbol | Period | Return | Max DD | Trades | Profit Factor |
| --- | --- | ---: | ---: | ---: | ---: |
| BTCUSDT | Train | 4.10% | -15.60% | 39 | 1.16 |
| BTCUSDT | Test | 18.22% | -7.56% | 20 | 2.45 |
| ETHUSDT | Train | 11.16% | -10.13% | 49 | 1.36 |
| ETHUSDT | Test | 6.92% | -10.60% | 16 | 1.59 |

解读：

- 交易次数显著下降。
- 样本外 BTC/ETH 都为正。
- BTC 训练集回撤变差，说明强 K 过滤不一定天然降低风险。
- 该过滤器应该先作为 A/B 可切换模块，不应直接进入实盘默认决策。

## Phase 2 实施结果

已新增独立策略类型：

- `brooks_breakout`

它不是“旧策略加开关”，而是多策略框架下的独立策略实例。

逻辑：

1. 前一根 K 必须突破过去 `breakout_window` 的高/低点。
2. 前一根 K 必须通过 Phase 1 price action 过滤：
   - 强信号 K；
   - 非 trading range；
   - 非 late climax。
3. 当前 K 必须给出 follow-through：
   - 多头：收盘继续高于突破位 + `brooks_breakout_buffer_atr * ATR`，且收盘位置在 K 线上半部；
   - 空头：对称。
4. 信号在 follow-through K 收盘后才触发。

配置：

```toml
name = "brooks_breakout"
brooks_breakout_buffer_atr = 0.10
brooks_follow_through_close_location_min = 0.55
brooks_follow_through_close_location_max = 0.45
```

BTC/ETH 4h、`risk_fraction = 0.01`、计入 funding 的全区间 smoke：

| Symbol | Return | Max DD | Trades | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| BTCUSDT | 3.83% | -7.57% | 20 | 1.30 |
| ETHUSDT | 19.10% | -8.62% | 26 | 2.13 |

解读：

- `brooks_breakout` 明显更保守，交易数量少。
- BTC 表现偏弱，说明“等待 follow-through”会过滤掉一部分有利的早期突破。
- ETH 表现较好，说明该结构在部分标的上有潜力。
- 该策略适合进入 paper runner 与 `breakout_atr` 并行观察，而不是立即替代主策略。

## 预期影响

- 交易次数会下降。
- 假突破会减少。
- 收益不一定立刻提高，但回撤和交易质量应该改善。
- 如果收益下降但 DD 明显下降，可以提高 `risk_fraction` 做风险预算平衡。

## 参考来源

- Brooks Trading Course, Price Action Fundamentals: https://www.brookstradingcourse.com/trade-price-action/
- Brooks Trading Course, Glossary of Terms: https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
- Brooks Price Action Abbreviations: https://www.brookstradingcourse.com/brooks-price-action-abbreviations/
- Brooks Trading Course, Trading Ranges: https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
- Brooks Trading Course, 10 Best Price Action Patterns: https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
- Brooks Trading Course, How to Trade Price Action Manual: https://www.brookstradingcourse.com/how-to-trade-price-action-manual/
