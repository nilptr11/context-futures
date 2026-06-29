# ruff: noqa: F403,F405,I001
from .helpers import *

class BrooksContextTests(unittest.TestCase):
    def test_brooks_market_read_allows_channel_trend_pullback(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.CHANNEL_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.80,
            breakout_score=0.10,
            always_in_bull_score=0.82,
            always_in_bear_score=0.18,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.30,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.75,
            fast_ema=101.0,
            slow_ema=99.0,
        )
        config = make_strategy_config(
            brooks=make_brooks_config(
                regime=BrooksRegimeConfig(always_in_threshold=0.70, range_score_max=0.55),
                trend_pullback=BrooksTrendPullbackConfig(enabled=True),
                breakout_pullback=BrooksBreakoutPullbackConfig(enabled=False),
                failed_breakout=BrooksFailedBreakoutConfig(enabled=False),
            ),
        )

        market_read = read_market(regime, trend=1, config=config)

        self.assertEqual(market_read.context.cycle, MarketCycle.CHANNEL)
        self.assertEqual(market_read.context.overlay, MarketOverlay.NONE)
        self.assertEqual(market_read.context.state, ContextState.BULL_CHANNEL)
        self.assertEqual(market_read.context.raw_regime, MarketRegime.CHANNEL_UP)
        self.assertEqual(market_read.primary_side, 1)
        self.assertEqual(market_read.candidate_kinds, (SetupKind.TREND_PULLBACK,))


    def test_brooks_climax_is_overlay_not_market_cycle(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.CLIMAX_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.86,
            always_in_bear_score=0.14,
            climax_score=0.90,
            climax_side=1,
            two_sided_score=0.20,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.95,
            fast_ema=107.0,
            slow_ema=100.0,
        )

        market_read = read_market(regime, trend=1, config=make_strategy_config())

        self.assertEqual(market_read.context.cycle, MarketCycle.TREND)
        self.assertEqual(market_read.context.overlay, MarketOverlay.CLIMAX)
        self.assertEqual(market_read.context.state, ContextState.BULL_CLIMAX)
        self.assertEqual(market_read.context.raw_regime, MarketRegime.CLIMAX_UP)
        self.assertEqual(market_read.candidate_kinds, ())


    def test_bear_breakout_uses_stricter_trade_equation(self) -> None:
        config = make_strategy_config(
            brooks=make_brooks_config(
                trader_equation=BrooksTraderEquationConfig(
                    min_probability_score=0.52,
                    min_edge_score_r=0.0,
                ),
                breakout_pullback=BrooksBreakoutPullbackConfig(
                    bear_min_probability_score=0.58,
                    bear_min_edge_score_r=0.35,
                ),
            ),
        )
        candidate = TradeCandidate(
            kind=SetupKind.BREAKOUT_PULLBACK,
            side=-1,
            reason="breakout_pullback_bear",
            plan=None,
            context=ContextScoreboard(
                side=-1,
                control_score=0.80,
                control_gap=0.80,
                trend_alignment_score=1.0,
                anti_range_score=0.80,
                breakout_follow_through_score=0.80,
                anti_climax_score=0.90,
                funding_crowding_score=0.0,
                taker_crowding_score=0.0,
                open_interest_crowding_score=0.0,
                external_crowding_score=0.0,
                range_edge_score=0.0,
                context_score=0.80,
            ),
            setup_score=0.80,
            signal_score=0.80,
            location_score=0.80,
            target_room_r=2.0,
            probability_score=0.57,
            edge_score_r=0.30,
        )
        decision = evaluate_candidate(candidate, config)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "probability_score")


    def test_brooks_range_defaults_to_no_trend_pullback(self) -> None:
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=1,
            range_score=0.90,
            trend_score=0.30,
            breakout_score=0.0,
            always_in_bull_score=0.80,
            always_in_bear_score=0.20,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
        )
        config = make_strategy_config(
            brooks=make_brooks_config(
                regime=BrooksRegimeConfig(range_score_max=0.55),
                trend_pullback=BrooksTrendPullbackConfig(enabled=True),
                breakout_pullback=BrooksBreakoutPullbackConfig(enabled=False),
                failed_breakout=BrooksFailedBreakoutConfig(enabled=False),
            ),
        )
        self.assertEqual(candidate_kinds_for_context(context, config), ())

        failed_breakout_config = make_strategy_config(
            brooks=make_brooks_config(
                regime=BrooksRegimeConfig(range_score_max=0.55),
                trend_pullback=BrooksTrendPullbackConfig(enabled=True),
                breakout_pullback=BrooksBreakoutPullbackConfig(enabled=False),
                failed_breakout=BrooksFailedBreakoutConfig(enabled=True, min_range_score=0.60),
            ),
        )
        self.assertEqual(
            candidate_kinds_for_context(context, failed_breakout_config),
            (SetupKind.FAILED_BREAKOUT,),
        )


    def test_market_evidence_parses_taker_and_oi_rows(self) -> None:
        evidence = market_evidence_from_rows(
            funding_rate=0.0001,
            open_interest_rows=[
                {"sumOpenInterest": "100.0", "timestamp": 1},
                {"sumOpenInterest": "103.0", "timestamp": 2},
            ],
            taker_rows=[{"buyVol": "60.0", "sellVol": "40.0", "timestamp": 2}],
        )
        self.assertAlmostEqual(evidence.open_interest_change_pct, 0.03)
        self.assertAlmostEqual(evidence.taker_buy_ratio, 0.60)

        candle = Candle(
            symbol="BTCUSDT",
            interval="1h",
            open_time=0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=100.0,
            close_time=1,
            taker_buy_volume=65.0,
        )
        self.assertAlmostEqual(taker_buy_ratio_from_candle(candle), 0.65)


    def test_extreme_taker_and_oi_can_reject_crowded_trend_entry(self) -> None:
        context = MarketContext(
            state=ContextState.BULL_TREND,
            direction=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.85,
            always_in_bear_score=0.15,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
        )
        pullback = make_pullback_signal()
        config = make_strategy_config(
            profit_target_r_multiple=2.0,
            brooks=make_brooks_config(
                trader_equation=BrooksTraderEquationConfig(min_context_score=0.77),
                evidence=BrooksEvidenceConfig(
                    external_crowding_context_penalty=0.30,
                    external_crowding_probability_penalty=0.20,
                ),
            ),
        )
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        neutral = evaluate_candidate(pullback_candidate(pullback, context, config, plan), config)
        crowded = evaluate_candidate(
            pullback_candidate(
                pullback,
                context,
                config,
                plan,
                MarketEvidence(taker_buy_ratio=0.85, open_interest_change_pct=0.05),
            ),
            config,
        )
        self.assertTrue(neutral.accepted)
        self.assertFalse(crowded.accepted)
        self.assertEqual(crowded.reason, "context_score")

