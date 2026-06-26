# Brooks Pullback Validation

日期：2026-06-27

## 数据

数据来自 Binance USD-M futures REST API，周期覆盖 `2021-01-01` 到 `2026-06-27` UTC exclusive。

| Symbol | 1h Candles | 4h Candles | Funding Rows |
| --- | ---: | ---: | ---: |
| BTCUSDT | 48,066 | 12,017 | 6,009 |
| ETHUSDT | 48,066 | 12,017 | 6,009 |

## 第一轮默认参数结果

刚实现后的默认参数过松，不合格。

| Symbol | Return | Max DD | Trades | Win Rate | PF | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | -30.63% | -45.02% | 373 | 26.81% | 0.854 | -561.01 |
| ETHUSDT | -18.22% | -47.27% | 394 | 28.68% | 0.906 | -567.80 |

原因：

- Always-In 过滤不够严格。
- 信号 K 质量阈值过低。
- 回调深度过浅。
- 没有 Brooks measured move / trader's equation 风格目标位，全部靠 stop/trailing 退出。

## 当前保守参数

当前 `config.brooks_pullback.example.toml` 使用：

```toml
profit_target_r_multiple = 2.0
brooks_always_in_threshold = 0.80
brooks_range_score_max = 0.55
brooks_pullback_min_depth_atr = 1.2
brooks_pullback_min_signal_score = 0.75
```

含义：

- 只在更明确的 4h Always-In 背景下交易。
- 更严格排除 trading range。
- 1h 回调至少达到 `1.2 ATR`。
- 信号 K 必须更强。
- 以 `2R` 作为第一版固定目标位。

## 全周期结果

| Symbol | Return | Max DD | Trades | Win Rate | PF | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 11.39% | -5.27% | 53 | 43.40% | 1.425 | -74.99 |
| ETHUSDT | 2.94% | -8.31% | 58 | 36.21% | 1.078 | -92.29 |

组合粗略合并：

- 总收益约 `7.17%`，按 BTC/ETH 各 10,000 初始资金等权计算。
- 最大回撤需要组合级事件回测进一步确认，不能简单取单品种回撤平均。

## 训练 / 样本外

| Window | Symbol | Return | Max DD | Trades | Win Rate | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2021-2024 train | BTCUSDT | 4.39% | -5.27% | 43 | 37.21% | 1.185 |
| 2021-2024 train | ETHUSDT | 3.70% | -4.78% | 35 | 37.14% | 1.175 |
| 2025-2026 test | BTCUSDT | 6.70% | -1.80% | 10 | 70.00% | 3.308 |
| 2025-2026 test | ETHUSDT | -0.73% | -8.31% | 23 | 34.78% | 0.955 |

解读：

- 样本外 BTC 表现好，但只有 10 笔，统计不足。
- 样本外 ETH 接近打平但略负，仍需改进。
- 当前版本可以进入 paper 观察，不应该直接实盘。

## 年度结果

| Year | BTC Return | ETH Return | Equal-Weight Combined |
| --- | ---: | ---: | ---: |
| 2021 | -0.29% | -3.29% | -1.79% |
| 2022 | 0.18% | 2.23% | 1.21% |
| 2023 | 0.48% | 3.51% | 2.00% |
| 2024 | 4.00% | 1.33% | 2.66% |
| 2025 | 2.70% | -0.05% | 1.33% |
| 2026 YTD | 3.89% | -0.68% | 1.61% |

## 当前结论

`brooks_pullback` 从第一版不合格，经过 Brooks 逻辑收紧和 `2R` 目标位后，已经变成低频、低回撤、组合为正的候选策略。

但它还没有达到直接实盘标准：

- ETH 样本外仍偏弱。
- 样本外交易数偏少。
- 当前回测仍是单品种分别跑，不是组合级事件回测。
- 目标位是固定 `2R`，还不是真正的 measured move / prior swing target。

## 下一步

1. 将 `brooks_pullback_1h` 放入多策略 paper，与 `breakout_4h_pa`、`brooks_breakout_4h` 并行。
2. 增加组合级多策略回测，真实模拟 BTC/ETH 共用资金和名义仓位上限。
3. 继续研究 ETH 多头弱的问题，优先看：
   - ETH long 是否需要更高 signal score；
   - 是否只在 `TREND_UP` 而不是 `CHANNEL_UP` 做多；
   - 是否用 measured move / swing high 替代固定 `2R`。
