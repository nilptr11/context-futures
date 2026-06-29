from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from context_futures.config import (
    AppConfig,
    BreakoutConfig,
    BrooksConfig,
    BrooksStrategyConfig,
    MarketMeasureConfig,
    PriceActionFilterConfig,
    RiskConfig,
    TrendConfig,
    load_config,
)
from context_futures.data import ParquetMarketDataStore
from context_futures.domain import UniverseBacktestRow
from context_futures.strategies.brooks.setups import SetupKind
from context_futures.strategies.brooks.setups.registry import scale_brooks_setups, set_enabled_setups
from context_futures.strategies.registry import create_strategy

from .datasets import load_backtest_data
from .market_view import BacktestData
from .single import run_backtest

DEFAULT_INTERVALS = ("5m", "15m", "30m", "1h", "4h")
DEFAULT_PROFILE_DIR = Path("configs/universe_profiles")


@dataclass(frozen=True, slots=True)
class UniverseProfile:
    name: str
    template_config_path: Path
    enabled_setups: tuple[SetupKind, ...]


def collect_universe_backtests(
    *,
    profile: str,
    template_config_path: str | Path | None,
    data_root: Path,
    symbols: tuple[str, ...],
    intervals: tuple[str, ...],
    start_time: int,
    end_time: int,
    initial_equity: float,
    risk_fraction: float | None = None,
) -> tuple[UniverseBacktestRow, ...]:
    profile_config = load_universe_profile(profile, template_config_path)
    template = load_profile_template(profile_config)
    base_strategy = _base_strategy(template)
    risk = replace(template.risk, initial_equity=initial_equity)
    if risk_fraction is not None:
        risk = replace(risk, risk_fraction=risk_fraction)

    windows = (*iter_year_windows(start_time, end_time), total_window(start_time, end_time))
    pairs = timeframe_pairs(intervals)
    store = ParquetMarketDataStore(data_root)
    data_cache = BacktestDataCache(store)
    rows: list[UniverseBacktestRow] = []

    for symbol in symbols:
        for fast_interval, slow_interval in pairs:
            strategy_config = build_universe_strategy_config(
                profile=profile_config,
                base=base_strategy,
                symbol=symbol,
                fast_interval=fast_interval,
                slow_interval=slow_interval,
            )
            try:
                data = data_cache.load(symbol, fast_interval, slow_interval)
            except Exception as exc:
                rows.extend(
                    _error_row(
                        profile=profile_config.name,
                        symbol=symbol,
                        fast_interval=fast_interval,
                        slow_interval=slow_interval,
                        window=window,
                        risk=risk,
                        error=exc,
                    )
                    for window in windows
                )
                continue

            strategy = create_strategy(strategy_config)
            for window in windows:
                try:
                    report = run_backtest(
                        strategy=strategy,
                        risk=risk,
                        symbol=symbol,
                        data=data,
                        trade_start_time=window.start_time,
                        trade_end_time=window.end_time,
                    )
                except Exception as exc:
                    rows.append(
                        _error_row(
                            profile=profile_config.name,
                            symbol=symbol,
                            fast_interval=fast_interval,
                            slow_interval=slow_interval,
                            window=window,
                            risk=risk,
                            error=exc,
                        )
                    )
                    continue
                rows.append(
                    UniverseBacktestRow(
                        profile=profile_config.name,
                        symbol=symbol,
                        fast_interval=fast_interval,
                        slow_interval=slow_interval,
                        window=window.label,
                        start=date_label(window.start_time),
                        end_exclusive=date_label(window.end_time),
                        cost_usdt=report.initial_equity,
                        final_usdt=report.final_equity,
                        pnl_usdt=report.final_equity - report.initial_equity,
                        return_rate=report.total_return,
                        max_drawdown=report.max_drawdown,
                        trades=len(report.trades),
                        win_rate=report.win_rate,
                        profit_factor=report.profit_factor,
                        funding=report.funding,
                    )
                )
    return tuple(rows)


