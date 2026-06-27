# Brooks 与未来函数审计

日期：2026-06-27

Brooks 策略原则统一见 `brooks_strategy_research.md`。本文只记录未来函数审计结论。

## 结论

当前实现没有发现明确的未来函数。

仍需持续关注：

- `probability_score` 是启发式，不是真实统计胜率。
- breakout/failed-breakout 不能在缺少 trapped trader 证据时随意启用。
- paper/live 的 OI/taker 是近期实时证据，不能拿来解释旧历史回测。
- 旧 CSV 没有 `taker_buy_volume` 时，回测不会伪造 taker 证据。

## 回测时间线

当前流程：

```text
fast candle idx close
  -> signal_at(idx)
  -> next candle open 执行
```

判断：没有用 next candle 生成信号。

## EMA / ATR

实现：

- `ema(values)` 第 `idx` 项只依赖 `0..idx`。
- `atr(candles)` 第 `idx` 项只依赖 `0..idx`。

判断：没有未来函数。

## MarketRegime

实现：

- `classify_market_regime(candles, idx, ...)` 使用 `candles[start:idx+1]`。
- breakout score 使用 `candles[start:idx]` 作为 prior window。
- `TrendFilter.regime_at(close_time)` 只取 `close_time <= current close_time` 的慢周期点。

判断：没有发现未来函数。

## Pullback

实现：

- `detect_pullback_signal(..., idx, ...)` 使用 `start..idx`。
- signal bar 是 `idx`。
- 交易执行在 `idx+1 open`。

判断：没有发现未来函数。

## Funding 证据

实现：

- 回测中 evidence 指针只推进到 `funding_time <= candle.close_time`。
- 资金费现金流指针和 evidence 指针分离。
- 持仓 funding 只在 `funding_time >= entry_time` 后计入。

判断：没有发现未来函数。

## OI / Taker 证据

实现：

- paper/live 使用当前 Binance 近期统计。
- 回测只使用 candle 自带 `taker_buy_volume`。
- 旧 CSV 缺字段时为 `None`，不伪造。

判断：没有历史回测未来函数；paper/live 是实时证据。

## 测试保护

已有 no-lookahead 测试：

```text
修改 idx 之后的未来 K 线，不改变 idx 的信号。
```

这能防止后续有人在 signal 或 context 中误用未来窗口。

## 后续纪律

每次策略增强必须同时回答：

```text
Brooks 逻辑依据：
这个改动回答 control/context/trapped traders/follow-through/invalidation/trader's equation 中的哪一个？

未来函数检查：
这个改动在 idx 时刻能否真实获得？
```

如果任一问题答不清楚，就不进入核心策略。
