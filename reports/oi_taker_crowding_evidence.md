# OI and Taker Crowding Evidence

日期：2026-06-27

## Brooks rationale

OI 和 taker buy/sell 不是开仓信号。

它们回答的是：

```text
趋势是否被新仓追出来？
同方向主动成交是否已经拥挤？
现在的顺势交易是否更像 late entry？
```

在 Brooks 语境下，这属于 context evidence，而不是 setup。

## 实现方式

新增 `MarketEvidence` 字段：

```text
open_interest
open_interest_change_pct
taker_buy_ratio
```

新增评分：

- `taker_crowding_score`
- `open_interest_crowding_score`
- `external_crowding_score`

方向解释：

```text
side = LONG, taker_buy_ratio 高 -> 多头主动追买拥挤
side = SHORT, taker_buy_ratio 低 -> 空头主动追卖拥挤
OI 同时上升 -> 说明更可能是新仓拥挤，而不只是换手
```

## 参数

```toml
brooks_taker_buy_crowding_threshold = 0.58
brooks_taker_sell_crowding_threshold = 0.42
brooks_taker_crowding_extreme_distance = 0.18
brooks_open_interest_crowding_threshold = 0.002
brooks_open_interest_crowding_extreme = 0.020
brooks_external_crowding_context_penalty = 0.10
brooks_external_crowding_probability_penalty = 0.08
```

## 数据来源

已接入：

- paper/live: `/futures/data/openInterestHist`
- paper/live: `/futures/data/takerlongshortRatio`
- future kline CSV: `taker_buy_volume`

历史限制：

- Binance 官方 OI statistics 仅适合近期窗口；
- taker buy/sell endpoint 仅适合近期窗口；
- kline 原始数据包含 taker buy volume，后续重新拉取 K 线后，回测可用 `taker_buy_ratio`。

旧 CSV 没有 `taker_buy_volume` 字段时，回测不会伪造 taker evidence。

## Brooks 对齐

这次实现遵守：

- OI/taker 不能创造候选交易；
- OI/taker 只能削弱 late/crowded 方向；
- 反方向 taker 不给交易加分；
- 仍必须经过 Context、Setup、Signal、Invalidation、Target Room 和 Trader's Equation。

## 未完成

OI/taker 还没有证明 failed breakout 的 trapped traders。

后续 failed breakout 需要的证据链是：

```text
range edge
  -> breakout attracts traders
  -> OI/taker confirms crowding
  -> no follow-through
  -> reversal bar and target room
  -> Trader's Equation
```
