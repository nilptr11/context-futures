# Brooks Single-Account Optimization

Date: 2026-06-27

Scope:
- Each symbol is treated as its own 100U account.
- Default leverage remains 20x isolated futures.
- Test window: 2025-01-01 to 2026-06-27.
- Target discussed: 50%-100% monthly return.

## Main Finding

The current Brooks logic can produce 50%+ months, but not consistently without very large drawdowns.

At 3% risk per trade, the strategy is too conservative for the stated target. At 10%-20% risk per trade, some months reach 50%-100%+, but max drawdown commonly expands into the 35%-60% area. This means the objective is primarily a risk-budget problem after the Brooks filters are made reasonable; loosening the pattern rules alone does not solve it.

## Best Single-Account Candidates

Filtered for positive return, profit factor >= 1.2, and max drawdown no worse than about 60%.

| Symbol | Variant | Risk/trade | Return | Max DD | PF | 50%+ months | Negative months |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | baseline | 15% | 329.63% | -48.97% | 2.145 | 3/18 | 3/18 |
| BTCUSDT | baseline | 20% | 428.39% | -57.54% | 1.977 | 3/18 | 3/18 |
| ETHUSDT | scalp_target | 15% | 322.00% | -49.39% | 1.261 | 2/18 | 7/18 |
| ETHUSDT | scalp_target | 20% | 434.69% | -55.96% | 1.212 | 4/18 | 7/18 |
| NEARUSDT | baseline | 15% | 308.23% | -48.18% | 1.618 | 3/18 | 5/18 |
| NEARUSDT | baseline | 20% | 415.88% | -58.95% | 1.499 | 3/18 | 5/18 |

Recommended working profile:
- BTCUSDT: keep the current Brooks baseline; use 15% risk only for aggressive testing.
- ETHUSDT: use the short-target variant, because it improved ETH trade harvesting.
- NEARUSDT: keep the current Brooks baseline; it remains the cleanest smaller-coin candidate.

## Rejected Direction

The loose variant increases trade count, but it damages quality. Example: BTC loose at 20% risk produced high average monthly return due to one extreme month, but final return was negative with -95.66% max drawdown and PF below 1.0. This is not a valid optimization path.

## Practical Expectation

Monthly 50%-100% should be treated as an occasional campaign outcome, not a stable monthly baseline. The data supports a high-risk profile that sometimes reaches the target, but a stable 50%-100% every month would require either:
- much more frequent high-quality setups than Brooks currently finds, or
- risk per trade high enough that account-level drawdowns approach failure territory.

Current aggressive template:
- `config.brooks_single_account_aggressive_15pct.example.toml`

Research scripts:
- `scripts/brooks_variant_sweep.py`
- `scripts/portfolio_risk_sweep.py`
- `scripts/portfolio_backtest.py`

Latest result file:
- `reports/brooks_variant_sweep_single_accounts_2025_now.csv`

## Direction Filter Update

Added entry-side filters:
- `allow_long`
- `allow_short`

These filters are applied only before opening a new position. Opposite signals remain available for exits, so a short-only strategy can still detect a bullish reversal signal for closing logic.

Side-mode sweep result file:
- `reports/brooks_variant_side_sweep_single_accounts_2025_now.csv`

Best improved candidate from the side-mode sweep:

| Symbol | Variant | Side mode | Risk/trade | Return | Max DD | PF | 50%+ months | Negative months |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NEARUSDT | scalp_target | short-only | 15% | 303.30% | -27.58% | 3.223 | 2/18 | 4/18 |
| NEARUSDT | scalp_target | short-only | 20% | 487.65% | -35.34% | 2.943 | 2/18 | 4/18 |
| BTCUSDT | baseline | both | 15% | 329.63% | -48.97% | 2.145 | 3/18 | 3/18 |
| ETHUSDT | scalp_target | both | 15% | 322.00% | -49.39% | 1.261 | 2/18 | 7/18 |

Updated aggressive 15% template:
- BTCUSDT: baseline, both directions.
- ETHUSDT: scalp target, both directions.
- NEARUSDT: scalp target, short-only.

Updated template file:
- `config.brooks_single_account_aggressive_15pct.example.toml`
