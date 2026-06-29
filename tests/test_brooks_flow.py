# ruff: noqa: F403,F405,I001
from .helpers import *

class BrooksFlowTests(unittest.TestCase):
    def test_brooks_decision_journal_can_probe_disabled_breakout_setup(self) -> None:
        candles = [make_ohlc(idx, 100 + idx, 103 + idx, 99 + idx, 102 + idx, interval="1h") for idx in range(12)]
        idx = len(candles) - 2
        regime = MarketRegimePoint(
            close_time=candles[idx].close_time,
            regime=MarketRegime.BREAKOUT_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.82,
            breakout_score=0.80,
            always_in_bull_score=0.82,
            always_in_bear_score=0.12,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.85,
            fast_ema=105.0,
            slow_ema=100.0,
        )
        trend = TrendFilter([TrendPoint(candles[idx].close_time, 1, 105.0, 100.0)])
        regime_filter = BrooksRegimeFilter([regime])
        strategy = create_strategy(
            make_strategy_config(
                name="brooks_price_action",
                atr_period=3,
                brooks_pullback_entry_ema=3,
                brooks_pullback_lookback=3,
                brooks_enable_trend_pullback=False,
                brooks_enable_breakout_pullback=False,
                brooks_enable_failed_breakout=False,
            )
        )

        default_records = strategy.decision_records_at(  # type: ignore[attr-defined]
            "BTCUSDT",
            "brooks_pa_btc_1h",
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
            regime_filter=regime_filter,
        )
        probe_records = strategy.decision_records_at(  # type: ignore[attr-defined]
            "BTCUSDT",
            "brooks_pa_btc_1h",
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
            regime_filter=regime_filter,
            include_research_setups=True,
        )

        self.assertEqual(default_records[0].decision_reason, "no_candidate_kind")
        breakout = next(item for item in probe_records if item.setup_kind == "BREAKOUT_PULLBACK")
        self.assertFalse(breakout.setup_enabled)
        self.assertFalse(breakout.accepted)
        self.assertIn(breakout.decision_reason, {"no_breakout_pullback_setup", "breakout_context_filter"})
        self.assertEqual(breakout.diagnostics.market_cycle, "BREAKOUT")


    def test_brooks_price_action_routes_trend_pullback(self) -> None:
        self.assertIn("brooks_price_action", available_strategies())
        candles = [
            make_ohlc(0, 100, 102, 99, 101, interval="1h"),
            make_ohlc(1, 101, 103, 100, 102, interval="1h"),
            make_ohlc(2, 102, 104, 101, 103, interval="1h"),
            make_ohlc(3, 103, 105, 102, 104, interval="1h"),
            make_ohlc(4, 104, 106, 103, 105, interval="1h"),
            make_ohlc(5, 105, 107, 104, 106, interval="1h"),
            make_ohlc(6, 106, 108, 105, 107, interval="1h"),
            make_ohlc(7, 107, 109, 106, 108, interval="1h"),
            make_ohlc(8, 108, 110, 107, 109, interval="1h"),
            make_ohlc(9, 109, 113, 108, 112, interval="1h"),
            make_ohlc(10, 112, 113, 109, 110, interval="1h"),
            make_ohlc(11, 110, 111, 107, 108, interval="1h"),
            make_ohlc(12, 108, 110, 106, 107, interval="1h"),
            make_ohlc(13, 107, 112, 106, 111, interval="1h"),
        ]
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(40)]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            trend_fast_ema=3,
            trend_slow_ema=8,
            brooks_always_in_threshold=0.45,
            brooks_range_score_max=0.90,
            brooks_climax_score_max=0.99,
            brooks_pullback_entry_ema=3,
            brooks_pullback_lookback=6,
            brooks_pullback_min_depth_atr=0.5,
            brooks_pullback_max_depth_atr=5.0,
            brooks_pullback_ema_touch_atr=10.0,
            brooks_pullback_min_legs=2,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        regime_filter = BrooksRegimeFilter.from_candles(slow, 3, 8, config.trend.regime_atr_period)
        signal = strategy.signal_at(
            candles,
            len(candles) - 1,
            trend,
            strategy.atr_values(candles),
            regime_filter=regime_filter,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_decision_trend_h2_pullback_bull")
        self.assertEqual(signal.setup_kind, "TREND_PULLBACK")
        self.assertIsNotNone(signal.stop_price)
        self.assertIsNotNone(signal.target_price)
        self.assertLess(signal.stop_price, candles[-1].close)
        self.assertGreater(signal.target_price, candles[-1].close)
        self.assertIsNotNone(signal.diagnostics.context_score)
        self.assertIsNotNone(signal.diagnostics.market_cycle)
        self.assertIsNotNone(signal.diagnostics.market_overlay)
        self.assertIsNotNone(signal.diagnostics.context_state)
        self.assertIsNotNone(signal.diagnostics.raw_regime)
        self.assertEqual(signal.diagnostics.context_direction, 1)
        self.assertIsNotNone(signal.diagnostics.control_gap)
        self.assertIsNotNone(signal.diagnostics.breakout_follow_through_score)
        self.assertIsNotNone(signal.diagnostics.target_model)
        self.assertIsNotNone(signal.diagnostics.trader_equation_cost_r)
        self.assertIsNotNone(signal.diagnostics.stop_distance_atr)
        self.assertIsNotNone(signal.diagnostics.setup_score)
        self.assertIsNotNone(signal.diagnostics.probability_score)
        self.assertIsNotNone(signal.diagnostics.edge_score_r)
        self.assertGreater(signal.diagnostics.context_score, 0.0)
        self.assertGreater(signal.diagnostics.probability_score, 0.0)


    def test_brooks_price_action_signal_has_no_future_candle_dependency(self) -> None:
        candles = [
            make_ohlc(0, 100, 102, 99, 101, interval="1h"),
            make_ohlc(1, 101, 103, 100, 102, interval="1h"),
            make_ohlc(2, 102, 104, 101, 103, interval="1h"),
            make_ohlc(3, 103, 105, 102, 104, interval="1h"),
            make_ohlc(4, 104, 106, 103, 105, interval="1h"),
            make_ohlc(5, 105, 107, 104, 106, interval="1h"),
            make_ohlc(6, 106, 108, 105, 107, interval="1h"),
            make_ohlc(7, 107, 109, 106, 108, interval="1h"),
            make_ohlc(8, 108, 110, 107, 109, interval="1h"),
            make_ohlc(9, 109, 113, 108, 112, interval="1h"),
            make_ohlc(10, 112, 113, 109, 110, interval="1h"),
            make_ohlc(11, 110, 111, 107, 108, interval="1h"),
            make_ohlc(12, 108, 110, 106, 107, interval="1h"),
            make_ohlc(13, 107, 112, 106, 111, interval="1h"),
            make_ohlc(14, 500, 520, 490, 510, interval="1h"),
        ]
        mutated = list(candles)
        mutated[14] = make_ohlc(14, 1, 2, 0.5, 1.5, interval="1h")
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(40)]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            trend_fast_ema=3,
            trend_slow_ema=8,
            brooks_always_in_threshold=0.45,
            brooks_range_score_max=0.90,
            brooks_climax_score_max=0.99,
            brooks_pullback_entry_ema=3,
            brooks_pullback_lookback=6,
            brooks_pullback_min_depth_atr=0.5,
            brooks_pullback_max_depth_atr=5.0,
            brooks_pullback_ema_touch_atr=10.0,
            brooks_pullback_min_legs=2,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        regime_filter = BrooksRegimeFilter.from_candles(slow, 3, 8, config.trend.regime_atr_period)
        idx = 13
        original_signal = strategy.signal_at(
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
            regime_filter=regime_filter,
        )
        mutated_signal = strategy.signal_at(
            mutated,
            idx,
            trend,
            strategy.atr_values(mutated),
            regime_filter=regime_filter,
        )
        self.assertIsNotNone(original_signal)
        self.assertIsNotNone(mutated_signal)
        self.assertEqual(original_signal.side, mutated_signal.side)
        self.assertEqual(original_signal.reason, mutated_signal.reason)
        self.assertAlmostEqual(original_signal.atr, mutated_signal.atr)
        self.assertAlmostEqual(original_signal.stop_price, mutated_signal.stop_price)
        self.assertAlmostEqual(original_signal.target_price, mutated_signal.target_price)


    def test_brooks_price_action_detects_failed_breakout_candidate(self) -> None:
        candles = [
            make_ohlc(0, 100, 103, 97, 101, interval="1h"),
            make_ohlc(1, 101, 103, 97, 99, interval="1h"),
            make_ohlc(2, 99, 103, 97, 101, interval="1h"),
            make_ohlc(3, 101, 103, 97, 99, interval="1h"),
            make_ohlc(4, 99, 103, 97, 101, interval="1h"),
            make_ohlc(5, 101, 103, 97, 99, interval="1h"),
            make_ohlc(6, 99, 103, 97, 101, interval="1h"),
            make_ohlc(7, 101, 103, 97, 99, interval="1h"),
            make_ohlc(8, 99, 103, 97, 101, interval="1h"),
            make_ohlc(9, 99, 100, 94.5, 96, interval="1h"),
            make_ohlc(10, 96, 101, 96, 98.5, interval="1h"),
            make_ohlc(11, 96.8, 102, 96.7, 99.5, interval="1h"),
        ]
        slow = [
            make_ohlc(idx, 100, 103, 97, 101 if idx % 2 else 99)
            for idx in range(30)
        ]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_trend_pullback=False,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=True,
            brooks_failed_breakout_lookback=5,
            brooks_failed_breakout_max_bars=3,
            brooks_failed_breakout_min_range_score=0.0,
            brooks_breakout_buffer_atr=0.05,
            brooks_decision_min_context_score=0.0,
            brooks_decision_min_setup_score=0.0,
            brooks_decision_min_probability_score=0.0,
            brooks_decision_min_target_room_r=0.0,
            brooks_decision_min_edge_score_r=-2.0,
            brooks_failed_breakout_min_probability_score=0.0,
            brooks_failed_breakout_min_edge_score_r=-2.0,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        regime_filter = BrooksRegimeFilter.from_candles(slow, 3, 8, config.trend.regime_atr_period)
        signal = strategy.signal_at(
            candles,
            len(candles) - 1,
            trend,
            strategy.atr_values(candles),
            regime_filter=regime_filter,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_decision_failed_breakout_bull")
        self.assertIsNotNone(signal.stop_price)
        self.assertLess(signal.stop_price, 94.5)
        self.assertIsNotNone(signal.diagnostics.setup_score)
        self.assertGreater(signal.diagnostics.setup_score, 0.0)


    def test_failed_breakout_requires_trapped_trader_evidence(self) -> None:
        candles = [
            make_ohlc(0, 100, 103, 97, 101, interval="1h"),
            make_ohlc(1, 101, 103, 97, 99, interval="1h"),
            make_ohlc(2, 99, 103, 97, 101, interval="1h"),
            make_ohlc(3, 101, 103, 97, 99, interval="1h"),
            make_ohlc(4, 99, 103, 97, 101, interval="1h"),
            make_ohlc(5, 101, 103, 97, 99, interval="1h"),
            make_ohlc(6, 99, 100, 95.8, 96.7, interval="1h"),
            make_ohlc(7, 96.7, 98.0, 96.5, 97.1, interval="1h"),
        ]
        config = make_strategy_config(
            atr_period=3,
            brooks_pullback_min_signal_score=0.0,
            brooks_failed_breakout_lookback=5,
            brooks_failed_breakout_max_bars=3,
            brooks_failed_breakout_min_trap_score=0.80,
            brooks_breakout_buffer_atr=0.05,
        )
        strategy = create_strategy(make_strategy_config(name="brooks_price_action", atr_period=3))
        setup = detect_failed_breakout(candles, len(candles) - 1, strategy.atr_values(candles), config, side=1)
        self.assertIsNone(setup)


if __name__ == "__main__":
    unittest.main()

