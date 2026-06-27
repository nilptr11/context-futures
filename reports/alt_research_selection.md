# Alt Research Selection

日期：2026-06-27

## 目的

扩展 BTC/ETH 之外的研究池，但不把低流动性或事件驱动噪音直接加入主策略。

Brooks rationale:

价格行为交易依赖群体行为、控制权、突破后的 follow-through 和 trapped traders。小币如果流动性不足或事件驱动过强，K 线形态容易变成随机插针，不适合直接套用 Brooks 候选。

## 研究池

第一批高流动性 alt：

- SOLUSDT
- BNBUSDT
- XRPUSDT
- DOGEUSDT
- AAVEUSDT
- SUIUSDT
- AVAXUSDT
- NEARUSDT
- ADAUSDT

数据：

- `data/alt_research_2024_now`
- 1h 入场周期
- 4h context 周期
- funding 纳入回测
- walk-forward windows: 2024, 2025, 2026 YTD

## 结果摘要

| Symbol | Avg Return | Min Return | Positive Windows | Max DD | Trades | Avg PF | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| NEARUSDT | 19.96% | 18.73% | 3/3 | -11.00% | 47 | 1.868 | candidate |
| XRPUSDT | 8.76% | 0.54% | 3/3 | -15.34% | 36 | 1.329 | watch |
| BNBUSDT | 7.00% | -3.83% | 2/3 | -18.78% | 42 | 1.513 | watch |
| SUIUSDT | 13.16% | -19.39% | 2/3 | -19.84% | 46 | 3.158 | watch |
| AAVEUSDT | 4.49% | -3.61% | 1/3 | -16.41% | 41 | 1.109 | reject |
| ADAUSDT | 1.04% | -1.03% | 2/3 | -15.59% | 50 | 1.055 | reject |
| AVAXUSDT | -8.09% | -17.42% | 0/3 | -20.74% | 44 | 0.739 | reject |
| DOGEUSDT | -2.65% | -15.82% | 1/3 | -21.54% | 38 | 0.867 | reject |
| SOLUSDT | -6.76% | -19.66% | 1/3 | -21.01% | 32 | 0.474 | reject |

## Candidate Configs

新增配置：

- `config.brooks_expanded_20x_alt_research.example.toml`
  - 全 9 个 alt，用于研究，不建议直接生产。
- `config.brooks_expanded_20x_alt_selected.example.toml`
  - NEAR/XRP/BNB/SUI，观察组合。
- `config.brooks_expanded_20x_alt_near.example.toml`
  - NEAR 单币验证。

## Walk-forward

### Full Alt Research Pool

| Window | Return | Max DD | Trades | PF |
|---|---:|---:|---:|---:|
| 2024 | -2.46% | -7.73% | 158 | 0.917 |
| 2025 | 10.77% | -3.55% | 160 | 1.363 |
| 2026 YTD | 3.99% | -4.08% | 58 | 1.390 |

结论：全池不合格，2024 为负。

### Selected Alt Pool

| Window | Return | Max DD | Trades | PF |
|---|---:|---:|---:|---:|
| 2024 | -0.01% | -6.32% | 70 | 1.000 |
| 2025 | 24.75% | -4.34% | 75 | 1.858 |
| 2026 YTD | 11.92% | -3.95% | 26 | 2.383 |

结论：观察组合可继续研究，但 2024 仅持平。

### NEAR Only

| Window | Return | Max DD | Trades | PF |
|---|---:|---:|---:|---:|
| 2024 | 18.73% | -11.00% | 20 | 1.597 |
| 2025 | 22.28% | -9.09% | 16 | 1.914 |
| 2026 YTD | 18.88% | -6.22% | 11 | 2.092 |

结论：NEAR 是当前唯一明确通过初筛的 alt candidate。

## 下一步

1. 先不要把全部 alt 池加入主策略。
2. NEAR 可进入小权重候选组合研究。
3. XRP/BNB/SUI 作为 watchlist，继续按 setup_kind 分桶验证。
4. SOL/DOGE/AVAX/AAVE/ADA 暂不加入。
5. 下一轮需要评估 BTC/ETH + NEAR 的组合级 walk-forward。
