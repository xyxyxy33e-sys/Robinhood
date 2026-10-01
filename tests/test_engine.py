from datetime import date

import pandas as pd

from scalper.config import Config
from scalper.engine import Engine
from scalper.levels import Level, compute_levels, merge_levels
from scalper.pricing import bs_price


def feed(eng, start, rows):
    ts = pd.Timestamp(start, tz="America/New_York")
    for i, (o, h, l, c) in enumerate(rows):
        eng.on_bar(ts + pd.Timedelta(minutes=i), o, h, l, c)


def test_bs_put_call_parity_and_expiry():
    c = bs_price(500, 500, 120, 0.15, "C", r=0)
    p = bs_price(500, 500, 120, 0.15, "P", r=0)
    assert abs(c - p) < 1e-9 and c > 0
    assert bs_price(502, 500, 0, 0.15, "C") == 2.0


def test_merge_prefers_stronger_label():
    out = merge_levels([Level(500.0, "ROUND"), Level(500.1, "PDH"), Level(503, "PDL")], 0.25)
    assert [l.price for l in out] == [500.1, 503.0]
    assert out[0].label.startswith("PDH")


def test_levels_use_only_preopen_data():
    idx = pd.date_range("2026-09-29 09:30", "2026-09-29 15:59", freq="1min", tz="America/New_York")
    prev = pd.DataFrame({"Open": 500.0, "High": 501.0, "Low": 499.0, "Close": 500.0, "Volume": 1}, index=idx)
    pre_idx = pd.date_range("2026-09-30 08:00", "2026-09-30 10:00", freq="1min", tz="America/New_York")
    today = pd.DataFrame({"Open": 502.0, "High": 502.5, "Low": 501.5, "Close": 502.0, "Volume": 1}, index=pre_idx)
    today.loc["2026-09-30 09:45", ["High", "Low"]] = [520.0, 480.0]  # after the open: must be ignored
    lv = {l.label.split("/")[0]: l.price for l in compute_levels(pd.concat([prev, today]), date(2026, 9, 30), Config())}
    assert lv["PDH"] == 501.0 and lv["PDL"] == 499.0 and lv["PMH"] == 502.5 and lv["PML"] == 501.5


def test_support_bounce_buys_call_and_hits_target():
    eng = Engine(Config(), [Level(500.0, "PDL")])
    feed(eng, "2026-09-30 09:40", [
        (501.0, 501.1, 500.6, 500.7),  # approaching from above
        (500.7, 500.8, 499.95, 500.2),  # tags the level, closes back above (green? no: c<o)
        (500.2, 500.5, 500.1, 500.45),  # green confirm bar -> buy call
    ])
    assert eng.open and eng.open.right == "C" and eng.open.window == "0DTE"
    feed(eng, "2026-09-30 09:43", [(500.45, 501.6, 500.4, 501.5)])
    tr = eng.trades[0]
    assert tr.exit_reason == "target" and tr.pnl > 0


def test_resistance_rejection_buys_put_and_stops_out_on_break():
    eng = Engine(Config(), [Level(500.0, "PDH")])
    feed(eng, "2026-09-30 13:10", [
        (499.3, 499.5, 499.2, 499.4),
        (499.4, 500.05, 499.3, 499.6),
        (499.6, 499.7, 499.5, 499.55),  # red bar closing below level -> buy put
    ])
    assert eng.open and eng.open.right == "P" and eng.open.window == "3DTE"
    assert (eng.open.expiry - date(2026, 9, 30)).days >= 3
    feed(eng, "2026-09-30 13:13", [(499.6, 501.5, 499.6, 501.4)])
    assert eng.trades[0].pnl < 0 and eng.trades[0].exit_reason in ("stop", "level broke")


def test_no_entries_outside_windows_or_through_broken_level():
    eng = Engine(Config(), [Level(500.0, "PDL")])
    feed(eng, "2026-09-30 12:00", [(501, 501.1, 500.6, 500.7), (500.7, 500.8, 499.95, 500.2), (500.2, 500.5, 500.1, 500.45)])
    assert not eng.trades  # lunch: no trades
    eng = Engine(Config(), [Level(500.0, "PDL")])
    feed(eng, "2026-09-30 10:00", [(501, 501.1, 500.6, 500.7), (500.7, 500.8, 499.0, 499.2), (499.2, 500.5, 499.1, 500.4)])
    assert not eng.trades  # pierced too far: level broken


def test_daily_loss_limit_halts():
    cfg = Config(max_losses_per_day=1)
    eng = Engine(cfg, [Level(500.0, "PDL"), Level(495.0, "ROUND")])
    feed(eng, "2026-09-30 09:40", [
        (501.0, 501.1, 500.6, 500.7), (500.7, 500.8, 499.95, 500.2), (500.2, 500.5, 500.1, 500.45),
        (500.4, 500.4, 497.0, 497.2),  # stop
    ])
    assert eng.halted
    feed(eng, "2026-09-30 09:44", [(496.0, 496.1, 495.6, 495.7), (495.7, 495.8, 494.95, 495.2), (495.2, 495.5, 495.1, 495.45)])
    assert len(eng.trades) == 1
