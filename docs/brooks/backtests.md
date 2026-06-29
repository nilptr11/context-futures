# Brooks 历史回测线索

内容基准：2026-06-27

本文维护 Brooks 相关历史回测线索和证据边界。以下结果只说明当前实现和当前配置在本地数据上的历史表现，不证明策略已经贯彻 Brooks 思想。

## 数据边界

组合回测数据目录采用 point-in-time parquet 分区布局：

```text
data/parquet/binance_usdm/klines/interval=<interval>/symbol=<SYMBOL>/year=<YEAR>/part.parquet
data/parquet/binance_usdm/funding/symbol=<SYMBOL>/year=<YEAR>/part.parquet
```

当前通用 Binance USD-M 研究数据集为 `data/parquet/binance_usdm/`，已按 BTCUSDT、ETHUSDT、NEARUSDT、SOLUSDT、BNBUSDT、XRPUSDT、DOGEUSDT、LINKUSDT、AVAXUSDT 和 2023/2024/2025/2026 拆分。每个标的维护 `5m`、`15m`、`30m`、`1h`、`4h` 和 funding。数据按市场和数据类型维护，不按策略维护；每条记录通过 `available_at` 或数据集默认规则确定回测可见时间。

## Universe Matrix 筛选报告

`cf-universe-backtest` 用于全币种、全时间组合的研究矩阵，不用于表达真实组合持仓。2026-06-27 本地运行：

```bash
uv run cf-universe-backtest \
  --profile brooks_trend_only \
  --data-root data/parquet/binance_usdm \
  --start 2023-01-01 \
  --end 2026-06-28 \
  --equity 100 \
  --workers 3 \
  --artifact-root data/backtests
```

该轮覆盖 9 个币种、15 个 `slow >= fast` 时间组合、2023/2024/2025/2026 YTD 和 `2023_now` 五个窗口，共 675 行，全部 `ok`、0 errors。报告输出：

- `data/backtests/<run_id>/matrix_detail.csv`
- `data/backtests/<run_id>/matrix_pivot.csv`
- `data/backtests/<run_id>/matrix_rankings.csv`

`rankings.csv` 中 `2023_now` 总窗口靠前组合：

| symbol | fast/slow | 100U 最终 | 收益率 | 最大回撤 | 交易数 | 胜率 | PF | 年度状态 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| NEARUSDT | 1h/4h | 142.56 | 42.56% | -5.46% | 20 | 65.00% | 3.522 | mixed_years |
| ETHUSDT | 30m/4h | 122.83 | 22.83% | -3.16% | 21 | 57.14% | 2.146 | mixed_years |
| BTCUSDT | 1h/4h | 122.51 | 22.51% | -5.17% | 21 | 57.14% | 2.090 | ok |
| NEARUSDT | 30m/4h | 115.40 | 15.40% | -14.29% | 34 | 44.12% | 1.405 | mixed_years |
| BNBUSDT | 15m/4h | 112.57 | 12.57% | -9.86% | 19 | 52.63% | 1.671 | mixed_years |

初步解读：

- 当前 `brooks_trend_only` 对 `4h` slow context 更敏感，排名靠前组合大多是 `*/4h`。
- BTCUSDT `1h/4h` 是本轮唯一 top 组合中四个年度窗口均为正的候选。
- ETHUSDT `30m/4h` 仍是有效候选，但 2023 为负；需要继续看 regime 分桶而不是直接提高权重。
- NEARUSDT `1h/4h` 总收益最高，但年度状态为 `mixed_years`，不能只因 `2023_now` 排名最高就直接纳入组合。
- 多个短周期组合 `no_trades`，说明当前趋势回踩门槛在过短 slow context 下过严，或者 Brooks 语义本身不适合该周期组合。

## 常规风险配置

当前参考配置：

- `configs/strategies/brooks/price_action_portfolio.toml`
- BTCUSDT `1h/4h`
- ETHUSDT `30m/4h`
- `risk_fraction = 0.02`

本地历史复核线索：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-27 | 48.46% | -6.68% | 33 | 60.61% | 2.513 |
| 2025-01-01 到 2026-06-27 | 28.17% | -5.84% | 18 | 66.67% | 2.872 |

证据边界：

- 交易数太少，不能证明长期稳定性。
- 只说明 `trend_pullback` 作为研究起点有继续分析价值。
- 不证明 breakout/failed breakout 可以启用。
- 不证明当前 `probability_score` 是真实概率。

## Breakout Pullback 研究配置

`configs/strategies/brooks/breakout_pullback_research.toml` 只作为 breakout pullback 研究配置。

该配置在常规配置基础上启用 breakout pullback，并收紧 breakout quality、retest quality、control score、control gap、bear probability 和 bear edge 门槛。

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-27 | 67.15% | -8.05% | 64 | 53.12% | 1.964 |
| 2025-01-01 到 2026-06-27 | 34.26% | -7.38% | 38 | 52.63% | 1.896 |

研究结论：

