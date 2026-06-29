# ruff: noqa: F403,F405,I001
from .helpers import *

class BrooksCandidateTests(unittest.TestCase):
    def test_brooks_context_score_uses_configured_weights(self) -> None:
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
        config = make_strategy_config(
            brooks=make_brooks_config(
                trader_equation=BrooksTraderEquationConfig(
                    context_weights=BrooksContextWeightsConfig(
                        control=1.0,
                        control_gap=0.0,
                        trend_alignment=0.0,
                        anti_range=0.0,
                        breakout_follow_through=0.0,
                        anti_climax=0.0,
                    )
                )
            )
        )

        scoreboard = score_context_for_side_with_evidence(context, 1, config, None)

        self.assertAlmostEqual(scoreboard.context_score, context.always_in_bull_score)


    def test_brooks_candidate_keeps_evidence_ledger(self) -> None:
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
        config = make_strategy_config(profit_target_r_multiple=2.0)
        hypothesis = hypothesis_for_pullback(pullback)
        plan = plan_pullback_trade(pullback, hypothesis, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        plan = require_not_none(plan)
        candidate = pullback_candidate(pullback, hypothesis, context, config, plan)
        equation = candidate.trader_equation
        self.assertIsNotNone(equation)
        assert equation is not None

        self.assertEqual(candidate.evidence.score_for("context_control"), 0.85)
        self.assertIsNotNone(candidate.evidence.score_for("setup_quality"))
        self.assertIsNotNone(candidate.evidence.score_for("signal_bar"))
        self.assertIsNotNone(candidate.evidence.score_for("entry_location"))
        self.assertIsNotNone(candidate.evidence.score_for("target_room"))
        self.assertAlmostEqual(equation.probability_evidence.weighted_score(), candidate.probability_score)
        self.assertIn(EvidenceCategory.TRADER_EQUATION, {item.category for item in candidate.evidence.items})
        diagnostics = diagnostics_from_candidate(candidate)
        self.assertEqual(diagnostics.pullback_depth_score, 0.50)
        self.assertEqual(diagnostics.pullback_leg_score, 0.50)
        self.assertEqual(diagnostics.pullback_double_test_score, 0.70)
        self.assertEqual(diagnostics.pullback_wedge_score, 0.0)

    def test_brooks_probability_score_uses_configured_family_weights(self) -> None:
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
                trader_equation=BrooksTraderEquationConfig(
                    probability_weights=BrooksProbabilityWeightsConfig(
                        trend_continuation=BrooksTrendContinuationProbabilityWeightsConfig(
                            base=0.0,
                            context=1.0,
                            setup=0.0,
                            signal=0.0,
                            location=0.0,
                        ),
                    ),
                ),
            ),
        )
        hypothesis = hypothesis_for_pullback(pullback)
        plan = require_not_none(
            plan_pullback_trade(pullback, hypothesis, reference_price=104.0, current_atr=3.0, config=config)
        )
        candidate = pullback_candidate(pullback, hypothesis, context, config, plan)
        equation = require_not_none(candidate.trader_equation)

        self.assertAlmostEqual(candidate.probability_score, candidate.context.context_score)
        self.assertEqual(equation.probability_evidence.score_for("probability_base"), 0.0)

    def test_brooks_setup_score_uses_configured_family_weights(self) -> None:
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
                trader_equation=BrooksTraderEquationConfig(
                    setup_score_weights=BrooksSetupScoreWeightsConfig(
                        trend_pullback=BrooksTrendPullbackScoreWeightsConfig(
                            setup_depth=0.0,
                            setup_legs=0.0,
                            setup_ema=1.0,
                            setup_structure=0.0,
                            location_setup=1.0,
                            location_anti_range=0.0,
                        ),
                    ),
                ),
            ),
        )
        hypothesis = hypothesis_for_pullback(pullback)
        plan = require_not_none(
            plan_pullback_trade(pullback, hypothesis, reference_price=104.0, current_atr=3.0, config=config)
        )
        candidate = pullback_candidate(pullback, hypothesis, context, config, plan)

        self.assertEqual(candidate.setup_score, 1.0)
        self.assertEqual(candidate.location_score, 1.0)
        self.assertEqual(candidate.evidence.score_for("setup_quality"), 1.0)
        self.assertEqual(candidate.evidence.score_for("entry_location"), 1.0)


    def test_brooks_candidate_keeps_market_structure_evidence(self) -> None:
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
            range_low=96.0,
            range_high=112.0,
            range_midpoint=104.0,
            range_position=0.50,
            cycle=MarketCycle.TREND,
        )
        candles = [
            make_ohlc(0, 100, 106, 96, 103, interval="1h"),
            make_ohlc(1, 103, 109, 99, 104, interval="1h"),
        ]
        pullback = make_pullback_signal()
        config = make_strategy_config(profit_target_r_multiple=2.0)
        structure = read_market_structure(candles, idx=1, current_atr=3.0, context=context, config=config)
        hypothesis = hypothesis_for_pullback(pullback)
        plan = plan_pullback_trade(pullback, hypothesis, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        assert plan is not None
        baseline_candidate = pullback_candidate(pullback, hypothesis, context, config, plan)
        candidate = pullback_candidate(pullback, hypothesis, context, config, plan, structure=structure)

        self.assertIs(candidate.structure, structure)
        self.assertIsNotNone(candidate.evidence.score_for("structure_magnet_target"))
        self.assertIsNotNone(candidate.evidence.score_for("structure_two_sided_transition"))
        self.assertIsNone(candidate.evidence.score_for("probability_structure_magnet_target"))
        self.assertEqual(candidate.probability_score, baseline_candidate.probability_score)
        self.assertIsNotNone(candidate.trader_equation)
        assert candidate.trader_equation is not None
        self.assertIsNone(candidate.trader_equation.probability_evidence.score_for("probability_structure_magnet_target"))


    def test_brooks_failed_breakout_candidate_keeps_trapped_trader_evidence(self) -> None:
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=0,
            range_score=0.90,
            trend_score=0.20,
            breakout_score=0.0,
            always_in_bull_score=0.45,
            always_in_bear_score=0.45,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.20,
            cycle=MarketCycle.TRADING_RANGE,
        )
        candles = [
            make_ohlc(0, 100, 103, 95, 100, interval="1h"),
            make_ohlc(1, 99, 102, 94, 98, interval="1h"),
        ]
        setup = FailedBreakoutSignal(
            side=1,
            variant=PatternVariant.FAILED_BREAKOUT,
            reason="failed_breakout_bull",
            signal_bar_score=0.80,
            setup_low=94.0,
            setup_high=103.0,
            range_low=95.0,
            range_high=105.0,
            trap_score=0.90,
            range_quality_score=0.80,
        )
        config = make_strategy_config(
            profit_target_r_multiple=2.0,
            brooks=make_brooks_config(
                trader_equation=BrooksTraderEquationConfig(min_target_room_r=0.0),
                failed_breakout=BrooksFailedBreakoutConfig(
                    min_probability_score=0.0,
                    min_edge_score_r=-2.0,
                ),
            ),
        )
        structure = read_market_structure(candles, idx=1, current_atr=3.0, context=context, config=config)
        hypothesis = hypothesis_for_setup(setup, SetupKind.FAILED_BREAKOUT)
        plan = plan_setup_trade(
            setup,
            hypothesis,
            reference_price=98.0,
            current_atr=3.0,
            config=config,
        )
        self.assertIsNotNone(plan)
        candidate = setup_candidate(
            setup,
            SetupKind.FAILED_BREAKOUT,
            hypothesis,
            context,
            config,
            plan=plan,
            structure=structure,
        )

        self.assertEqual(candidate.hypothesis.family, SetupFamily.RANGE_FADE)
        self.assertEqual(candidate.hypothesis.variant, PatternVariant.FAILED_BREAKOUT)
        self.assertEqual(candidate.evidence.score_for("failed_breakout_trap"), 0.90)
        self.assertEqual(candidate.evidence.score_for("failed_breakout_range_quality"), 0.80)
        self.assertIsNone(candidate.evidence.score_for("probability_failed_breakout_trap"))
        self.assertIsNotNone(candidate.trader_equation)
        assert candidate.trader_equation is not None
        self.assertIsNone(candidate.trader_equation.probability_evidence.score_for("probability_failed_breakout_trap"))
        self.assertIn(EvidenceCategory.TRAPPED_TRADERS, {item.category for item in candidate.evidence.items})
