#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import time
from decimal import Decimal

from bn_quant.binance_usdm import BinanceAPIError, BinanceFuturesClient
from bn_quant.config import load_config
from bn_quant.evidence import market_evidence_from_rows
from bn_quant.models import Candle, MarketEvidence
from bn_quant.precision import SymbolRules, decimal_to_exchange_string
from bn_quant.strategy import TrendFilter
from bn_quant.strategy_registry import create_strategy
from bn_quant.trade_plan import signal_stop_price, signal_target_price


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot Binance USD-M REST live/dry-run runner.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--equity", type=float, required=True, help="Risk equity in USDT for sizing.")
    parser.add_argument("--place-orders", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    symbol = args.symbol.upper()
    client = BinanceFuturesClient(base_url=config.binance.base_url, recv_window=config.binance.recv_window)
    strategy = create_strategy(config.strategy)

    fast = latest_klines(client, symbol, config.strategy.fast_interval, 260)
    slow = latest_klines(client, symbol, config.strategy.slow_interval, 260)
    trend = TrendFilter.from_candles(slow, config.strategy.trend_fast_ema, config.strategy.trend_slow_ema)
    atr_values = strategy.atr_values(fast)
    premium = client.premium_index(symbol)
    funding_rate = float(premium.get("lastFundingRate", "0"))
    market_evidence = build_market_evidence(client, symbol, funding_rate, fast[-2])
    signal = strategy.signal_at(fast, len(fast) - 2, trend, atr_values, market_evidence)

    if signal is None:
        print("signal: none")
        return

    if abs(funding_rate) > config.strategy.funding_abs_limit:
        print(f"signal: {signal.side_name}, skipped because funding_rate={funding_rate:.6f}")
        return

    exchange_info = client.exchange_info(symbol)
    rules = SymbolRules.from_exchange_info(exchange_info, symbol)
    reference_price = fast[-1].close
    entry_side = "BUY" if signal.side > 0 else "SELL"
    stop_side = "SELL" if signal.side > 0 else "BUY"
    stop_price_raw = signal_stop_price(reference_price, signal, config.strategy)
    if stop_price_raw is None:
        print(f"signal: {signal.side_name}, skipped because planned stop is invalid")
        return
    target_price_raw = signal_target_price(reference_price, signal, stop_price_raw, config.strategy)
    per_unit_risk = abs(reference_price - stop_price_raw)
    risk_budget = args.equity * config.risk.risk_fraction
    risk_qty = risk_budget / per_unit_risk if per_unit_risk > 0 else 0.0
    cap_qty = (args.equity * config.risk.max_symbol_notional_fraction) / reference_price
    qty = rules.round_quantity(Decimal(str(min(risk_qty, cap_qty))))
    stop_price = rules.round_price_for_side(Decimal(str(stop_price_raw)), stop_side)
    target_price = (
        rules.round_price_for_side(Decimal(str(target_price_raw)), stop_side)
        if target_price_raw is not None
        else None
    )
    notional = Decimal(str(reference_price)) * qty

    print(f"signal: {signal.side_name} ({signal.reason})")
    print(f"reference_price: {reference_price:.4f}")
    print(f"funding_rate: {funding_rate:.6f}")
    if signal.context_score is not None:
        print(f"context_score: {signal.context_score:.3f}")
    if signal.probability_score is not None:
        print(f"probability_score: {signal.probability_score:.3f}")
    if signal.edge_score_r is not None:
        print(f"edge_score_r: {signal.edge_score_r:.3f}")
    if signal.target_room_r is not None:
        print(f"target_room_r: {signal.target_room_r:.3f}")
    if market_evidence.open_interest_change_pct is not None:
        print(f"open_interest_change_pct: {market_evidence.open_interest_change_pct:.4%}")
    if market_evidence.taker_buy_ratio is not None:
        print(f"taker_buy_ratio: {market_evidence.taker_buy_ratio:.2%}")
    print(f"quantity: {decimal_to_exchange_string(qty)}")
    print(f"notional_usdt: {decimal_to_exchange_string(notional)}")
    print(f"initial_stop: {decimal_to_exchange_string(stop_price)}")
    if target_price is not None:
        print(f"planned_target: {decimal_to_exchange_string(target_price)}")
    print(f"leverage_setting: {config.risk.leverage}x")

    if not args.place_orders:
        print("mode: dry-run")
        return
    if os.getenv("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND_RISK":
        raise SystemExit("refusing live order: set CONFIRM_LIVE_TRADING=I_UNDERSTAND_RISK")
    if qty <= 0 or notional < rules.min_notional:
        raise SystemExit(f"refusing live order: qty/notional below exchange minimum ({rules.min_notional})")

    try:
        client.set_margin_type(symbol, config.risk.margin_type)
    except BinanceAPIError as exc:
        if "-4046" not in exc.body:
            raise
    client.set_leverage(symbol, config.risk.leverage)

    client_id = f"bnq_{symbol.lower()}_{int(time.time())}"
    entry = client.new_order(
        symbol=symbol,
        side=entry_side,
        order_type="MARKET",
        quantity=decimal_to_exchange_string(qty),
        new_client_order_id=f"{client_id}_entry",
    )
    print(f"entry_order: {entry}")

    stop = client.new_order(
        symbol=symbol,
        side=stop_side,
        order_type="STOP_MARKET",
        quantity=decimal_to_exchange_string(qty),
        stop_price=decimal_to_exchange_string(stop_price),
        reduce_only=True,
        new_client_order_id=f"{client_id}_stop",
        extra={"workingType": "MARK_PRICE"},
    )
    print(f"stop_order: {stop}")

    if target_price is not None:
        target = client.new_order(
            symbol=symbol,
            side=stop_side,
            order_type="TAKE_PROFIT_MARKET",
            quantity=decimal_to_exchange_string(qty),
            stop_price=decimal_to_exchange_string(target_price),
            reduce_only=True,
            new_client_order_id=f"{client_id}_target",
            extra={"workingType": "MARK_PRICE"},
        )
        print(f"target_order: {target}")


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
        print(f"market_evidence: open_interest unavailable ({type(exc).__name__})")
    try:
        taker_rows = client.taker_buy_sell_volume(symbol=symbol, period="5m", limit=1)
    except Exception as exc:
        print(f"market_evidence: taker_volume unavailable ({type(exc).__name__})")
    return market_evidence_from_rows(
        funding_rate=funding_rate,
        open_interest_rows=open_interest_rows,
        taker_rows=taker_rows,
        fallback_candle=fallback_candle,
    )


if __name__ == "__main__":
    main()
