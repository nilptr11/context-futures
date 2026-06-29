# ruff: noqa: F403,F405,I001
from .helpers import *

class BacktestArtifactTests(unittest.TestCase):
    def test_write_independent_artifacts_outputs_standard_tables(self) -> None:
        account_a = AccountSpec("strat_a:BTCUSDT", "strat_a", "BTCUSDT", "1h", "4h")
        account_b = AccountSpec("strat_b:ETHUSDT", "strat_b", "ETHUSDT", "30m", "4h")
        report_a = BacktestReport(
            name="BTCUSDT",
            initial_equity=100.0,
            final_equity=150.0,
            max_drawdown=-0.10,
            trades=(
                Trade(
                    symbol="BTCUSDT",
                    strategy_id="strat_a",
                    side="LONG",
                    entry_time=utc_ms("2023-01-02"),
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=95.0,
                    exit_time=utc_ms("2023-02-01"),
                    exit_price=120.0,
                    pnl=20.0,
                    fees=1.0,
                    funding=0.5,
                ),
            ),
            funding=0.5,
            equity_curve=(
                EquityPoint(utc_ms("2023-01-01"), 100.0),
                EquityPoint(utc_ms("2024-01-01"), 150.0),
            ),
        )
        report_b = BacktestReport(
            name="ETHUSDT",
            initial_equity=100.0,
            final_equity=80.0,
            max_drawdown=-0.25,
            trades=(
                Trade(
                    symbol="ETHUSDT",
                    strategy_id="strat_b",
                    side="SHORT",
                    entry_time=utc_ms("2023-03-01"),
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=105.0,
                    exit_time=utc_ms("2023-04-01"),
                    exit_price=120.0,
                    pnl=-20.0,
                    fees=1.0,
                    funding=-0.2,
                ),
            ),
            funding=-0.2,
            equity_curve=(
                EquityPoint(utc_ms("2023-01-01"), 100.0),
                EquityPoint(utc_ms("2024-01-01"), 80.0),
            ),
        )
        aggregate = aggregate_backtest_reports("independent_accounts", [report_a, report_b])
        with TemporaryDirectory() as tmp:
            run_dir = write_backtest_artifacts(
                artifact_root=Path(tmp),
                run_name="artifact_test",
                account_mode="independent",
                report=aggregate,
                accounts=(
                    AccountBacktestResult(account_a, report_a),
                    AccountBacktestResult(account_b, report_b),
                ),
                account_specs=(account_a, account_b),
                config_paths=("configs/examples/single_breakout_atr.toml",),
                data_root=Path("data/parquet/binance_usdm"),
                start="2023-01-01",
                end="2024-01-01",
                risk=RiskConfig(initial_equity=100.0),
            )

            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "summary.md").exists())
            self.assertTrue((run_dir / "period_returns.csv").exists())
            self.assertTrue((run_dir / "account_results.csv").exists())
            with (run_dir / "summary.json").open() as handle:
                import json

                summary = json.load(handle)
            self.assertEqual(summary["account_mode"], "independent")
            self.assertEqual(summary["accounts"], 2)
            self.assertEqual(summary["initial_equity"], 200.0)
            self.assertEqual(summary["final_equity"], 230.0)

            with (run_dir / "account_results.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["account_key"] for row in rows}, {"strat_a:BTCUSDT", "strat_b:ETHUSDT"})

            with (run_dir / "strategy_contribution.csv").open(newline="") as handle:
                contribution = {row["strategy_id"]: row for row in csv.DictReader(handle)}
            self.assertEqual(contribution["strat_a"]["pnl"], "20.00")
            self.assertEqual(contribution["strat_b"]["pnl"], "-20.00")


class ReportingAndArtifactTests(unittest.TestCase):
    def test_monthly_returns_compound_from_prior_month_end(self) -> None:
        points = (
            EquityPoint(utc_ms("2024-01-01"), 100.0),
            EquityPoint(utc_ms("2024-01-31"), 110.0),
            EquityPoint(utc_ms("2024-02-01"), 108.0),
            EquityPoint(utc_ms("2024-02-29"), 99.0),
        )
        trades = (
            Trade(
                "BTCUSDT",
                "LONG",
                utc_ms("2024-01-05"),
                100.0,
                1.0,
                95.0,
                utc_ms("2024-01-15"),
                112.0,
                10.5,
                1.0,
                -0.5,
            ),
            Trade(
                "BTCUSDT",
                "SHORT",
                utc_ms("2024-02-05"),
                108.0,
                1.0,
                112.0,
                utc_ms("2024-02-10"),
                113.0,
                -6.2,
                1.2,
                0.1,
            ),
        )
        months = calculate_monthly_returns(points, trades)

        self.assertEqual([item.month for item in months], ["2024-01", "2024-02"])
        self.assertAlmostEqual(months[0].return_rate, 0.10)
        self.assertAlmostEqual(months[1].start_equity, 110.0)
        self.assertAlmostEqual(months[1].return_rate, -0.10)
        self.assertAlmostEqual(months[1].equity_pnl, -11.0)
        self.assertAlmostEqual(months[1].closed_trade_pnl, -6.2)
        self.assertAlmostEqual(months[1].fees, 1.2)
        self.assertEqual(months[1].trades, 1)


    def test_aggregate_backtest_results_combines_equity_curve_for_drawdown(self) -> None:
        t1 = utc_ms("2024-01-01")
        t2 = utc_ms("2024-01-02")
        first = BacktestReport(
            name="BTCUSDT",
            initial_equity=100.0,
            final_equity=90.0,
            max_drawdown=-0.10,
            trades=(),
            equity_curve=(EquityPoint(t1, 100.0), EquityPoint(t2, 90.0)),
        )
        second = BacktestReport(
            name="ETHUSDT",
            initial_equity=200.0,
            final_equity=240.0,
            max_drawdown=0.0,
            trades=(),
            equity_curve=(EquityPoint(t1, 200.0), EquityPoint(t2, 240.0)),
        )

        result = aggregate_backtest_reports("ALL", [first, second])

        self.assertEqual(result.initial_equity, 300.0)
        self.assertEqual(result.final_equity, 330.0)
        self.assertAlmostEqual(result.max_drawdown, 0.0)
        self.assertEqual(result.equity_curve[-1], EquityPoint(t2, 330.0))
        self.assertEqual(len(result.monthly_returns), 1)


    def test_trade_csv_includes_brooks_telemetry(self) -> None:
        trade = Trade(
            "BTCUSDT",
            "LONG",
            utc_ms("2024-01-05"),
            100.0,
            1.0,
            95.0,
            utc_ms("2024-01-15"),
            112.0,
            10.5,
            1.0,
            -0.5,
            diagnostics=SignalDiagnostics(
                market_cycle="CHANNEL",
                market_overlay="NONE",
                context_state="BULL_CHANNEL",
                context_direction=1,
                raw_regime="CHANNEL_UP",
                control_gap=0.75,
                breakout_follow_through_score=0.20,
                target_model="measured_move",
                trader_equation_cost_r=0.05,
                stop_distance_atr=1.4,
                pullback_depth_score=0.50,
                pullback_wedge_score=1.00,
            ),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "trades.csv"
            write_trades_csv(output, [trade])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["market_cycle"], "CHANNEL")
        self.assertEqual(rows[0]["market_overlay"], "NONE")
        self.assertEqual(rows[0]["context_state"], "BULL_CHANNEL")
        self.assertEqual(rows[0]["context_direction"], "1")
        self.assertEqual(rows[0]["raw_regime"], "CHANNEL_UP")
        self.assertEqual(rows[0]["target_model"], "measured_move")
        self.assertEqual(rows[0]["trader_equation_cost_r"], "0.05")
        self.assertEqual(rows[0]["pullback_depth_score"], "0.5")
        self.assertEqual(rows[0]["pullback_wedge_score"], "1.0")


    def test_brooks_bucket_summary_groups_by_cycle_and_setup(self) -> None:
        trades = (
            Trade(
                symbol="BTCUSDT",
                side="LONG",
                entry_time=1,
                entry_price=100.0,
                quantity=1.0,
                stop_price=95.0,
                exit_time=2,
                exit_price=112.0,
                pnl=10.0,
                setup_kind="TREND_PULLBACK",
                diagnostics=SignalDiagnostics(
                    setup_family="TREND_CONTINUATION",
                    pattern_variant="WEDGE_PULLBACK",
                    market_cycle="CHANNEL",
                    context_score=0.70,
                    control_gap=0.80,
                    breakout_follow_through_score=0.20,
                    target_room_r=2.0,
                    probability_score=0.75,
                    edge_score_r=1.20,
                ),
            ),
            Trade(
                symbol="ETHUSDT",
                side="LONG",
                entry_time=3,
                entry_price=100.0,
                quantity=1.0,
                stop_price=95.0,
                exit_time=4,
                exit_price=94.0,
                pnl=-6.0,
                setup_kind="TREND_PULLBACK",
                diagnostics=SignalDiagnostics(
                    setup_family="TREND_CONTINUATION",
                    pattern_variant="H2",
                    market_cycle="CHANNEL",
                    context_score=0.60,
                    control_gap=0.70,
                    breakout_follow_through_score=0.10,
                    target_room_r=2.0,
                    probability_score=0.70,
                    edge_score_r=1.00,
                ),
            ),
            Trade(
                symbol="BTCUSDT",
                side="SHORT",
                entry_time=5,
                entry_price=100.0,
                quantity=1.0,
                stop_price=105.0,
                exit_time=6,
                exit_price=90.0,
                pnl=8.0,
                setup_kind="BREAKOUT_PULLBACK",
                diagnostics=SignalDiagnostics(
                    setup_family="BREAKOUT_CONTINUATION",
                    pattern_variant="BREAKOUT_PULLBACK",
                    market_cycle="BREAKOUT",
                ),
            ),
        )

        summaries = summarize_brooks_buckets(trades, dimensions=(("setup_kind", "market_cycle"),))
        channel = next(item for item in summaries if item.bucket == "setup_kind=TREND_PULLBACK|market_cycle=CHANNEL")

        self.assertEqual(channel.trades, 2)
        self.assertEqual(channel.wins, 1)
        self.assertEqual(channel.losses, 1)
        self.assertAlmostEqual(channel.pnl, 4.0)
        self.assertAlmostEqual(channel.win_rate, 0.5)
        self.assertAlmostEqual(channel.profit_factor, 10.0 / 6.0)
        self.assertAlmostEqual(channel.avg_context_score, 0.65)
        self.assertAlmostEqual(channel.avg_probability_score, 0.725)

        variant_summaries = summarize_brooks_buckets(trades, dimensions=(("setup_family", "pattern_variant"),))
        wedge = next(
            item
            for item in variant_summaries
            if item.bucket == "setup_family=TREND_CONTINUATION|pattern_variant=WEDGE_PULLBACK"
        )
        self.assertEqual(wedge.trades, 1)


    def test_brooks_decision_summary_groups_reasons_by_cycle(self) -> None:
        records = (
            BrooksDecisionRecord(
                strategy_id="brooks_pa_btc_1h",
                symbol="BTCUSDT",
                signal_time=1,
                next_open_time=2,
                close=100.0,
                setup_kind="TREND_PULLBACK",
                setup_family="TREND_CONTINUATION",
                pattern_variant="WEDGE_PULLBACK",
                side=1,
                setup_enabled=True,
                accepted=True,
                decision_reason="accepted",
                diagnostics=SignalDiagnostics(
                    setup_family="TREND_CONTINUATION",
                    pattern_variant="WEDGE_PULLBACK",
                    market_cycle="TREND",
                    context_score=0.70,
                    probability_score=0.75,
                    edge_score_r=1.20,
                    pullback_depth_score=0.60,
                    pullback_wedge_score=1.00,
                ),
            ),
            BrooksDecisionRecord(
                strategy_id="brooks_pa_eth_30m",
                symbol="ETHUSDT",
                signal_time=3,
                next_open_time=4,
                close=100.0,
                setup_kind="TREND_PULLBACK",
                setup_family="TREND_CONTINUATION",
                pattern_variant="H2",
                side=1,
                setup_enabled=True,
                accepted=False,
                decision_reason="target_room",
                diagnostics=SignalDiagnostics(
                    setup_family="TREND_CONTINUATION",
                    pattern_variant="H2",
                    market_cycle="TREND",
                    context_score=0.60,
                    probability_score=0.70,
                    edge_score_r=1.00,
                    pullback_depth_score=0.40,
                    pullback_wedge_score=0.00,
                ),
            ),
            BrooksDecisionRecord(
                strategy_id="brooks_pa_btc_1h",
                symbol="BTCUSDT",
                signal_time=5,
                next_open_time=6,
                close=100.0,
                setup_kind="",
                side=0,
                setup_enabled=False,
                accepted=False,
                decision_reason="no_candidate_kind",
                diagnostics=SignalDiagnostics(market_cycle="TRADING_RANGE"),
            ),
        )

        summaries = summarize_brooks_decisions(records, dimensions=(("market_cycle",),))
        trend = next(item for item in summaries if item.bucket == "market_cycle=TREND")

        self.assertEqual(trend.records, 2)
        self.assertEqual(trend.accepted, 1)
        self.assertEqual(trend.rejected, 1)
        self.assertAlmostEqual(trend.accept_rate, 0.5)
        self.assertAlmostEqual(trend.avg_context_score, 0.65)
        self.assertAlmostEqual(trend.avg_probability_score, 0.725)
        self.assertAlmostEqual(trend.avg_pullback_depth_score, 0.50)
        self.assertAlmostEqual(trend.avg_pullback_wedge_score, 0.50)

