# Structural Trade Plan

日期：2026-06-27

## 本次实现

`brooks_price_action` 现在不再只用 ATR 和固定 R 倍数执行。

顺势回调候选会先生成结构化交易计划：

```text
Pullback structure
  -> structural invalidation
  -> measured move target
  -> target_room_r
  -> TradeDecision
```

## 结构止损

多头：

```text
stop = pullback_low - ATR * brooks_structural_stop_buffer_atr
```

空头：

```text
stop = pullback_high + ATR * brooks_structural_stop_buffer_atr
```

保护规则：

- 若结构止损小于 `brooks_structural_stop_min_atr`，扩大到最低 ATR 距离；
- 若结构止损大于 `brooks_structural_stop_max_atr`，候选交易无效；
- 若执行价格跳过结构止损，交易跳过，不回退到普通 ATR stop。

## 结构目标

目标价来自两个候选中的更近有效目标：

- measured move target；
- `profit_target_r_multiple` 目标。

这样不会用过远目标虚增 `target_room_r`。

## 执行链路

已接入：

- backtester；
- paper runner；
- live REST runner。

`Signal` 现在可携带：

```text
stop_price
target_price
```

backtest/paper/live 会优先使用 signal 计划；只有普通策略没有计划价时，才回到原 ATR/R 规则。

live runner 在真实下单时会同时挂 reduce-only `STOP_MARKET` 和可选 reduce-only `TAKE_PROFIT_MARKET`。

## 影响

结构交易计划让交易数下降，止损更符合 Brooks 的“市场在哪里证明我错了”，但不会无条件提高收益。

最新验证见：

```text
reports/brooks_price_action_validation.md
```
