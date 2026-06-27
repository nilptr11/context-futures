# Brooks 激进风险回测结果

日期：2026-06-27

策略研究主线见 `brooks_strategy_research.md`。本文只保留激进风险配置的回测结论。

## 研究问题

讨论目标：月收益 50%-100%。

测试方式：

- 每个标的按独立 100U 账户或共享 100U 账户研究。
- 默认使用 20x 逐仓合约参数。
- 重点观察 15%-20% 单笔风险下的收益和回撤。

## 历史单账户候选

筛选条件：收益为正、利润因子 >= 1.2、最大回撤不差于约 60%。

| 标的 | 变体 | 单笔风险 | 收益率 | 最大回撤 | 利润因子 | 50%+ 月份 | 亏损月份 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | baseline | 15% | 329.63% | -48.97% | 2.145 | 3/18 | 3/18 |
| BTCUSDT | baseline | 20% | 428.39% | -57.54% | 1.977 | 3/18 | 3/18 |
| ETHUSDT | scalp_target | 15% | 322.00% | -49.39% | 1.261 | 2/18 | 7/18 |
| ETHUSDT | scalp_target | 20% | 434.69% | -55.96% | 1.212 | 4/18 | 7/18 |
| NEARUSDT | baseline | 15% | 308.23% | -48.18% | 1.618 | 3/18 | 5/18 |
| NEARUSDT | baseline | 20% | 415.88% | -58.95% | 1.499 | 3/18 | 5/18 |

## 当前激进 15% 组合配置

当前配置文件：`configs/strategies/brooks/aggressive_15pct.toml`

策略组成：

- BTCUSDT：`brooks_price_action`，`1h/4h`，双向。
- ETHUSDT：`brooks_price_action`，`30m/4h`，短目标 scalp 配置，双向。
- NEARUSDT：`brooks_price_action`，`1h/4h`，short-only。

共享账户回测命令形态：

```bash
uv run bnq-portfolio-backtest \
  --config configs/strategies/brooks/aggressive_15pct.toml \
  --data-dir data/monthly_2025_now \
  --extra-data-dirs data/alt_research_2024_now \
  --funding-dir data/monthly_2025_now \
  --extra-funding-dirs data/alt_research_2024_now \
  --start 2025-01-01 \
  --end 2026-06-27
```

结果：

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

## 结论

- 该配置可以用于研究回测。
- 它不适合直接实盘，最大回撤已经达到 -59.10%。
- 月收益 50%-100% 应视为高风险配置下的偶发结果，不是稳定生产基线。
- 后续若继续研究高收益目标，应优先提升 setup 质量和风险预算模型，而不是继续放松 Brooks 交易条件。
