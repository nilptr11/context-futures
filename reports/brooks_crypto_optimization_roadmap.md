# Brooks Crypto Optimization Roadmap

日期：2026-06-27

## 核心判断

当前问题不是价格行为不适用于加密市场，而是纯 OHLC 版本还没有完整表达 Brooks 的交易过程。

后续优化不能按“多开单、多形态、多参数”推进，必须按 Brooks 的交易链条推进：

```text
Market Context
  -> Candidate Trade
  -> Invalidation
  -> Target Room
  -> Trader's Equation
  -> Setup-specific Calibration
  -> Trade / No Trade
```

## 当前诊断

基于 `2025-01-01` 到 `2026-06-27`、100U、`config.brooks_expanded_20x.example.toml`：

- `TREND_PULLBACK` 质量最高，交易少但贡献稳定。
- `BREAKOUT_PULLBACK` 能提高收益，但空头 breakout pullback 是主要拖累。
- `FAILED_BREAKOUT` 经过更严格 gate 后接近持平，但仍不足以默认启用。
- 20x 合约设置已经存在；收益主要由 `risk_fraction` 和信号质量决定，不由交易所杠杆数字直接决定。

## 已补的工程基础

- `Trade`/`Position` 增加 `entry_reason`、`exit_reason`、`setup_kind`。
- backtest / paper runner 保留入场 setup telemetry。
- 新增 `scripts/analyze_setup_performance.py`，按 setup kind 和 entry reason 汇总胜率、PF、PnL 和平均分数。

## 优化优先级

### 1. 校准 breakout pullback

Brooks rationale:

突破回踩交易只有在突破改变市场共识、回踩守住、并且目标空间足够时才有意义。

下一步：

- 单独分析 `breakout_pullback_bear` 为什么 PF < 1。
- 加入更强的 breakout follow-through 要求。
- 对空头突破加入更强的 higher-timeframe control requirement，避免牛市或强反弹中追空。
- 按多空分别校准 probability，而不是共用 breakout pullback 先验。

当前进展：

- 已加入 breakout control gate：最低控制权、最低控制权差值、空头突破的最大多头控制权。
- `breakout_pullback_bear` 的亏损已下降，但仍未达到可接受 PF。
- 已开始 setup-side-specific probability calibration：多头/空头 breakout 使用不同概率先验，空头 breakout 使用更高的最低 probability/edge 门槛。
- 当前 `breakout_pullback_bear` 已从亏损转为正贡献；下一步必须用 walk-forward 验证 `brooks_breakout_bear_min_probability_score = 0.78` 是否稳健，避免样本内过拟合。
- 后续仍应考虑按 market regime 进一步拆分 breakout 概率。

Walk-forward 结果：

使用 `config.brooks_expanded_20x.example.toml`、100U、固定参数：

| Window | Return | Max DD | Trades | PF |
|---|---:|---:|---:|---:|
| 2024 | 20.97% | -4.91% | 40 | 1.716 |
| 2025 | 33.61% | -6.95% | 53 | 1.779 |
| 2026 YTD | 9.18% | -6.69% | 18 | 1.724 |

结论：

- 当前 breakout 多空校准没有只在 2025-2026 片段上失效。
- 2026 YTD 的 ETH 分支为负，BTC 分支抵消并贡献组合收益。
- 下一步需要按 symbol/regime 分桶，而不是继续全局调一个概率阈值。

### 2. 保留但不默认启用 failed breakout

Brooks rationale:

Failed breakout 的 alpha 来自 trapped traders，不是价格回到区间内。

下一步：

- 必须接入 OI/funding/taker/liquidation 才能证明被困交易者。
- 在没有衍生品证据时，failed breakout 只能作为研究候选。
- 使用更高的 setup-specific probability/edge 门槛。

### 3. 建立 setup-specific calibration

Brooks rationale:

Trader's Equation 不能用同一个启发式概率覆盖所有 setup。

下一步：

- 用 `setup_performance` 报告按 setup_kind、side、symbol、regime 分桶。
- 根据历史分桶结果调整不同 setup 的概率先验。
- 禁止只根据总体收益调参。

### 4. 接入 crypto microstructure evidence

Brooks rationale:

加密永续里的 trapped traders 和 crowding 常体现在 funding、OI、taker flow、liquidation，而不只在 K 线里。

下一步：

- historical OI change。
- taker buy/sell imbalance。
- funding extreme / funding flip。
- liquidation spike / stop-run evidence。

## 当前推荐配置

- 保守生产研究：`config.brooks_price_action_20x_mixed.example.toml`
- 扩展 Brooks 研究：`config.brooks_expanded_20x.example.toml`

`config.brooks_expanded_20x.example.toml` 默认启用：

- `trend_pullback`
- `breakout_pullback`

默认关闭：

- `failed_breakout`

原因：failed breakout 仍未证明稳定 edge。
