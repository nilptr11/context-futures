from __future__ import annotations

from context_futures.backtesting.market_view import BacktestData
from context_futures.config import RiskConfig
from context_futures.domain import BacktestReport, Candle, FundingRate
from context_futures.strategies import TradingStrategy

from .event_loop import BacktestRun, run_event_loop


class Backtester:
    def __init__(self, strategy: TradingStrategy, risk: RiskConfig) -> None:
        self.strategy = strategy
        self.risk = risk

    def run(
        self,
        symbol: str,
        fast_candles: list[Candle],
        slow_candles: list[Candle],
        trade_start_time: int | None = None,
        trade_end_time: int | None = None,
        funding_rates: list[FundingRate] | None = None,
    ) -> BacktestReport:
        data = BacktestData.from_candles(
            symbol=symbol,
            fast_interval=self.strategy.config.fast_interval,
            slow_interval=self.strategy.config.slow_interval,
            fast=fast_candles,
            slow=slow_candles,
            funding=funding_rates,
        )
        return run_backtest(
            strategy=self.strategy,
            risk=self.risk,
            symbol=symbol,
            data=data,
            trade_start_time=trade_start_time,
            trade_end_time=trade_end_time,
        )


def run_backtest(
    *,
    strategy: TradingStrategy,
    risk: RiskConfig,
    symbol: str,
    data: BacktestData | None = None,
    fast_candles: list[Candle] | None = None,
    slow_candles: list[Candle] | None = None,
    trade_start_time: int | None = None,
    trade_end_time: int | None = None,
    funding_rates: list[FundingRate] | None = None,
    strategy_id: str | None = None,
) -> BacktestReport:
    if data is None:
        if fast_candles is None or slow_candles is None:
            raise ValueError("backtest data or fast/slow candles are required")
        data = BacktestData.from_candles(
            symbol=symbol,
            fast_interval=strategy.config.fast_interval,
            slow_interval=strategy.config.slow_interval,
            fast=fast_candles,
            slow=slow_candles,
            funding=funding_rates,
        )
    if len(data.bars(data.fast_interval)) < strategy.required_history() + 2:
        raise ValueError("not enough fast candles")
    if not data.bars(data.slow_interval):
        raise ValueError("slow candles are required for trend filter")

    run_strategy_id = strategy_id or strategy.config.id or strategy.config.name
    result = run_event_loop(
        name=symbol,
        runs=(
            BacktestRun(
                strategy_key=run_strategy_id,
                symbol=symbol,
                strategy=strategy,
                data=data,
            ),
        ),
        risk=risk,
        start_time=trade_start_time,
        end_time=trade_end_time,
    )
    return result.report
