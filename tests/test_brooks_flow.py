# ruff: noqa: F403,F405,I001
from .helpers import *

class BrooksFlowTests(unittest.TestCase):
    def test_brooks_decision_journal_can_probe_disabled_breakout_setup(self) -> None:
        candles = [make_ohlc(idx, 100 + idx, 103 + idx, 99 + idx, 102 + idx, interval="1h") for idx in range(12)]
        idx = len(candles) - 2
        strategy = create_strategy(
            make_strategy_config(
                name="brooks_price_action",
                fast_interval="1h",
                slow_interval="4h",
                atr_period=3,
                trend_fast_ema=3,
                trend_slow_ema=8,
                brooks_always_in_threshold=0.35,
                brooks_range_score_max=0.95,
                brooks_pullback_entry_ema=3,
                brooks_pullback_lookback=3,
                brooks_enable_trend_pullback=False,
                brooks_enable_breakout_pullback=False,
                brooks_enable_failed_breakout=False,
            )
        )
        slow = [make_ohlc(i, 100 + i, 102 + i, 99 + i, 101 + i) for i in range(20)]
        view = make_market_view(strategy, candles, slow, idx=idx, strategy_id="brooks_pa_btc_1h")

        default_records = strategy.decision_records_on_bar_close(view)  # type: ignore[attr-defined]
        probe_records = strategy.decision_records_on_bar_close(  # type: ignore[attr-defined]
            view,
            include_research_setups=True,
        )

        self.assertEqual(default_records[0].decision_reason, "no_candidate_kind")
        disabled = next(item for item in probe_records if item.setup_kind)
        self.assertFalse(disabled.setup_enabled)
        self.assertFalse(disabled.accepted)
        self.assertIn(disabled.setup_kind, {"TREND_PULLBACK", "BREAKOUT_PULLBACK", "FAILED_BREAKOUT"})


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
            fast_interval="1h",
            slow_interval="4h",
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
        fast = candles + [make_ohlc(14, 111, 113, 110, 112, interval="1h")]
        signal = strategy.on_bar_close(make_market_view(strategy, fast, slow, idx=len(candles) - 1))
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
            fast_interval="1h",
            slow_interval="4h",
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
        idx = 13
        original_signal = strategy.on_bar_close(
            make_market_view(strategy, candles, slow, idx=idx)
        )
        mutated_signal = strategy.on_bar_close(
            make_market_view(strategy, mutated, slow, idx=idx)
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
            fast_interval="1h",
            slow_interval="4h",
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
        fast = candles + [make_ohlc(12, 99.5, 101, 98, 100.5, interval="1h")]
        signal = strategy.on_bar_close(
            make_market_view(strategy, fast, slow, idx=len(candles) - 1)
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
