# Brooks 价格行为验证结果

日期：2026-06-27

策略原则、候选 setup、实现纪律和后续路线统一见 `brooks_strategy_research.md`。本文只保留可对照的回测结果。

## 配置口径

- 当前维护配置形状：`configs/strategies/brooks/price_action_portfolio.toml`
- BTCUSDT：`1h` 入场周期 + `4h` 上下文周期
- ETHUSDT：`30m` 入场周期 + `4h` 上下文周期
- `risk_fraction = 0.02`
- `max_symbol_notional_fraction = 5.0`
- `max_total_notional_fraction = 8.0`
- `leverage = 20`
- funding、手续费、滑点计入回测

## 重构后同口径复核

本次架构重构后，使用当前代码和本地 `data/monthly_2025_now` 数据复核 `2025-01-01` 之后样本外结果：

| 策略 | 标的 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `brooks_pa_btc_1h` | BTCUSDT | 11.99% | -3.03% | 5 | 80.00% | 6.316 |
| `brooks_pa_eth_30m` | ETHUSDT | 14.45% | -3.16% | 13 | 61.54% | 2.199 |

结果与重构前报告口径一致。

## 当前本地数据全样本

当前本地可用数据从 `2024-01-01` 到 `2026-06-26`，不等同于旧报告全样本。

| 策略 | 标的 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `brooks_pa_btc_1h` | BTCUSDT | 20.46% | -4.71% | 15 | 60.00% | 2.539 |
| `brooks_pa_eth_30m` | ETHUSDT | 23.24% | -3.16% | 18 | 61.11% | 2.425 |

## 共享账户组合

使用 `configs/strategies/brooks/price_action_portfolio.toml`：

| 区间 | 收益率 | 最大回撤 | 交易数 | 胜率 | 利润因子 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024-01-01 到 2026-06-26 | 48.46% | -6.68% | 33 | 60.61% | 2.513 |
| 2025-01-01 到 2026-06-27 | 28.17% | -5.84% | 18 | 66.67% | 2.872 |

## 结论

- 当前维护的 Brooks PA 配置可以继续作为主研究基线。
- 该验证只证明 `trend_pullback` 主路径有效，不证明 breakout/failed-breakout 可默认启用。
- 后续策略研究不要分散到本文，统一维护在 `brooks_strategy_research.md`。