class BacktestDataCache:
    def __init__(self, store: ParquetMarketDataStore) -> None:
        self.store = store
        self._values: dict[tuple[str, str, str], BacktestData] = {}

    def load(self, symbol: str, fast_interval: str, slow_interval: str) -> BacktestData:
        key = (symbol, fast_interval, slow_interval)
        if key not in self._values:
            self._values[key] = load_backtest_data(
                self.store,
                symbol=symbol,
                fast_interval=fast_interval,
                slow_interval=slow_interval,
            )
        return self._values[key]


class UniverseWindow:
    def __init__(self, label: str, start_time: int, end_time: int) -> None:
        self.label = label
        self.start_time = start_time
        self.end_time = end_time


def available_universe_profiles(profile_dir: Path = DEFAULT_PROFILE_DIR) -> tuple[str, ...]:
    if not profile_dir.exists():
        return ()
    return tuple(sorted(path.stem for path in profile_dir.glob("*.toml")))


def load_universe_profile(
    profile: str,
    template_config_path: str | Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
) -> UniverseProfile:
    path = profile_dir / f"{profile}.toml"
    if not path.exists():
        choices = ", ".join(available_universe_profiles(profile_dir))
        raise ValueError(f"unknown universe profile '{profile}'. available: {choices}")
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    allowed = {"name", "template_config", "enabled_setups"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown keys for UniverseProfile: {sorted(unknown)}")
    name = str(raw.get("name", profile))
    template_value = template_config_path or raw.get("template_config")
    if not template_value:
        raise ValueError(f"universe profile '{name}' requires template_config")
    template = Path(template_value)
    enabled_setups = tuple(_setup_kind(value) for value in raw.get("enabled_setups", ()))
    return UniverseProfile(
        name=name,
        template_config_path=template,
        enabled_setups=enabled_setups,
    )


def load_profile_template(profile: UniverseProfile) -> AppConfig:
    return load_config(profile.template_config_path)


def discover_symbols(data_root: Path, interval: str | None = None) -> tuple[str, ...]:
    return ParquetMarketDataStore(data_root).discover_symbols(interval=interval)


def timeframe_pairs(intervals: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(sorted(dict.fromkeys(intervals), key=interval_minutes))
    return tuple((fast, slow) for idx, fast in enumerate(ordered) for slow in ordered[idx:])


def build_universe_strategy_config(
    *,
    profile: UniverseProfile,
    base: BrooksStrategyConfig,
    symbol: str,
    fast_interval: str,
    slow_interval: str,
) -> BrooksStrategyConfig:
    fast_base = base.fast_interval
    slow_base = base.slow_interval
    brooks = set_enabled_setups(
        _scale_brooks(base.brooks, fast_base, fast_interval),
        profile.enabled_setups,
    )
    return replace(
        base,
        id=_strategy_id(profile.name, symbol, fast_interval, slow_interval),
        symbols=(symbol,),
        fast_interval=fast_interval,
        slow_interval=slow_interval,
        market=_scale_market(base.market, fast_base, fast_interval),
        breakout=_scale_breakout(base.breakout, fast_base, fast_interval),
        trend=_scale_trend(base.trend, slow_base, slow_interval),
        price_action=_scale_price_action(base.price_action, fast_base, fast_interval),
        brooks=brooks,
    )


def iter_year_windows(start_time: int, end_time: int) -> tuple[UniverseWindow, ...]:
    if end_time <= start_time:
        return ()
    start = utc_datetime(start_time)
    end = utc_datetime(end_time)
    windows: list[UniverseWindow] = []
    for year in range(start.year, end.year + 1):
        year_start = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
        year_end = dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC)
        window_start = max(start, year_start)
        window_end = min(end, year_end)
        if window_start >= window_end:
            continue
        label = f"{year}_ytd" if window_end < year_end else str(year)
        windows.append(UniverseWindow(label, to_ms(window_start), to_ms(window_end)))
    return tuple(windows)


def total_window(start_time: int, end_time: int) -> UniverseWindow:
    return UniverseWindow(f"{utc_datetime(start_time).year}_now", start_time, end_time)


def interval_minutes(value: str) -> int:
    if value.endswith("m"):
        return int(value[:-1])
    if value.endswith("h"):
        return int(value[:-1]) * 60
    if value.endswith("d"):
        return int(value[:-1]) * 24 * 60
    raise ValueError(f"unsupported interval: {value}")


def utc_datetime(value: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC)


def to_ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def date_label(value: int) -> str:
    return utc_datetime(value).strftime("%Y-%m-%d")


def _base_strategy(template: AppConfig) -> BrooksStrategyConfig:
    strategies = template.active_strategies()
    if not strategies:
        raise ValueError("profile template must define at least one strategy")
    strategy = strategies[0]
    if not isinstance(strategy, BrooksStrategyConfig):
        raise ValueError("universe profile template must define a Brooks strategy")
    return strategy


def _scale_breakout(base: BreakoutConfig, base_interval: str, target_interval: str) -> BreakoutConfig:
    return replace(
        base,
        window=_scale_period(base.window, base_interval, target_interval, minimum=5),
    )


def _scale_market(base: MarketMeasureConfig, base_interval: str, target_interval: str) -> MarketMeasureConfig:
    return replace(
        base,
        atr_period=_scale_period(base.atr_period, base_interval, target_interval, minimum=3),
    )


def _scale_trend(base: TrendConfig, base_interval: str, target_interval: str) -> TrendConfig:
    return replace(
        base,
        fast_ema=_scale_period(base.fast_ema, base_interval, target_interval, minimum=5),
        slow_ema=_scale_period(base.slow_ema, base_interval, target_interval, minimum=20),
        regime_atr_period=_scale_period(base.regime_atr_period, base_interval, target_interval, minimum=3),
    )


def _scale_price_action(
    base: PriceActionFilterConfig,
    base_interval: str,
    target_interval: str,
) -> PriceActionFilterConfig:
    return replace(
        base,
        range_lookback=_scale_period(base.range_lookback, base_interval, target_interval, minimum=5),
    )


def _scale_brooks(base: BrooksConfig, base_interval: str, target_interval: str) -> BrooksConfig:
    return scale_brooks_setups(base, base_interval, target_interval)


def _scale_period(value: int, base_interval: str, target_interval: str, *, minimum: int) -> int:
    base_minutes = interval_minutes(base_interval)
    target_minutes = interval_minutes(target_interval)
    scaled = round(value * base_minutes / target_minutes)
    return max(minimum, int(scaled))


def _strategy_id(profile: str, symbol: str, fast_interval: str, slow_interval: str) -> str:
    return f"{profile}_{symbol.lower()}_{fast_interval}_{slow_interval}"


def _setup_kind(value: object) -> SetupKind:
    try:
        return SetupKind(str(value))
    except ValueError as exc:
        choices = ", ".join(item.value for item in SetupKind)
        raise ValueError(f"unknown Brooks setup kind '{value}'. available: {choices}") from exc


def _error_row(
    *,
    profile: str,
    symbol: str,
    fast_interval: str,
    slow_interval: str,
    window: UniverseWindow,
    risk: RiskConfig,
    error: Exception,
) -> UniverseBacktestRow:
    return UniverseBacktestRow(
        profile=profile,
        symbol=symbol,
        fast_interval=fast_interval,
        slow_interval=slow_interval,
        window=window.label,
        start=date_label(window.start_time),
        end_exclusive=date_label(window.end_time),
        cost_usdt=risk.initial_equity,
        final_usdt=risk.initial_equity,
        pnl_usdt=0.0,
        return_rate=0.0,
        max_drawdown=0.0,
        trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        funding=0.0,
        status="error",
        error=str(error),
    )
