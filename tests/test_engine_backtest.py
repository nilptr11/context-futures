# ruff: noqa: F403,F405,I001
from .helpers import *

class EngineBacktestTests(unittest.TestCase):
    def test_backtester_runs(self) -> None:
        fast = [make_candle(idx, 100 + idx * 0.2) for idx in range(120)]
        for idx in range(40, 120, 20):
            fast[idx] = make_candle(idx, fast[idx].close + 8.0)
        slow = [make_candle(idx, 100 + idx * 0.5, interval="4h") for idx in range(260)]
        config = make_strategy_config(
            breakout_window=20,
            atr_period=14,
            trend_fast_ema=5,
            trend_slow_ema=20,
            enable_price_action_filters=False,
        )
        risk = RiskConfig(initial_equity=10_000, risk_fraction=0.003, leverage=20)
        result = Backtester(BreakoutAtrStrategy(config), risk).run("BTCUSDT", fast, slow)
        self.assertGreaterEqual(result.final_equity, 0)
        self.assertTrue(result.equity_curve)
        self.assertTrue(result.monthly_returns)


    def test_positive_funding_charges_long_position(self) -> None:
        position = Position(
            symbol="BTCUSDT",
            side=1,
            entry_time=1_000,
            entry_price=100.0,
            quantity=2.0,
            stop_price=90.0,
            entry_fee=0.0,
        )
        funding_idx, delta = apply_funding_until(
            position,
            [FundingRate(symbol="BTCUSDT", funding_time=1_000, funding_rate=0.01, mark_price=100.0)],
            funding_idx=0,
            end_time=2_000,
            fallback_mark_price=100.0,
        )
        self.assertEqual(funding_idx, 1)
        self.assertAlmostEqual(delta, -2.0)
        self.assertAlmostEqual(position.funding, -2.0)

    def test_funding_settlement_waits_until_available(self) -> None:
        position = Position(
            symbol="BTCUSDT",
            side=1,
            entry_time=1_000,
            entry_price=100.0,
            quantity=2.0,
            stop_price=90.0,
            entry_fee=0.0,
        )
        event = FundingRate(
            symbol="BTCUSDT",
            funding_time=1_000,
            funding_rate=0.01,
            mark_price=100.0,
            available_at=3_000,
        )

        funding_idx, delta = apply_funding_until(
            position,
            [event],
            funding_idx=0,
            end_time=2_000,
            fallback_mark_price=100.0,
        )
        self.assertEqual(funding_idx, 0)
        self.assertAlmostEqual(delta, 0.0)

        funding_idx, delta = apply_funding_until(
            position,
            [event],
            funding_idx=0,
            end_time=3_000,
            fallback_mark_price=100.0,
        )
        self.assertEqual(funding_idx, 1)
        self.assertAlmostEqual(delta, -2.0)


    def test_profit_target_hit(self) -> None:
        fill_policy = ConservativeOhlcFillPolicy(RiskConfig(slippage_rate=0.0))
        position = Position(
            symbol="BTCUSDT",
            side=1,
            entry_time=1,
            entry_price=100.0,
            quantity=1.0,
            stop_price=90.0,
            entry_fee=0.0,
            target_price=120.0,
        )
        fill = fill_policy.exit_for_position(
            position,
            Candle(
                symbol="BTCUSDT",
                interval="1h",
                open_time=1,
                open=110.0,
                high=121.0,
                low=109.0,
                close=120.0,
                volume=100.0,
                close_time=2,
            ),
        )
        self.assertIsNotNone(fill)
        self.assertAlmostEqual(fill.exit_price, 120.0)
        self.assertEqual(fill.reason, "profit_target")


    def test_portfolio_risk_caps_new_order(self) -> None:
        state = PortfolioState(
            cash=10_000.0,
            positions={
                "BTCUSDT": Position(
                    strategy_id="test",
                    symbol="BTCUSDT",
                    side=1,
                    entry_time=1,
                    entry_price=100.0,
                    quantity=50.0,
                    stop_price=90.0,
                    entry_fee=0.0,
                    last_signal_close_time=1,
                )
            },
        )
        risk = RiskConfig(
            initial_equity=10_000.0,
            risk_fraction=0.01,
            max_symbol_notional_fraction=1.0,
            max_total_notional_fraction=1.0,
        )
        decision = PortfolioRiskManager(risk).size_order(
            state,
            marks={"BTCUSDT": 100.0},
            symbol="ETHUSDT",
            entry_price=100.0,
            stop_price=99.0,
        )
        self.assertTrue(decision.allowed)
        self.assertAlmostEqual(decision.quantity, 50.0)


    def test_strategy_symbols_requires_configured_symbols(self) -> None:
        from context_futures.backtest.portfolio import strategy_symbols

        config = make_strategy_config(id="missing_symbols", name="brooks")

        with self.assertRaisesRegex(ValueError, "must define symbols"):
            strategy_symbols(config)


    def test_close_paper_position_uses_position_symbol(self) -> None:
        state = PortfolioState(
            cash=10_000.0,
            positions={
                "test:BTCUSDT": Position(
                    strategy_id="test",
                    symbol="BTCUSDT",
                    side=1,
                    entry_time=1,
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=90.0,
                    entry_fee=0.0,
                    last_signal_close_time=1,
                    entry_reason="brooks_decision_trend_h2_pullback_bull",
                    setup_kind="TREND_PULLBACK",
                )
            },
        )
        trade = close_state_position(state, RiskConfig(), "test:BTCUSDT", 2, 110.0, "test_exit")
        self.assertEqual(trade.symbol, "BTCUSDT")
        self.assertEqual(trade.reason, "test_exit")
        self.assertEqual(trade.exit_reason, "test_exit")
        self.assertEqual(trade.entry_reason, "brooks_decision_trend_h2_pullback_bull")
        self.assertEqual(trade.setup_kind, "TREND_PULLBACK")
        self.assertNotIn("test:BTCUSDT", state.positions)
