#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from bn_quant.binance_usdm import BinanceFuturesClient
from bn_quant.config import load_config
from bn_quant.evidence import market_evidence_from_rows
from bn_quant.models import Candle, MarketEvidence
from bn_quant.portfolio import (
    PortfolioRiskManager,
    close_paper_position,
    load_state,
    open_paper_position,
    save_state,
)
from bn_quant.strategy import TrendFilter
from bn_quant.strategy_registry import TradingStrategy, create_strategy, strategy_id
from bn_quant.trade_plan import signal_stop_price, signal_target_price


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent paper runner with portfolio risk controls.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--state", default="state/paper_state.json")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--lookback", type=int, default=320)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    symbols = [symbol.upper() for symbol in args.symbols]
    client = BinanceFuturesClient(base_url=config.binance.base_url, recv_window=config.binance.recv_window)
    state = load_state(args.state, config.risk.initial_equity)
    strategies = [(strategy_id(item, idx), create_strategy(item)) for idx, item in enumerate(config.active_strategies())]
    risk_manager = PortfolioRiskManager(config.risk)

    while True:
        started = int(time.time() * 1000)
        try:
            process_cycle(client, strategies, risk_manager, config.risk, state, symbols, args.lookback, started)
            save_state(args.state, state)
        except Exception as exc:
            print(f"cycle_error: {type(exc).__name__}: {exc}")

        if args.once:
            break
        time.sleep(max(args.poll_seconds, 1.0))


def process_cycle(
    client: BinanceFuturesClient,
    strategies: list[tuple[str, TradingStrategy]],
    risk_manager: PortfolioRiskManager,
    risk,
    state,
    symbols: list[str],
    lookback: int,
    now_ms: int,
) -> None:
    market: dict[tuple[str, str, str], tuple[list[Candle], list[Candle], dict]] = {}
    marks: dict[str, float] = {}

    for _, strategy in strategies:
        for symbol in strategy_symbols(strategy, symbols):
            key = (symbol, strategy.config.fast_interval, strategy.config.slow_interval)
            if key in market:
                continue
            fast = latest_klines(client, symbol, strategy.config.fast_interval, lookback)
            slow = latest_klines(client, symbol, strategy.config.slow_interval, lookback)
            premium = client.premium_index(symbol)
            mark_price = float(premium.get("markPrice") or fast[-1].close)
            market[key] = (fast, slow, premium)
            marks[symbol] = mark_price

    equity = state.equity(marks)
    total_notional = state.total_notional(marks)
    print(
        f"portfolio equity={equity:.2f} cash={state.cash:.2f} "
        f"positions={len(state.positions)} total_notional={total_notional:.2f}"
    )

    for strategy_key, strategy in strategies:
        for symbol in strategy_symbols(strategy, symbols):
            market_key = (symbol, strategy.config.fast_interval, strategy.config.slow_interval)
            process_symbol(
                client,
                state,
                risk,
                risk_manager,
                strategy_key,
                strategy,
                symbol,
                market[market_key],
                marks,
                now_ms,
            )


def process_symbol(
    client: BinanceFuturesClient,
    state,
    risk,
    risk_manager: PortfolioRiskManager,
    strategy_key: str,
    strategy: TradingStrategy,
    symbol: str,
    market_item: tuple[list[Candle], list[Candle], dict],
    marks: dict[str, float],
    now_ms: int,
) -> None:
    fast, slow, premium = market_item
    idx = last_closed_index(fast, now_ms)
    if idx is None:
        print(f"{strategy_key}/{symbol}: no closed candle")
        return
    if idx < strategy.required_history():
        print(f"{strategy_key}/{symbol}: not enough closed candles")
        return

    candle = fast[idx]
    slow_idx = last_closed_index(slow, now_ms)
    if slow_idx is None:
        print(f"{strategy_key}/{symbol}: no closed slow candle")
        return
    slow_closed = slow[: slow_idx + 1]
    seen_key = position_key(strategy_key, symbol)
    last_seen = state.last_processed_close_time.get(seen_key)
    if last_seen is not None and candle.close_time <= last_seen:
        print(f"{strategy_key}/{symbol}: no new closed candle")
        return

    trend_filter = TrendFilter.from_candles(slow_closed, strategy.config.trend_fast_ema, strategy.config.trend_slow_ema)
    atr_values = strategy.atr_values(fast)
    mark_price = marks[symbol]
    state.last_processed_close_time[seen_key] = candle.close_time

    if seen_key in state.positions:
        handle_existing_position(state, risk, strategy, trend_filter, atr_values, fast, idx, seen_key, symbol, mark_price)
        return

    funding_rate = float(premium.get("lastFundingRate") or 0.0)
    market_evidence = build_market_evidence(client, symbol, funding_rate, candle)
    signal = strategy.signal_at(fast, idx, trend_filter, atr_values, market_evidence)
    if signal is None:
        print(f"{strategy_key}/{symbol}: signal none")
        return

    if abs(funding_rate) > strategy.config.funding_abs_limit:
        print(f"{strategy_key}/{symbol}: skip {signal.side_name}, funding_rate={funding_rate:.6f}")
        return

    entry_price = apply_entry_slippage(mark_price, signal.side, risk.slippage_rate)
    stop_price = signal_stop_price(entry_price, signal, strategy.config)
    if stop_price is None:
        print(f"{strategy_key}/{symbol}: skip {signal.side_name}, invalid_planned_stop")
        return
    target_price = signal_target_price(entry_price, signal, stop_price, strategy.config)
    decision = risk_manager.size_order(state, marks, symbol, entry_price, stop_price)
    if not decision.allowed:
        print(f"{strategy_key}/{symbol}: skip {signal.side_name}, risk={decision.reason}")
        return

    position = open_paper_position(
        state,
        risk,
        position_key=seen_key,
        strategy_id=strategy_key,
        symbol=symbol,
        side=signal.side,
        entry_time=now_ms,
        entry_price=entry_price,
        quantity=decision.quantity,
        stop_price=stop_price,
        signal_close_time=candle.close_time,
        target_price=target_price,
        context_score=signal.context_score,
        setup_score=signal.setup_score,
        signal_score=signal.signal_score,
        location_score=signal.location_score,
        target_room_r=signal.target_room_r,
        probability_score=signal.probability_score,
        edge_score_r=signal.edge_score_r,
        funding_crowding_score=signal.funding_crowding_score,
        taker_crowding_score=signal.taker_crowding_score,
        open_interest_crowding_score=signal.open_interest_crowding_score,
        external_crowding_score=signal.external_crowding_score,
    )
    print(
        f"{strategy_key}/{symbol}: OPEN {position.side_name} qty={position.quantity:.8f} "
        f"entry={position.entry_price:.6f} stop={position.stop_price:.6f} target={position.target_price or 0:.6f} "
        f"notional={position.notional(mark_price):.2f} "
        f"context={position.context_score or 0:.3f} prob={position.probability_score or 0:.3f} edge={position.edge_score_r or 0:.3f}"
    )


