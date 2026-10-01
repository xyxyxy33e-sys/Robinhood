"""Key levels marked before the open."""
from dataclasses import dataclass
import math

import pandas as pd

from .config import Config

# Higher number wins when two levels merge.
_PRIORITY = {"PDH": 5, "PDL": 5, "PDC": 4, "PMH": 4, "PML": 4, "WKH": 3, "WKL": 3, "MANUAL": 6, "ROUND": 1}


@dataclass
class Level:
    price: float
    label: str

    def __str__(self) -> str:
        return f"{self.label} {self.price:.2f}"


def _rth(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.between_time("09:30", "15:59")


def compute_levels(bars: pd.DataFrame, session_date, cfg: Config) -> list[Level]:
    """Build levels for `session_date` from 1-minute bars (tz US/Eastern, extended hours ok).

    Only data strictly before 09:30 on `session_date` is used.
    """
    day = pd.Timestamp(session_date).date()
    hist = bars[bars.index.date < day]
    rth_hist = _rth(hist)
    if rth_hist.empty:
        raise ValueError(f"no regular-session history before {day}")

    days = sorted(set(rth_hist.index.date))
    prev = rth_hist[rth_hist.index.date == days[-1]]
    week = rth_hist[rth_hist.index.date >= days[max(0, len(days) - 5)]]

    raw = [
        Level(prev["High"].max(), "PDH"),
        Level(prev["Low"].min(), "PDL"),
        Level(prev["Close"].iloc[-1], "PDC"),
        Level(week["High"].max(), "WKH"),
        Level(week["Low"].min(), "WKL"),
    ]

    today = bars[bars.index.date == day]
    pre = today.between_time("04:00", "09:29")
    if not pre.empty:
        raw += [Level(pre["High"].max(), "PMH"), Level(pre["Low"].min(), "PML")]
        ref = pre["Close"].iloc[-1]
    else:
        ref = prev["Close"].iloc[-1]

    lo, hi = ref * (1 - cfg.round_range_pct), ref * (1 + cfg.round_range_pct)
    k = math.ceil(lo / cfg.round_step)
    while k * cfg.round_step <= hi:
        raw.append(Level(k * cfg.round_step, "ROUND"))
        k += 1

    raw += [Level(float(p), "MANUAL") for p in cfg.extra_levels]
    return merge_levels(raw, cfg.merge_distance)


def merge_levels(levels: list[Level], distance: float) -> list[Level]:
    out: list[Level] = []
    for lv in sorted(levels, key=lambda x: x.price):
        if out and lv.price - out[-1].price < distance:
            keep = out[-1]
            if _PRIORITY.get(lv.label, 0) > _PRIORITY.get(keep.label, 0):
                out[-1] = Level(round(lv.price, 2), f"{lv.label}/{keep.label}")
            else:
                out[-1] = Level(keep.price, f"{keep.label}/{lv.label}")
        else:
            out.append(Level(round(float(lv.price), 2), lv.label))
    return out
