from dataclasses import dataclass, field
from datetime import time


@dataclass
class Config:
    symbol: str = "SPY"

    # Session windows (US/Eastern). 0DTE in the morning, ~3DTE in the afternoon.
    zero_dte_start: time = time(9, 31)
    zero_dte_end: time = time(11, 30)
    three_dte_start: time = time(13, 0)
    three_dte_end: time = time(15, 45)  # no new entries after this
    flat_by: time = time(15, 55)  # force-close anything still open
    afternoon_min_calendar_dte: int = 3

    # Key levels (all computed before the open)
    round_step: float = 5.0  # SPY multiples of $5
    round_range_pct: float = 0.015  # only round numbers within 1.5% of the pre-open price
    merge_distance: float = 0.25  # levels closer than this collapse into one

    # Touch / reversal rules (underlying $)
    touch_tolerance: float = 0.10  # bar must trade within this of the level
    max_pierce: float = 0.35  # trading further through the level = broken
    confirm_distance: float = 0.05  # confirming close must be this far back on the right side
    confirm_bars: int = 3  # bars allowed after the touch to confirm the reversal
    trades_per_level: int = 1

    # Option trade management (option premium $ per share)
    take_profit: float = 0.40  # inside the post's $0.30-$0.60 band
    stop_loss: float = 0.30
    max_hold_minutes: int = 12
    slippage: float = 0.02  # paid on entry and exit, per share
    fee_per_contract: float = 0.03
    contracts: int = 1

    # Daily risk limits
    max_trades_per_day: int = 5
    max_losses_per_day: int = 2
    max_daily_loss: float = 150.0  # $ across all contracts

    # Pricing model fallback (backtest / when no chain IV is available)
    default_iv: float = 0.16
    risk_free: float = 0.04

    extra_levels: list = field(default_factory=list)
