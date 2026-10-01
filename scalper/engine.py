"""Bar-by-bar strategy engine shared by the backtester and the paper runner.

Rules (from the setup being replicated):
  1. 0DTE in the first 2 hours, ~3DTE in the last 3 hours.
  2. Key levels marked before the open.
  3. Wait for price to come to a level.
  4. Enter the reversal at the level (calls off support, puts off resistance).
  5. Take a small premium gain ($0.30-$0.60) and get out within minutes.
  No level touched -> no trade.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import math
from typing import Callable, Optional

import pandas as pd

from .config import Config
from .levels import Level
from .pricing import bs_price


@dataclass
class Trade:
    entry_time: datetime
    level: Level
    side: str  # "support" -> calls, "resistance" -> puts
    right: str
    strike: float
    expiry: date
    window: str
    iv: float
    entry_spot: float
    entry_price: float
    contracts: int
    exit_time: Optional[datetime] = None
    exit_spot: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * 100 * self.contracts

    def as_dict(self) -> dict:
        return {
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "window": self.window,
            "level": str(self.level),
            "contract": f"{self.expiry:%Y-%m-%d} {self.strike:g}{self.right}",
            "contracts": self.contracts,
            "iv": round(self.iv, 4),
            "entry_spot": round(self.entry_spot, 2),
            "exit_spot": round(self.exit_spot, 2) if self.exit_spot else None,
            "entry_price": round(self.entry_price, 2),
            "exit_price": round(self.exit_price, 2) if self.exit_price is not None else None,
            "exit_reason": self.exit_reason,
            "pnl": round(self.pnl, 2),
        }


@dataclass
class _Touch:
    level: Level
    side: str
    bar_index: int


def default_expiry_picker(cfg: Config) -> Callable[[datetime, str], date]:
    """SPY lists daily (Mon-Fri) expiries; holidays are ignored in this approximation."""

    def pick(now: datetime, window: str) -> date:
        d = now.date()
        if window == "0DTE":
            return d
        d += timedelta(days=cfg.afternoon_min_calendar_dte)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    return pick


def minutes_to_expiry(now: datetime, expiry: date) -> float:
    close = datetime.combine(expiry, time(16, 0), tzinfo=now.tzinfo)
    return max((close - now).total_seconds() / 60.0, 0.0)


class Engine:
    def __init__(
        self,
        cfg: Config,
        levels: list[Level],
        expiry_picker: Optional[Callable[[datetime, str], date]] = None,
        iv_lookup: Optional[Callable[[datetime, date, float, str], Optional[float]]] = None,
        log: Callable[[str], None] = lambda s: None,
    ):
        self.cfg = cfg
        self.levels = levels
        self.pick_expiry = expiry_picker or default_expiry_picker(cfg)
        self.iv_lookup = iv_lookup
        self.log = log
        self.trades: list[Trade] = []
        self.open: Optional[Trade] = None
        self.touches: dict[float, _Touch] = {}
        self.level_uses: dict[float, int] = {}
        self.prev_close: Optional[float] = None
        self.i = 0
        self.halted = ""

    # -- helpers ---------------------------------------------------------------
    def window(self, t: time) -> Optional[str]:
        c = self.cfg
        if c.zero_dte_start <= t < c.zero_dte_end:
            return "0DTE"
        if c.three_dte_start <= t < c.three_dte_end:
            return "3DTE"
        return None

    def price(self, tr: Trade, spot: float, now: datetime) -> float:
        return bs_price(spot, tr.strike, minutes_to_expiry(now, tr.expiry), tr.iv, tr.right, self.cfg.risk_free)

    @property
    def realized(self) -> float:
        return sum(t.pnl - 2 * self.cfg.fee_per_contract * t.contracts for t in self.trades if t.exit_price is not None)

    def _check_limits(self) -> None:
        c = self.cfg
        closed = [t for t in self.trades if t.exit_price is not None]
        losses = sum(1 for t in closed if t.pnl < 0)
        if len(self.trades) >= c.max_trades_per_day:
            self.halted = "max trades reached"
        elif losses >= c.max_losses_per_day:
            self.halted = "max losing trades reached"
        elif self.realized <= -c.max_daily_loss:
            self.halted = "daily loss limit hit"
        if self.halted:
            self.log(f"HALT: {self.halted} — no more entries today")

    # -- main loop -------------------------------------------------------------
    def on_bar(self, ts: pd.Timestamp, o: float, h: float, l: float, c: float) -> None:
        now = ts.to_pydatetime()
        # The bar stamped ts covers [ts, ts+1m); decisions happen at its close.
        decided = now + timedelta(minutes=1)
        if self.open:
            self._manage(decided, h, l, c)
        if not self.open and not self.halted:
            self._scan(decided, ts.time(), o, h, l, c)
        self.prev_close = c
        self.i += 1

    def _manage(self, now: datetime, h: float, l: float, c: float) -> None:
        tr, cfg = self.open, self.cfg
        calls = tr.right == "C"
        best = self.price(tr, h if calls else l, now)
        worst = self.price(tr, l if calls else h, now)
        target = tr.entry_price + cfg.take_profit
        stop = tr.entry_price - cfg.stop_loss
        broken = (c < tr.level.price - cfg.max_pierce) if calls else (c > tr.level.price + cfg.max_pierce)
        held = (now - tr.entry_time).total_seconds() / 60

        exit_px, reason, spot = None, "", c
        # If one bar spans both the stop and the target, assume the stop came first.
        if worst <= stop:
            exit_px, reason, spot = stop, "stop", (l if calls else h)
        elif best >= target:
            exit_px, reason, spot = target, "target", (h if calls else l)
        elif broken:
            exit_px, reason = self.price(tr, c, now), "level broke"
        elif held >= cfg.max_hold_minutes:
            exit_px, reason = self.price(tr, c, now), "time stop"
        elif now.time() >= cfg.flat_by:
            exit_px, reason = self.price(tr, c, now), "end of day"
        if exit_px is not None:
            self._close(now, spot, exit_px, reason)

    def _close(self, now: datetime, spot: float, mark: float, reason: str) -> None:
        tr = self.open
        tr.exit_time, tr.exit_spot, tr.exit_reason = now, spot, reason
        tr.exit_price = max(mark - self.cfg.slippage, 0.0)
        self.open = None
        self.log(
            f"EXIT  {tr.right} {tr.strike:g} {tr.expiry} @ {tr.exit_price:.2f} ({reason}) "
            f"spot {spot:.2f} pnl ${tr.pnl:+.2f}"
        )
        self._check_limits()

    def _scan(self, now: datetime, bar_time: time, o: float, h: float, l: float, c: float) -> None:
        cfg = self.cfg
        window = self.window(bar_time)
        prev = self.prev_close if self.prev_close is not None else o

        for lv in self.levels:
            p = lv.price
            if self.level_uses.get(p, 0) >= cfg.trades_per_level:
                continue
            touch = self.touches.get(p)

            # Invalidate an armed touch if price blew through the level or took too long.
            if touch:
                broke = l < p - cfg.max_pierce if touch.side == "support" else h > p + cfg.max_pierce
                if broke or self.i - touch.bar_index > cfg.confirm_bars:
                    del self.touches[p]
                    touch = None

            # New touch: arriving from the far side and tagging the level without breaking it.
            if not touch:
                if prev > p + cfg.touch_tolerance and l <= p + cfg.touch_tolerance and l >= p - cfg.max_pierce:
                    touch = self.touches[p] = _Touch(lv, "support", self.i)
                elif prev < p - cfg.touch_tolerance and h >= p - cfg.touch_tolerance and h <= p + cfg.max_pierce:
                    touch = self.touches[p] = _Touch(lv, "resistance", self.i)
                else:
                    continue

            # Reversal confirmation: a bar that closes back away from the level, in the reversal direction.
            if touch.side == "support":
                confirmed = c >= p + cfg.confirm_distance and c > o
            else:
                confirmed = c <= p - cfg.confirm_distance and c < o
            if confirmed and window:
                del self.touches[p]
                self._enter(now, window, touch, c)
                return

    def _enter(self, now: datetime, window: str, touch: _Touch, spot: float) -> None:
        cfg = self.cfg
        right = "C" if touch.side == "support" else "P"
        strike = float(round(spot))
        expiry = self.pick_expiry(now, window)
        iv = None
        if self.iv_lookup:
            iv = self.iv_lookup(now, expiry, strike, right)
        if not iv or not math.isfinite(iv) or iv <= 0.01:
            iv = cfg.default_iv
        tr = Trade(now, touch.level, touch.side, right, strike, expiry, window, iv, spot, 0.0, cfg.contracts)
        tr.entry_price = self.price(tr, spot, now) + cfg.slippage
        if tr.entry_price < 0.10:
            self.log(f"skip {right} {strike:g}: premium too small ({tr.entry_price:.2f})")
            return
        self.level_uses[touch.level.price] = self.level_uses.get(touch.level.price, 0) + 1
        self.open = tr
        self.trades.append(tr)
        self.log(
            f"ENTER {window} {touch.side} @ {touch.level} -> buy {cfg.contracts}x {expiry} {strike:g}{right} "
            f"@ {tr.entry_price:.2f} (spot {spot:.2f}, iv {iv:.1%})"
        )
        self._check_limits()

    def force_flat(self, now: datetime, spot: float) -> None:
        if self.open:
            self._close(now, spot, self.price(self.open, spot, now), "end of day")
