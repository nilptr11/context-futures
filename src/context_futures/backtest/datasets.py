from __future__ import annotations

from context_futures.data import ParquetMarketDataStore

from .market_view import BacktestData


def load_backtest_data(
    store: ParquetMarketDataStore,
    *,
    symbol: str,
    fast_interval: str,
    slow_interval: str,
) -> BacktestData:
    fast = store.load_klines(symbol, fast_interval)
    slow = fast if fast_interval == slow_interval else store.load_klines(symbol, slow_interval)
    funding = store.load_funding(symbol)
    return BacktestData.from_candles(
        symbol=symbol.upper(),
        fast_interval=fast_interval,
        slow_interval=slow_interval,
        fast=fast,
        slow=slow,
        funding=funding,
    )
