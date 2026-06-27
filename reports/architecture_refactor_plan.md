# Architecture Refactor Plan

Date: 2026-06-27

## Goal

Make the codebase easier to extend with new strategies and strategy variants without forcing every strategy to share Brooks-specific code paths.

Compatibility with old import paths is intentionally not preserved.

## Current Target Shape

```text
src/bn_quant/
  models.py
  config.py

  strategies/
    base.py
    breakout_atr.py
    brooks/
      __init__.py
      context.py
      pullback.py
      setups.py
      strategy.py
      trade_plan.py

  execution/
    filters.py

  backtest.py
  portfolio.py
  trade_plan.py
```

## Boundaries

### `strategies/`

Strategy modules generate `Signal` objects. They should not size positions, mutate account state, place orders, or decide whether a symbol/account is allowed to open a trade.

Current files:
- `strategies/base.py`: `TradingStrategy`, `TrendFilter`, `TrendPoint`
- `strategies/breakout_atr.py`: non-Brooks baseline strategy
- `strategies/brooks/strategy.py`: Brooks pullback, breakout, and price-action strategy orchestration
- `strategies/brooks/context.py`: Brooks market context, candidate routing, and trader's equation scoring
- `strategies/brooks/pullback.py`: H/L pullback and wedge/double-test pullback detection
- `strategies/brooks/setups.py`: breakout-pullback and failed-breakout setup detection
- `strategies/brooks/trade_plan.py`: Brooks structural stop and target planning

### `execution/`

Execution modules decide whether a signal can become a position and how orders are constrained.

Current file:
- `execution/filters.py`: entry-side filter via `allow_long` / `allow_short`

Future candidates:
- `execution/sizing.py`
- `execution/exits.py`
- `execution/funding.py`
- `execution/orders.py`

### `backtest.py`

Backtest remains the historical execution engine. It should consume a `TradingStrategy`, apply execution filters, open/close positions, and return reports.

It should not contain strategy pattern logic.

### `portfolio.py`

Portfolio state and portfolio risk sizing live here. This is used by paper/multi-position runners.

Single-symbol backtest currently has its own sizing logic; this should be unified later.

### `models.py`

`StrategyConfig` now owns only identity, symbol, and timeframe fields directly. Strategy parameters are grouped by concern:

- `breakout`: breakout window and ATR period
- `trade`: stop, trailing stop, and profit target parameters
- `trend`: EMA trend filter parameters
- `execution`: funding and side filters
- `price_action`: generic price-action filters
- `brooks`: Brooks-specific setup and decision thresholds

The config loader accepts both nested TOML sections and current flat keys, which keeps research configs readable while preserving existing experiment files during the refactor.

## Known Remaining Debt

1. Execution logic is still duplicated across:
   - `backtest.py`
   - `scripts/paper_runner.py`
   - `scripts/live_rest_runner.py`
   - `scripts/portfolio_backtest.py`

2. Research scripts are useful but fragmented. A unified experiment runner should eventually replace one-off sweep scripts.

3. Group dataclass field names still keep their old prefixes, such as `config.brooks.brooks_*`. This is acceptable during the structural refactor, but the field names should eventually be shortened once all configs are nested.

## Recommended Next Refactor

1. Extract a shared execution engine for:
   - signal -> entry plan
   - entry filters
   - position sizing
   - stop/target/opposite-signal exits

2. Consolidate research scripts around a single experiment spec.

3. Rename nested config fields to drop redundant prefixes after configs are migrated to nested TOML.