- breakout pullback 有独立研究价值，但当前利润因子和胜率弱于 `trend_pullback`。
- 直接宽松启用 breakout pullback 会明显放大回撤；严格配置更适合作为研究起点。
- 空头 breakout 样本更少，不能因为少数高 R 交易就放松阈值。
- 该配置不能替代 `price_action_portfolio.toml` 作为当前维护默认配置。

2026-06-27 参数 ablation 复核：

| 变体 | 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| trend only | 2024-01-01 到 2026-06-27 | 48.46% | -6.68% | 33 | 60.61% | 2.513 |
| trend + breakout research | 2024-01-01 到 2026-06-27 | 67.15% | -8.05% | 64 | 53.12% | 1.964 |
| breakout only | 2024-01-01 到 2026-06-27 | 8.89% | -9.96% | 35 | 42.86% | 1.260 |
| breakout strict | 2024-01-01 到 2026-06-27 | 33.25% | -7.91% | 40 | 52.50% | 1.721 |
| trend only | 2025-01-01 到 2026-06-27 | 28.17% | -5.84% | 18 | 66.67% | 2.872 |
| trend + breakout research | 2025-01-01 到 2026-06-27 | 34.26% | -7.38% | 38 | 52.63% | 1.896 |
| breakout only | 2025-01-01 到 2026-06-27 | 4.75% | -9.96% | 20 | 40.00% | 1.226 |
| breakout strict | 2025-01-01 到 2026-06-27 | 10.13% | -7.91% | 23 | 47.83% | 1.408 |

分年复核：

| 变体 | 2024 收益/PF/DD | 2025 收益/PF/DD | 2026 YTD 收益/PF/DD |
| --- | ---: | ---: | ---: |
| trend only | 15.83% / 2.085 / -6.68% | 16.87% / 2.769 / -3.16% | 9.67% / 3.050 / -3.11% |
| trend + breakout research | 24.49% / 2.113 / -8.05% | 20.78% / 1.696 / -7.38% | 11.17% / 2.601 / -4.65% |
| breakout only | 3.95% / 1.320 / -8.96% | 3.35% / 1.179 / -9.96% | 1.36% / 1.598 / -2.38% |
| breakout strict | 21.00% / 2.304 / -6.68% | 3.37% / 1.169 / -7.45% | 6.54% / 2.387 / -3.11% |

ablation 结论：

- `breakout_pullback` 不是独立稳定 alpha；`breakout only` 在主要窗口收益低、回撤更高、PF 较弱。
- `trend + breakout research` 提高总收益，但以更多交易、更低胜率、更低 PF 和更高回撤为代价。
- 简单收紧 breakout quality / retest / control / target / edge 后，2025 表现明显恶化，说明“更严格”不等于更符合 Brooks。
- 当前不调整生产参数；继续保持 `price_action_portfolio.toml` 为 trend-only 基线。
- breakout 下一步应研究失败后的表现、follow-through 强度、突破后的第二腿和目标空间，而不是继续盲调阈值。

## 激进风险配置

`configs/strategies/brooks/aggressive_15pct.toml` 只作为风险放大实验，不作为 Brooks 策略证明。

当前结构化数据集 `data/parquet/binance_usdm/`，2025-01-01 到 2026-06-27 共享账户回测：

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

本轮重构复盘结论：

- `aggressive_15pct` 是高风险回归基线；新架构必须先复现或接近旧收益路径，再讨论是否继续引入 Brooks 结构证据。
- 错误重构曾把未校准的 structure/setup 证据直接加入 `probability_score`，并让 structure magnet 改变目标选择，导致回测退化到最终权益 `1466.55`、回撤 `-66.60%`、交易数 `133`、胜率 `50.38%`、利润因子 `1.290`。
- 修复后只回到 `5602.93` 的剩余差距来自 channel 被错误排除在 trend pullback 之外；2026-02-10 的两笔 NEARUSDT channel pullback 高质量交易被跳过。
- Brooks 语义下 channel 仍是趋势结构的一种表现；把 channel 纳入 `trend_pullback` 扫描后，101 笔交易 entry/exit/setup 与归档报告完全匹配，PnL 汇总为 `6607.48623732`。
- 后续任何 Brooks 新证据必须先以 telemetry 和 decision journal 分桶验证；未校准前不得改变 Trader's Equation、target selection 或 position path。

分年独立回测线索：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 | 资金费率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2025-01-01 | 73.85% | -50.81% | 59 | 45.76% | 1.131 | -6.71 |
| 2025-01-01 到 2026-01-01 | 1809.23% | -43.31% | 71 | 57.75% | 1.585 | 2.25 |
| 2026-01-01 到 2026-06-27 | 251.32% | -56.38% | 30 | 53.33% | 1.665 | 0.49 |

结论：

- 可作为研究配置。
- 不应直接用于实盘。
- 该结果主要说明风险预算可以放大收益和回撤，不证明策略具备稳定月收益 50%-100% 的生产能力。
- 不能用该结果反向合理化放松 Brooks 条件。
