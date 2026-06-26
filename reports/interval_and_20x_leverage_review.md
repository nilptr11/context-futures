# Interval and 20x Leverage Review

日期：2026-06-27

## 结论

胜率和收益不合格时，不应简单把周期降到 `15m`，也不应直接把名义仓位拉满到 `20x`。

本轮测试结论：

1. `15m` 明显更噪声，BTC/ETH 都不理想。
2. `30m` 对 ETH 有改善，但对 BTC 变差。
3. 更合理的做法是 **按品种分周期**：
   - BTCUSDT: `1h` entry + `4h` context
   - ETHUSDT: `30m` entry + `4h` context，且 ATR/EMA/lookback 按时间尺度放大
4. 20x 应作为保证金效率，不应直接满仓。当前较合理的激进档是：
   - `leverage = 20`
   - `risk_fraction = 0.02`
   - `max_symbol_notional_fraction = 5.0`
   - `max_total_notional_fraction = 8.0`

## 降周期测试

固定 Brooks Pullback 逻辑，4h 作为慢周期上下文。

| Scenario | Symbol | Return | Max DD | Trades | Win Rate | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `1h_base` | BTCUSDT | 11.39% | -5.27% | 53 | 43.40% | 1.425 |
| `1h_base` | ETHUSDT | 2.94% | -8.31% | 58 | 36.21% | 1.078 |
| `30m_native` | BTCUSDT | -8.33% | -13.44% | 117 | 33.33% | 0.851 |
| `30m_native` | ETHUSDT | 6.31% | -10.78% | 93 | 36.56% | 1.113 |
| `15m_native` | BTCUSDT | -25.84% | -30.06% | 196 | 32.14% | 0.645 |
| `15m_native` | ETHUSDT | -5.29% | -22.59% | 192 | 35.94% | 0.944 |
| `30m_scaled` | BTCUSDT | -2.81% | -9.23% | 79 | 36.71% | 0.932 |
| `30m_scaled` | ETHUSDT | 8.39% | -7.13% | 60 | 40.00% | 1.235 |
| `15m_scaled` | BTCUSDT | -3.65% | -9.82% | 56 | 37.50% | 0.845 |
| `15m_scaled` | ETHUSDT | 2.34% | -9.20% | 41 | 39.02% | 1.113 |

解释：

- `native` 表示只改 K 线周期，不改 ATR/EMA/lookback 参数。
- `scaled` 表示保持类似时间尺度：
  - `30m_scaled`: ATR 28, EMA 40, lookback 24
  - `15m_scaled`: ATR 56, EMA 80, lookback 48

## 20x 风险测试

基准仍是 BTC/ETH 都用 `1h_base`。

| Risk | Cap | BTC Return | BTC DD | ETH Return | ETH DD |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0% | 1x | 11.39% | -5.27% | 2.94% | -8.31% |
| 1.0% | 5x | 15.31% | -5.30% | 2.94% | -8.31% |
| 1.5% | 3x | 22.48% | -7.89% | 4.00% | -12.23% |
| 2.0% | 5x | 31.56% | -10.45% | 4.77% | -16.01% |
| 3.0% | 5x | 43.25% | -15.43% | 5.45% | -23.14% |

解释：

- BTC 受名义仓位上限影响更明显，提高 cap 后收益明显改善。
- ETH 策略质量仍弱，提高风险主要放大回撤，收益提升有限。
- `3%` 风险档已经太热，ETH 回撤超过 `23%`，不建议。

## 混合周期 + 20x 结果

方案：

- BTCUSDT: `1h_base`
- ETHUSDT: `30m_scaled`

### Conservative

`risk_fraction = 0.01`, `max_symbol_notional_fraction = 1.0`

| Window | BTC | ETH | Combined |
| --- | ---: | ---: | ---: |
| All | 11.39% | 8.39% | 9.89% |
| Train 2021-2024 | 4.39% | 1.48% | 2.93% |
| Test 2025-2026 | 6.70% | 6.81% | 6.75% |

### Moderate 20x

`risk_fraction = 0.015`, `max_symbol_notional_fraction = 3.0`

| Window | BTC | ETH | Combined |
| --- | ---: | ---: | ---: |
| All | 22.48% | 13.98% | 18.23% |
| Train 2021-2024 | 7.03% | 3.00% | 5.01% |
| Test 2025-2026 | 14.43% | 10.66% | 12.55% |

### Aggressive 20x

`risk_fraction = 0.02`, `max_symbol_notional_fraction = 5.0`

| Window | BTC | ETH | Combined |
| --- | ---: | ---: | ---: |
| All | 31.56% | 18.34% | 24.95% |
| Train 2021-2024 | 9.14% | 3.61% | 6.38% |
| Test 2025-2026 | 20.54% | 14.22% | 17.38% |

### Too Hot

`risk_fraction = 0.03`, `max_symbol_notional_fraction = 5.0`

| Window | BTC | ETH | Combined |
| --- | ---: | ---: | ---: |
| All | 43.25% | 26.45% | 34.85% |
| Train 2021-2024 | 11.60% | 4.24% | 7.92% |
| Test 2025-2026 | 28.36% | 21.30% | 24.83% |

不建议 `3%` 风险档，因为 ETH 单品种回撤接近 `20%`，且该结果仍未做组合级并发资金回测。

## 实施调整

已新增：

- `StrategyConfig.symbols`
- `paper_runner.py` 按策略 `symbols` 过滤交易品种
- `config.brooks_pullback_20x_mixed.example.toml`

这个配置实现：

```text
BTCUSDT -> brooks_pullback_btc_1h
ETHUSDT -> brooks_pullback_eth_30m
```

## 当前建议

不建议：

- 直接切到 `15m`
- 直接用 `20x` 满名义仓位
- 把 ETH 和 BTC 强行使用同一入场周期

建议：

1. 用 `config.brooks_pullback_20x_mixed.example.toml` 做下一轮 paper。
2. 风险档先在 `risk_fraction = 0.015` 到 `0.02` 之间选择。
3. 如果目标是更稳，先用 moderate 20x。
4. 如果目标是更高收益，可用 aggressive 20x，但必须接受 BTC 约 `-10%`、ETH 约 `-13%` 级别的单品种回撤，组合实盘还可能更复杂。
