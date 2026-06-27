from __future__ import annotations

from dataclasses import dataclass

from .portfolio import EquityPoint
from .position import Trade


@dataclass(frozen=True, slots=True)
class MonthlyReturn:
    month: str
    start_time: int
    end_time: int
    start_equity: float
    end_equity: float
    equity_pnl: float
    return_rate: float
    closed_trade_pnl: float
    fees: float
    funding: float
    trades: int


@dataclass(frozen=True, slots=True)
class SymbolYearReturn:
    config: str
    strategy_id: str
    symbol: str
    fast_interval: str
    slow_interval: str
    year: int
    start: str
    end_exclusive: str
    cost_usdt: float
    final_usdt: float
    pnl_usdt: float
    return_rate: float
    max_drawdown: float
    trades: int
    win_rate: float
    profit_factor: float
    funding: float


@dataclass(frozen=True, slots=True)
class UniverseBacktestRow:
    profile: str
    symbol: str
    fast_interval: str
    slow_interval: str
    window: str
    start: str
    end_exclusive: str
    cost_usdt: float
    final_usdt: float
    pnl_usdt: float
    return_rate: float
    max_drawdown: float
    trades: int
    win_rate: float
    profit_factor: float
    funding: float
    status: str = "ok"
    error: str = ""


@dataclass(frozen=True, slots=True)
class BacktestReport:
    name: str
    initial_equity: float
    final_equity: float
    max_drawdown: float
    trades: tuple[Trade, ...]
    funding: float = 0.0
    equity_curve: tuple[EquityPoint, ...] = ()
    monthly_returns: tuple[MonthlyReturn, ...] = ()

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_equity - 1.0 if self.initial_equity > 0 else 0.0

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for trade in self.trades if trade.pnl > 0)
        return wins / len(self.trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(trade.pnl for trade in self.trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in self.trades if trade.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss


BacktestResult = BacktestReport
