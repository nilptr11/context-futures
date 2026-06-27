# Brooks 策略研究总览

日期：2026-06-27

本文是 Al Brooks 策略研究的唯一主文档。其他报告只记录架构、审计或具体回测结果，不再分散保存 Brooks 策略原则和研究路线。

## 核心判断

Brooks 的核心不是形态识别，也不是场景路由，而是交易前的市场阅读：

```text
市场上下文
  -> 证据
  -> 候选交易
  -> Invalidation
  -> 目标空间
  -> Trader's Equation
  -> 交易 / 不交易
```

因此，策略实现必须避免两类错误：

- 把 H2/L2、wedge、breakout、failed breakout 直接当作开仓信号。
- 为了增加交易数，直接打开更多 setup，而不检查目标空间、成本、胜率和结构止损。

## 交易原则

### 1. 先判断谁在控制市场

Brooks 的第一问题不是“有没有形态”，而是：

```text
多头还是空头在控制？
控制权强不强？
反方尝试是否失败？
```

实现要求：

- `Always-In` 必须表示控制权，不只是 EMA 趋势过滤。
- 多空控制权要有差值，不能只看单边分数。
- 反方向失败、follow-through、time above/below value 后续要进入评分。

当前实现：

- 已有 `always_in_bull_score` / `always_in_bear_score`。
- 已有 `control_gap`。
- 反方向失败证据仍偏弱，后续需要补。

### 2. Context 是连续证据，不是交易开关

`ContextState` 只能是标签，不能写成：

```text
if state == X:
    trade
```

当前 `brooks_price_action` 已从旧 router 改为：

```text
ContextScoreboard
  -> 候选 Setup
  -> 上下文 / Setup / 信号 / 位置分数
  -> 目标空间和成本
  -> 概率分数和 Edge 分数
  -> 接受或拒绝
```

### 3. 形态只是证据，不是信号

H2、L2、wedge、double test、breakout、failed breakout 都只能产生候选交易。

```text
形态 -> 候选交易 -> Trader's Equation -> 交易 / 不交易
```

当前实现：

- `PullbackSignal` 和 `SetupSignal` 只进入候选交易。
- `Signal` 只在 `TradeDecision.accepted` 后生成。

### 4. Trading Range 默认 No Trade

Brooks 对 trading range 的提醒不是“做均值回归”，而是“多数方向判断会失败”。

实现要求：

- trend pullback 不允许在 range 中自动开仓。
- range 中只允许非常具体的边缘/失败突破候选。
- 区间中部交易默认禁止。

当前实现：

- `candidate_kinds_for_context` 对 trend pullback 有 range gate。
- failed breakout 默认关闭。
- 测试已保护 range 默认不会产生 trend pullback 候选。

### 5. Breakout 看后续，而不是看突破本身

breakout 的关键是：

```text
breakout 后是否有 follow-through？
是否改变市场共识？
回踩是否守住？
```

实现要求：

- 突破 K 不能单独成为信号。
- breakout pullback 必须有突破质量、回踩质量、目标空间。
- 没有 follow-through 的 breakout 更接近 failed breakout 证据链。

当前状态：

- breakout pullback 可作为研究候选，但不应默认生产启用。
- 当前候选评分仍需补完整 trapped trader、follow-through 和结构目标。

### 6. Failed Breakout 必须证明 trapped traders

Failed breakout 的 alpha 不来自“价格回来了”，而来自错误方向交易者被困。

实现要求：

- range 边界真实。
- 突破后缺乏 follow-through。
- 回到区间后有反向强度。
- 目标到区间中轴或另一边有足够空间。
- 加密永续中应加入 funding/OI/taker/liquidation 作为拥挤度证据。

当前状态：

- failed breakout 默认关闭。
- 当前实现还没有充分 trapped trader evidence。

### 7. 入场前先定义在哪里错

Brooks 的交易必须有 invalidation。

实现要求：

- 顺势回调用结构高低点做 invalidation。
- 不能只因为 ATR 止损方便就忽略结构。
- 结构止损太远时跳过交易，而不是硬做。

当前实现：

- 已实现顺势回调结构止损。
- 回测执行优先使用 signal 计划价格。
- breakout/failed breakout 还没有结构化 invalidation。

### 8. Trader's Equation 必须在最终入口

交易不是“信号出现”，而是：

```text
概率 * 回报 - 风险 - 成本 > 阈值
```

实现要求：

- context、setup、signal、location、target room、cost 都要进入决策。
- 单个指标不能绕过决策层。
- 回测调参不能把 `decision_min_edge_score_r` 变成摆设。

当前状态：

- 已有 `probability_score` 和 `edge_score_r`。
- 当前 probability 仍是启发式，需要用样本统计校准。

## 当前实现

当前主策略是 `brooks_price_action`。

它取代了旧 `brooks_context_router`，不再保留兼容 alias。旧模型：

```text
ContextState -> SetupKind -> Signal
```

新模型：

