# ruff: noqa: F403,F405,I001
from .helpers import *

class PointInTimeMarketViewTests(unittest.TestCase):
    def test_closed_bars_hide_future_bars_unfinished_higher_timeframe_and_future_funding(self) -> None:
        fast = [
            make_interval_candle(0, 3_600_000, 100.0, "1h"),
            make_interval_candle(1, 3_600_000, 101.0, "1h"),
            make_interval_candle(2, 3_600_000, 999.0, "1h"),
        ]
        slow = [make_interval_candle(0, 14_400_000, 105.0, "4h")]
        funding = [
            FundingRate("BTCUSDT", funding_time=0, funding_rate=0.01, available_at=0),
            FundingRate("BTCUSDT", funding_time=1_000, funding_rate=0.99, available_at=99_000_000),
        ]
        data = BacktestData.from_candles(
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
            fast=fast,
            slow=slow,
            funding=funding,
        )
        view = MarketView(
            data=data,
            now=fast[1].close_time + 1,
            strategy_id="test",
            decision_candle=fast[1],
            next_open_candle=fast[2],
        )

        visible_fast = view.closed_bars("1h")
        self.assertEqual(len(visible_fast), 2)
        self.assertEqual(visible_fast[-1].close, 101.0)
        self.assertEqual(tuple(view.closed_bars("4h")), ())
        self.assertEqual(view.latest_funding_rate(), 0.01)

    def test_trend_filter_rejects_queries_after_view_time(self) -> None:
        fast = [make_interval_candle(idx, 3_600_000, 100.0 + idx, "1h") for idx in range(3)]
        slow = [make_interval_candle(idx, 14_400_000, 100.0 + idx, "4h") for idx in range(3)]
        data = BacktestData.from_candles(
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
            fast=fast,
            slow=slow,
        )
        view = MarketView(
            data=data,
            now=slow[0].close_time + 1,
            strategy_id="test",
            decision_candle=fast[-1],
            next_open_candle=None,
        )
        trend = view.trend_filter(1, 2, "4h")

        self.assertIsInstance(trend.trend_at(slow[0].close_time), int)
        with self.assertRaises(ValueError):
            trend.trend_at(slow[1].close_time)



