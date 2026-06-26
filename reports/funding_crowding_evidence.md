# Funding Crowding Evidence

日期：2026-06-27

## Brooks rationale

Funding 不是交易信号。

它回答的是 Brooks 语境里的：

```text
这是不是 late bulls / late bears？
同方向交易是否已经拥挤？
现在继续顺势追随，是否更接近趋势中段，还是接近尾端？
```

因此 funding 只能作为 context evidence，不能直接开仓。

## 实现方式

新增：

- `MarketEvidence(funding_rate=...)`
- `ContextScoreboard.funding_crowding_score`
- `funding_crowding_score(...)`

方向解释：

```text
side = LONG, funding > 0 -> 多头拥挤，削弱 long context
side = SHORT, funding < 0 -> 空头拥挤，削弱 short context
反方向 funding -> 不给开仓加分，只是不惩罚
```

惩罚进入两处：

- `context_score`
- `probability_score`

没有进入：

- `candidate_kinds_for_context`
- setup detection

也就是说：

```text
funding 不能创造候选交易，只能降低已有候选的质量。
```

## 参数

```toml
brooks_funding_crowding_threshold = 0.0
brooks_funding_extreme_threshold = 0.0003
brooks_funding_crowding_context_penalty = 0.25
brooks_funding_crowding_probability_penalty = 0.15
```

解释：

- 低于 threshold 的同向 funding 不处理；当前默认从 0 开始处理同向 funding；
- threshold 到 extreme 之间线性映射到 `0..1` crowding score；
- 超过 extreme 视为满分拥挤；
- context/probability penalty 决定削弱幅度。

## 执行链路

已接入：

- backtester：用历史 funding rate 对齐到当前 candle close；
- paper runner：用 premium index 的 `lastFundingRate`；
- live runner：用 premium index 的 `lastFundingRate`。

原 `funding_abs_limit` 仍保留为账户级硬风险闸门。

## Brooks 对齐

这次实现符合以下原则：

- crypto 数据只作为 context evidence；
- 不把 funding 变成信号；
- 高同向 funding 表示 late/crowded risk；
- funding 只是降低交易质量，不替代 K 线 context、invalidation、target room。

## 限制

Funding 只能告诉我们持仓成本和拥挤方向的近似信息。

它不能单独证明：

- trapped traders；
- liquidation cascade；
- CVD 背离；
- breakout 是否真正失败。

后续 OI、taker buy/sell、liquidation 仍应按同样纪律接入 context，而不是直接开仓。
