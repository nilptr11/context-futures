# Brooks Price Action Refactor

日期：2026-06-27

## 本次重构结论

上一版 `brooks_context_router` 已被替换为 `brooks_price_action`。

核心变化不是改名，而是决策模型变化：

```text
旧版：ContextState -> SetupKind -> Signal
新版：MarketContext -> Candidate Trade -> Trader's Equation -> TradeDecision
```

这更接近 Al Brooks 的思想：形态不是信号，形态只是证据。交易必须同时回答：

- 谁在控制市场；
- 控制权是否足够强；
- setup 是否发生在合理位置；
- signal bar 是否有足够质量；
- 目标空间是否足够；
- 扣除成本后是否仍有正向 edge。

## 新增实现

- `context_engine.py`
  - `MarketContext`
  - `ContextScoreboard`
  - `TradeCandidate`
  - `TradeDecision`
  - `candidate_kinds_for_context`
  - `pullback_candidate`
  - `setup_candidate`
  - `evaluate_candidate`
- `strategy.py`
  - 新策略类：`BrooksPriceActionStrategy`
  - 注册名：`brooks_price_action`
- `setups.py`
  - `SetupSignal` 现在携带 `signal_bar_score`
- `models.py`
  - 删除旧 `context_*` 参数
  - 新增 `brooks_*` 候选开关和决策门槛

## 现在如何理解策略

`brooks_price_action` 不是“多场景策略合集”。

它是一个统一交易决策框架：

```text
Context Scoreboard
  -> Candidate Setup
  -> Context / Setup / Signal / Location Scores
  -> Target Room and Cost
  -> Probability Score and Edge Score
  -> Accepted or Rejected
```

当前默认只启用 trend pullback 候选，因为它是已有回测中唯一通过验证的分支。

`breakout_pullback` 和 `failed_breakout` 仍保留为候选生成器，但默认关闭。开启后也不会直接交易，必须通过统一决策层。

## 重要取舍

本次按目标架构重构，没有为旧 `brooks_context_router` 注册名做兼容 alias。

对应示例配置已改为：

```text
config.brooks_price_action_20x_mixed.example.toml
```

## 仍未完成

这次已完成第一版 Trader's Equation，并在后续补上了顺势回调的结构化交易计划。

已完成：

- 顺势回调结构 invalidation；
- measured move target；
- signal 级 `stop_price` / `target_price`；
- backtest、paper、live 对计划价格的执行。

还没有完成：

- funding/OI/taker buy-sell/liquidation 等 crypto crowding evidence；
- 对 breakout/failed-breakout 候选的高质量长样本验证。

下一步不应急着加更多形态，而应先把 target/invalidation/crowding evidence 做扎实。
