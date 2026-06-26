# Brooks Alignment Checklist

日期：2026-06-27

## 目的

后续实现不能只追求回测收益，也不能把 Brooks 简化成形态识别或场景路由。

每次新增策略模块、指标或过滤器前，都要先回答：

```text
这个改动是在强化 Brooks 的市场阅读，还是只是在堆参数？
```

## 核心检查清单

### 1. 先判断谁在控制市场

Brooks 的第一问题不是“有没有形态”，而是：

```text
多头还是空头在控制？
控制权强不强？
反方尝试是否失败？
```

实现要求：

- `Always-In` 必须表示控制权，不只是 EMA 趋势过滤；
- 多空控制权要有差值，不只看单边分数；
- 反方向失败、follow-through、time above/below value 后续要进入评分。

当前状态：

- 已有 `always_in_bull_score` / `always_in_bear_score`；
- 已有 `control_gap`；
- 反方向失败证据仍偏弱，后续需要补。

### 2. Context 是连续证据，不是交易开关

Brooks 的 context 不是简单枚举。

实现要求：

- `ContextState` 只能作为标签；
- 交易必须看 `ContextScoreboard`；
- 不允许直接写成 `if state == X: trade`。

当前状态：

- `brooks_price_action` 已从 router 改为 candidate + decision；
- `candidate_kinds_for_context` 只决定候选类型，不直接产生交易；
- 仍要警惕 breakout/failed-breakout 被重新写成事件触发器。

### 3. 形态只是 evidence，不是 signal

H2、L2、wedge、double test、breakout、failed breakout 都不能直接下单。

实现要求：

```text
Pattern -> Candidate -> Trader's Equation -> Trade/No Trade
```

当前状态：

- `PullbackSignal` 只进入 `TradeCandidate`；
- `SetupSignal` 只进入 `TradeCandidate`；
- `Signal` 只在 `TradeDecision.accepted` 后生成。

### 4. Trading Range 默认 No Trade

Brooks 对 trading range 的核心提醒不是“做均值回归”，而是：

```text
多数方向判断会失败。
```

实现要求：

- trend pullback 不允许在 range 中自动开仓；
- range 中只允许非常具体的边缘/失败突破候选；
- 区间中部交易必须默认禁止。

当前状态：

- `candidate_kinds_for_context` 对 trend pullback 有 range gate；
- failed breakout 默认关闭；
- 已增加测试保护：range 默认不会产生 trend pullback 候选。

### 5. Breakout 看后续，而不是看突破本身

Brooks 判断 breakout 的关键是：

```text
breakout 后是否有 follow-through？
是否改变市场共识？
回踩是否守住？
```

实现要求：

- 突破 K 不能单独成为信号；
- breakout pullback 必须有突破质量、回踩质量、目标空间；
- 没有 follow-through 的 breakout 要更接近 failed breakout 的证据链。

当前状态：

- breakout pullback 默认关闭；
- 当前候选评分仍不够完整，不能启用为生产策略。

### 6. Failed Breakout 必须证明 trapped traders

Failed breakout 的 alpha 不来自“价格回来了”，而来自错误方向交易者被困。

实现要求：

- range 边界要真实；
- 突破后要缺乏 follow-through；
- 回到区间后要有反向强度；
- 目标到区间中轴/另一边要有空间；
- crypto 中应加入 funding/OI/taker/liquidation 作为拥挤度证据。

当前状态：

- failed breakout 默认关闭；
- 当前实现还没有充分 trapped trader evidence。

### 7. 入场前必须先定义在哪里错

Brooks 的交易必须有 invalidation。

实现要求：

- 顺势回调用结构高低点做 invalidation；
- 不能只因为 ATR 停损方便就忽略结构；
- 结构止损太远时，应该跳过交易，而不是硬做。

当前状态：

- 已实现顺势回调结构止损；
- backtest/paper/live 已使用 signal 计划价格；
- breakout/failed-breakout 还没有结构化 invalidation。

### 8. Trader's Equation 必须在最终入口

交易不是“信号出现”，而是：

```text
Probability * Reward - Risk - Cost > threshold
```

实现要求：

- context、setup、signal、location、target room、cost 都要进入决策；
- 单个指标不能绕过 decision engine；
- 回测调参不能把 `decision_min_edge_score_r` 变成摆设。

当前状态：

- 已有 `probability_score` 和 `edge_score_r`；
- 当前 probability 仍是启发式，后续应由样本统计校准。

### 9. Crypto 数据只能作为 context evidence

Funding、OI、taker buy/sell、liquidation 不能直接变成开仓信号。

实现要求：

- funding 高只能说明拥挤或 late risk；
- OI 增减要结合价格方向解释；
- CVD 背离要进入 momentum/follow-through 证据；
- liquidation 要判断是否 climax 或 stop-run。

当前状态：

- funding 已用于过滤、回测现金流，并作为同方向 crowding evidence 进入 `ContextScoreboard`；
- OI/taker 已作为同方向主动成交和新仓拥挤 evidence 进入 `ContextScoreboard`；
- liquidation 尚未接入。

## 当前实现是否偏离

没有明显偏离，但有三个风险点：

1. `probability_score` 仍然是启发式，容易被误当成真实胜率。
2. breakout/failed-breakout 候选已经存在，后续若为了交易数打开，会偏离 Brooks。
3. crypto crowding evidence 已开始接入，但 failed breakout 的“谁被困住”证据仍不足。

## 后续实现纪律

每次新增功能前先写一句：

```text
Brooks rationale:
```

必须说明这个功能回答的是：

- control；
- context；
- trapped traders；
- follow-through；
- invalidation；
- trader's equation；
- no-trade filter；
- crypto crowding evidence。

如果回答不了，就不应该进入策略核心。