def handle_existing_position(
    state,
    risk,
    strategy: TradingStrategy,
    trend_filter: TrendFilter,
    atr_values,
    fast: list[Candle],
    idx: int,
    position_key_value: str,
    symbol: str,
    mark_price: float,
) -> None:
    position = state.positions[position_key_value]
    candle = fast[idx]

    stop_hit = (position.side > 0 and candle.low <= position.stop_price) or (
        position.side < 0 and candle.high >= position.stop_price
    )
    if stop_hit:
        exit_price = apply_exit_slippage(position.stop_price, position.side, risk.slippage_rate)
        trade = close_paper_position(state, risk, position_key_value, candle.close_time, exit_price, "stop")
        print(f"{position_key_value}: CLOSE {trade.side} stop exit={exit_price:.6f} pnl={trade.pnl:.2f}")
        return

    target_hit = position.target_price is not None and (
        (position.side > 0 and candle.high >= position.target_price)
        or (position.side < 0 and candle.low <= position.target_price)
    )
    if target_hit:
        exit_price = apply_exit_slippage(position.target_price, position.side, risk.slippage_rate)
        trade = close_paper_position(state, risk, position_key_value, candle.close_time, exit_price, "profit_target")
        print(f"{position_key_value}: CLOSE {trade.side} target exit={exit_price:.6f} pnl={trade.pnl:.2f}")
        return

    current_atr = atr_values[idx]
    if current_atr is not None and current_atr > 0:
        distance = strategy.config.trail_atr_multiple * current_atr
        if position.side > 0:
            position.stop_price = max(position.stop_price, candle.close - distance)
        else:
            position.stop_price = min(position.stop_price, candle.close + distance)

    opposite = strategy.opposite_signal(fast, idx, trend_filter, position.side, atr_values)
    if opposite is not None:
        exit_price = apply_exit_slippage(mark_price, position.side, risk.slippage_rate)
        trade = close_paper_position(state, risk, position_key_value, candle.close_time, exit_price, "opposite_signal")
        print(f"{position_key_value}: CLOSE {trade.side} opposite exit={exit_price:.6f} pnl={trade.pnl:.2f}")
        return

    print(
        f"{position_key_value}: HOLD {position.side_name} entry={position.entry_price:.6f} "
        f"mark={mark_price:.6f} stop={position.stop_price:.6f} target={position.target_price or 0:.6f} "
        f"unpnl={position.unrealized_pnl(mark_price):.2f}"
    )


def latest_klines(client: BinanceFuturesClient, symbol: str, interval: str, limit: int) -> list[Candle]:
    rows = client.klines(symbol=symbol, interval=interval, limit=limit)
    return [
        Candle(
            symbol=symbol,
            interval=interval,
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
            taker_buy_volume=float(row[9]) if len(row) > 9 and row[9] != "" else None,
        )
        for row in rows
    ]


def build_market_evidence(
    client: BinanceFuturesClient,
    symbol: str,
    funding_rate: float,
    fallback_candle: Candle,
) -> MarketEvidence:
    open_interest_rows = None
    taker_rows = None
    try:
        open_interest_rows = client.open_interest_statistics(symbol=symbol, period="5m", limit=2)
    except Exception as exc:
        print(f"{symbol}: market_evidence open_interest unavailable: {type(exc).__name__}")
    try:
        taker_rows = client.taker_buy_sell_volume(symbol=symbol, period="5m", limit=1)
    except Exception as exc:
        print(f"{symbol}: market_evidence taker_volume unavailable: {type(exc).__name__}")
    return market_evidence_from_rows(
        funding_rate=funding_rate,
        open_interest_rows=open_interest_rows,
        taker_rows=taker_rows,
        fallback_candle=fallback_candle,
    )


def last_closed_index(candles: list[Candle], now_ms: int) -> int | None:
    for idx in range(len(candles) - 1, -1, -1):
        if candles[idx].close_time <= now_ms:
            return idx
    return None


def apply_entry_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 + slippage_rate) if side > 0 else price * (1.0 - slippage_rate)


def apply_exit_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 - slippage_rate) if side > 0 else price * (1.0 + slippage_rate)


def position_key(strategy_key: str, symbol: str) -> str:
    return f"{strategy_key}:{symbol}"


def strategy_symbols(strategy: TradingStrategy, fallback_symbols: list[str]) -> list[str]:
    if strategy.config.symbols:
        return [symbol.upper() for symbol in strategy.config.symbols]
    return fallback_symbols


if __name__ == "__main__":
    main()
