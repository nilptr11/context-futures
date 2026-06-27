# Brooks 决策分数遥测结果

日期：2026-06-27

策略研究主线见 `brooks_strategy_research.md`。本文只保留分数遥测字段和已有分箱观察。

## 遥测字段

Brooks 决策分数统一保存在 `SignalDiagnostics` 中，并随 `Signal`、`Position`、`Trade` 传递。交易 CSV 输出由 `context_futures.reporting.write_trades_csv` 展平这些字段：

- `context_score`
- `setup_score`
- `signal_score`
- `location_score`
- `target_room_r`
- `probability_score`
- `edge_score_r`
- `funding_crowding_score`
- `taker_crowding_score`
- `open_interest_crowding_score`
- `external_crowding_score`

## 样本

- BTCUSDT `1h/4h`
- ETHUSDT `30m/4h`
- 61 笔 Brooks 价格行为交易

## 分箱观察

### 上下文分数

| 分箱 | 交易数 | 近似胜率 | PnL |
| --- | ---: | ---: | ---: |
| 0.60-0.65 | 13 | 53.8% | 1294.97 |
| 0.65-0.70 | 29 | 51.7% | 2958.59 |
| 0.70-0.75 | 17 | 58.8% | 2008.93 |

结论：`context_score` 有正向意义，但不是线性越高越好。

### 概率分数

| 分箱 | 交易数 | 近似胜率 | PnL |
| --- | ---: | ---: | ---: |
| 0.70-0.75 | 24 | 50.0% | 2027.46 |
| 0.75-0.80 | 21 | 61.9% | 3031.21 |
| 0.80-0.85 | 9 | 55.6% | 1071.92 |

结论：`probability_score >= 0.75` 目前更有优势，但样本不足。

### Edge 分数

| 分箱 | 交易数 | 近似胜率 | PnL |
| --- | ---: | ---: | ---: |
| 1.05-1.10 | 9 | 55.6% | 1001.06 |
| 1.10-1.15 | 7 | 42.9% | 451.15 |
| 1.15-1.20 | 6 | 33.3% | -59.96 |
| 1.20-1.25 | 6 | 50.0% | 494.04 |
| 1.25-1.30 | 7 | 57.1% | 547.39 |
| 1.30-1.35 | 7 | 85.7% | 2086.65 |

结论：`edge_score_r` 的高分区有优势，但中间区间非单调。

### Setup 分数

`setup_score` 明显非单调：

- 0.75-0.80 表现好。
- 0.80-0.85 表现差。
- 0.95-1.00 又恢复较好。

结论：`setup_score` 公式需要重新审查，可能混合了不同 pullback 类型。

## 后续分析口径

后续分析应基于 `context_futures.backtesting` 产生 `BacktestReport`，再按 `report.trades[*].diagnostics` 分桶。

优先分桶维度：

- `setup_kind`
- side
- symbol
- regime
- funding/taker/OI 拥挤分数