```text
MarketContext -> 候选交易 -> Trader's Equation -> TradeDecision
```

当前默认可用分支：

- `trend_pullback`：已验证，是主路径。

当前研究候选：

- `breakout_pullback`：可以提高收益，但需要按多空、标的和市场状态校准。
- `failed_breakout`：暂不启用，必须先证明 trapped traders。

当前已完成工程基础：

- `SignalDiagnostics` 保存 Brooks 决策分数。
- `Trade` 保留 `entry_reason`、`exit_reason`、`setup_kind` 和诊断分数。
- `bn_quant.reporting.write_trades_csv` 展平诊断字段。
- `ExecutionEngine` 统一执行结构止损、目标价、费用、滑点和 funding。

## 加密市场证据

Crypto 数据只能作为上下文证据，不能直接创造交易。

当前已支持：

- funding：削弱同方向拥挤。
- taker buy ratio：识别同方向主动成交拥挤。
- open interest change：辅助判断新仓拥挤。

当前仍缺：

- liquidation spike / stop-run 证据。
- 更长历史的 OI/taker 数据。
- 对 failed breakout 中 trapped traders 的统计验证。

接入纪律：

- funding 高只能说明拥挤或 late risk。
- OI 增减必须结合价格方向解释。
- taker imbalance 只能削弱追随拥挤方向，不能给反向交易直接加分。
- liquidation 要判断是 climax、stop-run，还是普通波动。

## 策略族优先级

### 第一优先级

- `trend_pullback`：当前主路径。
- `brooks_price_action` 的结构止损和 Trader's Equation：继续完善。
- setup 专属校准：按 setup_kind、side、symbol、regime 分桶。

### 第二优先级

- `breakout_pullback`：补 breakout quality、follow-through、retest quality、target room。
- measured move target：用于目标空间和出场过滤。
- crypto crowding evidence：用于 late/crowded 风险惩罚。

### 暂不启用

- `failed_breakout`：证据链不足。
- trading range fade：容易退化成区间网格。
- major trend reversal / climax reversal：逆势误判风险高，先做过滤器或退出逻辑。

## 验证结论

### 价格行为验证

同口径 `2025-01-01` 之后样本外结果：

| 策略 | 标的 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `brooks_pa_btc_1h` | BTCUSDT | 11.99% | -3.03% | 5 | 80.00% | 6.316 |
| `brooks_pa_eth_30m` | ETHUSDT | 14.45% | -3.16% | 13 | 61.54% | 2.199 |

结论：

- `trend_pullback` 主路径可继续研究。
- breakout/failed-breakout 还没有证明可默认启用。
- 当前 `configs/strategies/brooks/price_action_portfolio.toml` 是已验证 Brooks PA 组合配置形态。

### 激进 15% 风险研究

`configs/strategies/brooks/aggressive_15pct.toml` 可运行研究回测，但风险极高。

2025-01-01 到 2026-06-27 共享账户回测：

| 指标 | 数值 |
| --- | ---: |
| 初始权益 | 100.00 |
| 最终权益 | 6707.49 |
| 总收益率 | 6607.49% |
| 最大回撤 | -59.10% |
| 交易数 | 101 |
| 胜率 | 56.44% |
| 利润因子 | 1.641 |
| 资金费率 | 11.62 |

结论：

- 可作为研究配置。
- 不应直接用于实盘。
- 该结果主要说明风险预算可以放大收益和回撤，不证明策略具备稳定月收益 50%-100% 的生产能力。

## 决策分数研究

现有样本观察：

- `context_score` 有正向意义，但不是线性越高越好。
- `probability_score >= 0.75` 目前更有优势，但样本不足。
- `edge_score_r` 高分区有优势，中间区间非单调。
- `setup_score` 公式需要重审，可能混合了不同 pullback 类型。

后续研究方式：

1. 将 `probability_score` 拆成可解释子项。
2. 单独分析 setup 构成：深度、腿数、EMA 触碰、double test、wedge。
3. 按 `setup_kind`、side、symbol、regime 分桶。
4. 再决定是否调整 `decision_min_probability_score` 或 `decision_min_edge_score_r`。

## 后续路线

1. 保持 `trend_pullback` 为主路径，不急着增加更多 setup。
2. 将 `breakout_pullback` 拆成多空、标的、regime 分桶验证。
3. 为 failed breakout 补完整 trapped trader 证据链。
4. 重建 research 模块，用代码生成 setup performance 报告，而不是恢复旧脚本。
5. 接入更可靠的历史 OI/taker/liquidation 数据后，再验证 crypto crowding evidence。
6. 所有策略增强必须同时通过 Brooks 逻辑检查和未来函数检查。

## 实现纪律

每次新增功能前先写清楚：

```text
Brooks 逻辑依据：
这个改动回答 control/context/trapped traders/follow-through/invalidation/trader's equation 中的哪一个？

未来函数检查：
这个改动在 idx 时刻能否真实获得？
```

如果任一问题答不清楚，就不进入策略核心。
