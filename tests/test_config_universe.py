# ruff: noqa: F403,F405,I001
import tomllib

from .helpers import *

class ConfigUniverseTests(unittest.TestCase):
    def test_universe_brooks_profile_scales_periods_by_timeframe_duration(self) -> None:
        base = make_strategy_config(
            id="brooks_pa_btc_1h",
            name="brooks",
            symbols=("BTCUSDT",),
            fast_interval="1h",
            slow_interval="4h",
            atr_period=14,
            trend_fast_ema=50,
            trend_slow_ema=200,
            brooks=make_brooks_config(
                trend_pullback=BrooksTrendPullbackConfig(enabled=True, entry_ema=20, lookback=12),
                breakout_pullback=BrooksBreakoutPullbackConfig(enabled=True),
            ),
        )

        config = build_universe_strategy_config(
            profile=UniverseProfile(
                name="brooks_trend_continuation_baseline",
                template_config_path=Path("configs/strategies/brooks/trend_continuation_portfolio.toml"),
                enabled_setups=(SetupKind.TREND_PULLBACK,),
            ),
            base=base,
            symbol="ETHUSDT",
            fast_interval="30m",
            slow_interval="1h",
        )

        self.assertEqual(config.symbols, ("ETHUSDT",))
        self.assertEqual(config.market.atr_period, 28)
        self.assertEqual(config.brooks.structure.range_lookback, 80)
        self.assertEqual(config.brooks.setups.trend_pullback.entry_ema, 40)
        self.assertEqual(config.brooks.setups.trend_pullback.lookback, 24)
        self.assertEqual(config.trend.fast_ema, 200)
        self.assertEqual(config.trend.slow_ema, 800)
        self.assertTrue(config.brooks.setups.trend_pullback.enabled)
        self.assertFalse(config.brooks.setups.breakout_pullback.enabled)


    def test_universe_profile_loads_from_config_file(self) -> None:
        profile = load_universe_profile("brooks_breakout_research")

        self.assertEqual(profile.name, "brooks_breakout_research")
        self.assertEqual(
            profile.template_config_path,
            Path("configs/strategies/brooks/breakout_pullback_research.toml"),
        )
        self.assertEqual(profile.enabled_setups, (SetupKind.TREND_PULLBACK, SetupKind.BREAKOUT_PULLBACK))

    def test_brooks_family_baseline_profiles_load(self) -> None:
        expected = {
            "brooks_trend_continuation_baseline": (SetupKind.TREND_PULLBACK,),
            "brooks_breakout_continuation_baseline": (SetupKind.BREAKOUT_PULLBACK,),
            "brooks_range_fade_baseline": (SetupKind.FAILED_BREAKOUT,),
        }

        for profile_name, enabled_setups in expected.items():
            with self.subTest(profile=profile_name):
                profile = load_universe_profile(profile_name)

                self.assertEqual(profile.name, profile_name)
                self.assertEqual(profile.enabled_setups, enabled_setups)

    def test_brooks_family_baseline_profile_enables_only_selected_setup(self) -> None:
        base = make_strategy_config(
            id="brooks_pa_btc_1h",
            name="brooks",
            symbols=("BTCUSDT",),
            fast_interval="1h",
            slow_interval="4h",
            brooks=make_brooks_config(
                trend_pullback=BrooksTrendPullbackConfig(enabled=True),
                breakout_pullback=BrooksBreakoutPullbackConfig(enabled=True),
                failed_breakout=BrooksFailedBreakoutConfig(enabled=True),
            ),
        )
        profile = load_universe_profile("brooks_range_fade_baseline")

        config = build_universe_strategy_config(
            profile=profile,
            base=base,
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
        )

        self.assertFalse(config.brooks.setups.trend_pullback.enabled)
        self.assertFalse(config.brooks.setups.breakout_pullback.enabled)
        self.assertTrue(config.brooks.setups.failed_breakout.enabled)

    def test_brooks_setup_config_specs_match_runtime_definitions(self) -> None:
        specs = brooks_setup_config_specs()
        definitions = all_setup_definitions()

        self.assertEqual(
            {SetupKind(spec.kind_value) for spec in specs},
            set(SetupKind),
        )
        self.assertEqual(
            {definition.kind for definition in definitions},
            set(SetupKind),
        )
        self.assertEqual(len(specs), len(SetupKind))
        self.assertEqual(len(definitions), len(SetupKind))

        specs_by_kind = {SetupKind(spec.kind_value): spec for spec in specs}
        for definition in definitions:
            with self.subTest(setup=definition.kind.value):
                self.assertIs(definition.config_spec, specs_by_kind[definition.kind])
                self.assertEqual(definition.config_spec.kind_value, definition.kind.value)
                self.assertEqual(definition.config_attr, definition.config_spec.config_attr)
                self.assertGreaterEqual(definition.required_history(make_strategy_config()), 0)

    def test_brooks_strategy_templates_pin_scoring_weights(self) -> None:
        for path in sorted(Path("configs/strategies/brooks").glob("*.toml")):
            with self.subTest(config=str(path)):
                raw = tomllib.loads(path.read_text())
                strategies = raw.get("strategies", ())
                self.assertGreater(len(strategies), 0)
                for strategy in strategies:
                    trader_equation = strategy["brooks"]["trader_equation"]
                    probability_weights = trader_equation.get("probability_weights")
                    setup_score_weights = trader_equation.get("setup_score_weights")

                    self.assertIsNotNone(probability_weights)
                    self.assertIsNotNone(setup_score_weights)
                    self.assertEqual(
                        set(probability_weights),
                        {"trend_continuation", "breakout_continuation", "range_fade"},
                    )
                    self.assertEqual(
                        set(setup_score_weights),
                        {"trend_pullback", "breakout_continuation", "range_fade"},
                    )


    def test_nested_strategy_config_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "nested.toml"
            config_path.write_text(
                """
[strategy]
id = "nested"
name = "brooks"
symbols = ["nearusdt"]
fast_interval = "1h"
slow_interval = "4h"

[strategy.market]
atr_period = 21

[strategy.trade]
profit_target_r_multiple = 1.25
trail_atr_multiple = 1.8

[strategy.trend]
fast_ema = 34
slow_ema = 144

[strategy.execution]
allow_long = false
allow_short = true

[strategy.brooks.setups.breakout_pullback]
enabled = true

[strategy.brooks.setups.trend_pullback]
min_signal_score = 0.70

[strategy.brooks.structure]
range_lookback = 64

[strategy.brooks.trader_equation.probability_weights.trend_continuation]
base = 0.10
context = 0.30

[strategy.brooks.trader_equation.setup_score_weights.trend_pullback]
setup_ema = 1.0
location_setup = 1.0
location_anti_range = 0.0
"""
            )
            config = load_config(config_path)
            strategy = config.strategy
            self.assertIsNotNone(strategy)
            assert strategy is not None
            self.assertIsInstance(strategy, BrooksStrategyConfig)
            assert isinstance(strategy, BrooksStrategyConfig)
            self.assertEqual(strategy.symbols, ("NEARUSDT",))
            self.assertEqual(strategy.market.atr_period, 21)
            self.assertEqual(strategy.trade.profit_target_r_multiple, 1.25)
            self.assertEqual(strategy.trend.fast_ema, 34)
            self.assertFalse(strategy.execution.allow_long)
            self.assertTrue(strategy.execution.allow_short)
            self.assertTrue(strategy.brooks.setups.breakout_pullback.enabled)
            self.assertEqual(strategy.brooks.setups.trend_pullback.min_signal_score, 0.70)
            self.assertEqual(strategy.brooks.structure.range_lookback, 64)
            self.assertEqual(strategy.brooks.trader_equation.probability_weights.trend_continuation.base, 0.10)
            self.assertEqual(strategy.brooks.trader_equation.probability_weights.trend_continuation.context, 0.30)
            self.assertEqual(strategy.brooks.trader_equation.setup_score_weights.trend_pullback.setup_ema, 1.0)
            self.assertEqual(strategy.brooks.trader_equation.setup_score_weights.trend_pullback.location_setup, 1.0)
            self.assertEqual(
                strategy.brooks.trader_equation.setup_score_weights.trend_pullback.location_anti_range,
                0.0,
            )

    def test_baseline_strategy_rejects_brooks_section(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "baseline.toml"
            config_path.write_text(
                """
[strategy]
id = "baseline"
name = "breakout_atr"
symbols = ["btcusdt"]

[strategy.brooks.setups.breakout_pullback]
enabled = true
"""
            )

            with self.assertRaisesRegex(ValueError, "unknown keys for BreakoutAtrStrategyConfig"):
                load_config(config_path)


    def test_repository_configs_load(self) -> None:
        config_paths = sorted(Path("configs/examples").glob("**/*.toml"))
        config_paths.extend(sorted(Path("configs/strategies").glob("**/*.toml")))
        self.assertGreaterEqual(len(config_paths), 3)
        for config_path in config_paths:
            with self.subTest(config=str(config_path)):
                config = load_config(config_path)
                self.assertGreaterEqual(len(config.active_strategies()), 1)
