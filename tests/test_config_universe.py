# ruff: noqa: F403,F405,I001
from .helpers import *

class ConfigUniverseTests(unittest.TestCase):
    def test_universe_brooks_profile_scales_periods_by_timeframe_duration(self) -> None:
        base = make_strategy_config(
            id="brooks_pa_btc_1h",
            name="brooks_price_action",
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
            profile="brooks_trend_only",
            base=base,
            symbol="ETHUSDT",
            fast_interval="30m",
            slow_interval="1h",
        )

        self.assertEqual(config.symbols, ("ETHUSDT",))
        self.assertEqual(config.breakout.atr_period, 28)
        self.assertEqual(config.brooks.setups.trend_pullback.entry_ema, 40)
        self.assertEqual(config.brooks.setups.trend_pullback.lookback, 24)
        self.assertEqual(config.trend.fast_ema, 200)
        self.assertEqual(config.trend.slow_ema, 800)
        self.assertTrue(config.brooks.setups.trend_pullback.enabled)
        self.assertFalse(config.brooks.setups.breakout_pullback.enabled)


    def test_nested_strategy_config_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "nested.toml"
            config_path.write_text(
                """
[strategy]
id = "nested"
name = "brooks_price_action"
symbols = ["nearusdt"]
fast_interval = "1h"
slow_interval = "4h"

[strategy.breakout]
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
"""
            )
            config = load_config(config_path)
            strategy = config.strategy
            self.assertEqual(strategy.symbols, ("NEARUSDT",))
            self.assertEqual(strategy.breakout.atr_period, 21)
            self.assertEqual(strategy.trade.profit_target_r_multiple, 1.25)
            self.assertEqual(strategy.trend.fast_ema, 34)
            self.assertFalse(strategy.execution.allow_long)
            self.assertTrue(strategy.execution.allow_short)
            self.assertTrue(strategy.brooks.setups.breakout_pullback.enabled)
            self.assertEqual(strategy.brooks.setups.trend_pullback.min_signal_score, 0.70)


    def test_repository_configs_load(self) -> None:
        config_paths = sorted(Path("configs").glob("**/*.toml"))
        self.assertGreaterEqual(len(config_paths), 3)
        for config_path in config_paths:
            with self.subTest(config=str(config_path)):
                config = load_config(config_path)
                self.assertGreaterEqual(len(config.active_strategies()), 1)
