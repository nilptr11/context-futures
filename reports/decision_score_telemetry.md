# Decision Score Telemetry

日期：2026-06-27

## Brooks rationale

优化不应该从“调参数让回测好看”开始。

Brooks 的交易是概率问题，因此下一步应先检查：

```text
Context / Setup / Signal / Target Room / Edge
```

这些分数是否真的对应更好的交易结果。

## 本次实现

`Signal`、`Position`、`Trade` 已保存 Brooks 决策分数：

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

新增脚本：

```bash
PYTHONPATH=src python3 scripts/analyze_trade_scores.py \
  --config config.brooks_price_action_20x_mixed.example.toml \
  --data-dir data \
  --funding-dir data \
  --out reports/decision_score_bins.csv
```

输出：

```text
reports/decision_score_bins.csv
```

## 初步观察

样本：

- BTCUSDT `1h/4h`
- ETHUSDT `30m/4h`
- 61 笔 Brooks price action 交易

### Context Score

| Bin | Trades | Approx Win Rate | PnL |
| --- | ---: | ---: | ---: |
| 0.60-0.65 | 13 | 53.8% | 1294.97 |
| 0.65-0.70 | 29 | 51.7% | 2958.59 |
| 0.70-0.75 | 17 | 58.8% | 2008.93 |

结论：

```text
context_score 有正向意义，但不是线性越高越好。
```

### Probability Score

| Bin | Trades | Approx Win Rate | PnL |
| --- | ---: | ---: | ---: |
| 0.70-0.75 | 24 | 50.0% | 2027.46 |
| 0.75-0.80 | 21 | 61.9% | 3031.21 |
| 0.80-0.85 | 9 | 55.6% | 1071.92 |

结论：

```text
probability_score >= 0.75 目前更有优势。
```

但样本还不够大，不能直接把阈值上调为生产结论。

### Edge Score

| Bin | Trades | Approx Win Rate | PnL |
| --- | ---: | ---: | ---: |
| 1.05-1.10 | 9 | 55.6% | 1001.06 |
| 1.10-1.15 | 7 | 42.9% | 451.15 |
| 1.15-1.20 | 6 | 33.3% | -59.96 |
| 1.20-1.25 | 6 | 50.0% | 494.04 |
| 1.25-1.30 | 7 | 57.1% | 547.39 |
| 1.30-1.35 | 7 | 85.7% | 2086.65 |

结论：

```text
edge_score_r 的高分区有明显优势，但中间区间非单调。
```

这说明当前 `probability_score` 仍是启发式，不能当真实概率。

### Setup Score

`setup_score` 明显非单调：

- 0.75-0.80 表现好；
- 0.80-0.85 表现差；
- 0.95-1.00 又恢复较好。

结论：

```text
setup_score 公式需要重新审查。
```

它可能混合了不同 pullback 类型，或者把“过深/过整齐”的回调误认为高质量。

## 当前优化建议

不建议立刻大幅调参。

更合理的下一步：

1. 将 `probability_score` 拆成可解释子项，避免一个黑箱启发式分数。
2. 单独分析 `setup_score` 的组成：depth、legs、EMA touch、double test、wedge。
3. 把 pullback 类型作为 trade telemetry：H2/L2、double test、wedge 分开统计。
4. 再决定是否提高 `brooks_decision_min_probability_score` 或 `brooks_decision_min_edge_score_r`。

## 风险

当前样本只有 61 笔。

任何直接基于这些分箱调阈值的改动，都有过拟合风险。
