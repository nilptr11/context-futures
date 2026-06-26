# Brooks and Lookahead Audit

日期：2026-06-27

## 结论

需要定期做这类审计。

当前实现总体仍然沿着 Brooks 的核心思想推进：

```text
Market Context
  -> Evidence
  -> Candidate Trade
  -> Invalidation
  -> Trader's Equation
  -> Trade / No Trade
```

没有发现明确的未来函数。

但仍有几类风险需要继续盯：

- `probability_score` 仍是启发式，不是真实统计胜率；
- breakout/failed-breakout 还没有足够 trapped trader evidence，不能随意启用；
- paper/live 的 OI/taker 是近期实时 evidence，不能拿来解释旧历史回测；
- 当前回测使用旧 CSV 时没有 `taker_buy_volume`，不会伪造 taker evidence。

## Brooks 思想对照

### 1. Context 先于形态

当前实现：

- `ContextState` 只是标签；
- `ContextScoreboard` 才进入交易决策；
- `candidate_kinds_for_context` 只产生候选类型，不直接交易。

判断：

```text
符合 Brooks。
```

风险：

- 如果后续为了交易数启用 `breakout_pullback` 或 `failed_breakout`，必须先补完整 evidence。

### 2. Always-In 是控制权

当前实现：

- `always_in_bull_score` / `always_in_bear_score`；
- `control_gap`；
- trend pullback 必须通过 Always-In threshold。

判断：

```text
方向正确，但仍偏工程近似。
```

缺口：

- 反方向尝试失败；
- time above/below value；
- pullback holding structure；
- follow-through after signal。

这些还可以继续增强 Always-In 的行为解释力。

### 3. Trading Range 默认 No Trade

当前实现：

- range score 超过阈值时 trend pullback 不能产生候选；
- failed breakout 默认关闭；
- 已有测试保护。

判断：

```text
符合 Brooks。
```

### 4. 形态只是 evidence

当前实现：

- `PullbackSignal`、`SetupSignal` 都只进入 `TradeCandidate`；
- 只有 `TradeDecision.accepted` 才生成 `Signal`。

判断：

```text
符合 Brooks。
```

### 5. Invalidation 先于交易

当前实现：

- trend pullback 使用结构低点/高点加 ATR buffer；
- 结构止损太远则跳过；
- backtest/paper/live 都执行 signal 计划 stop/target。

判断：

```text
符合 Brooks 的“在哪里证明我错了”。
```

缺口：

- breakout/failed-breakout 还没有结构化 invalidation。

### 6. Crypto evidence 只能辅助 context

当前实现：

- funding 只削弱同方向拥挤；
- OI/taker 只削弱同方向主动成交 + 新仓拥挤；
- 这些 evidence 不会创造候选交易。

判断：

```text
符合 Brooks，也符合加密衍生品特性。
```

## 未来函数审计

### Backtest 时间线

当前流程：

```text
fast candle idx close
  -> signal_at(idx)
  -> next candle open 执行
```

判断：

```text
没有用 next candle 生成信号。
```

### EMA / ATR

实现：

- `ema(values)` 第 `idx` 项只依赖 `0..idx`；
- `atr(candles)` 第 `idx` 项只依赖 `0..idx`。

判断：

```text
没有未来函数。
```

### MarketRegime

实现：

- `classify_market_regime(candles, idx, ...)` 使用 `candles[start:idx+1]`；
- breakout score 使用 `candles[start:idx]` 作为 prior window；
- `TrendFilter.regime_at(close_time)` 只取 `close_time <= current close_time` 的慢周期点。

判断：

```text
没有发现未来函数。
```

### Pullback

实现：

- `detect_pullback_signal(..., idx, ...)` 使用 `start..idx`；
- signal bar 是 `idx`；
- 交易执行在 `idx+1 open`。

判断：

```text
没有发现未来函数。
```

### Funding evidence

实现：

- 回测中 evidence 指针只推进到 `funding_time <= candle.close_time`；
- 资金费现金流指针和 evidence 指针分离；
- 持仓 funding 只在 `funding_time >= entry_time` 后计入。

判断：

```text
没有发现未来函数。
```

### OI / Taker evidence

实现：

- paper/live 使用当前 Binance 近期统计；
- 回测只使用 candle 自带 `taker_buy_volume`；
- 旧 CSV 缺字段时为 `None`，不伪造。

判断：

```text
没有历史回测未来函数；paper/live 是实时 evidence。
```

## 已补测试

新增 no-lookahead 测试：

```text
修改 idx 之后的未来 K 线，不改变 idx 的信号。
```

这能防止后续有人在 signal 或 context 中误用未来窗口。

## 后续纪律

每次策略增强必须同时回答两个问题：

```text
Brooks rationale:
这个改动回答 control/context/trapped traders/follow-through/invalidation/trader's equation 中的哪一个？

Lookahead check:
这个改动在 idx 时刻能否真实获得？
```

如果任一问题答不清楚，就不进入核心策略。
