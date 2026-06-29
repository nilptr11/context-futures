# ruff: noqa: F403,F405,I001
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
                name="brooks_trend_only",
                template_config_path=Path("configs/strategies/brooks/price_action_portfolio.toml"),
                enabled_setups=(SetupKind.TREND_PULLBACK,),
            ),
            base=base,
            symbol="ETHUSDT",
            fast_interval="30m",
            slow_interval="1h",
        )

        self.assertEqual(config.symbols, ("ETHUSDT",))
        self.assertEqual(config.market.atr_period, 28)
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

[strategy.breakout]
window = 120

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
"""
            )
            config = load_config(config_path)
            strategy = config.strategy
            self.assertIsNotNone(strategy)
            assert strategy is not None
            self.assertEqual(strategy.symbols, ("NEARUSDT",))
            self.assertEqual(strategy.market.atr_period, 21)
            self.assertEqual(strategy.trade.profit_target_r_multiple, 1.25)
            self.assertEqual(strategy.trend.fast_ema, 34)
            self.assertFalse(strategy.execution.allow_long)
            self.assertTrue(strategy.execution.allow_short)
            self.assertTrue(strategy.brooks.setups.breakout_pullback.enabled)
            self.assertEqual(strategy.brooks.setups.trend_pullback.min_signal_score, 0.70)


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
