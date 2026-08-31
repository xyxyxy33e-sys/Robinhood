#!/usr/bin/env python3
"""Evaluate §1.3 legs, base tape and the chase guard from a raw
get_equity_historicals payload.

PROCEDURAL GUARD (added 2026-08-26 after the THIRD truncated-pull error).
Five occurrences in three sessions: 8/25 16:00:00Z, 8/26 14:20:00Z,
8/26 17:00:00Z, 8/27 14:00:00Z, 8/27 15:35:00Z — each silently breaking
VWAP, the session high/low and the baseline median. Notes did not stop
it and neither did "copy the line verbatim". So there are now two
independent controls, one upstream and one here:

  UPSTREAM (runbooks/entry.md): pull with start_time <date>T00:00:00Z.
  bounds=regular clamps the response to the 13:30Z open anyway, so
  midnight gives a 13.5-hour margin and no plausible typo can land
  after the open. Verified 2026-08-27.

  HERE: this script REFUSES to evaluate unless the first bar of every
  symbol is the session open. It also takes the
pull payload verbatim, which removes the hand-transcription step that
was its own error source.

Usage:  python3 tools/eval_entry.py <payload.json> <prev_closes.json> <dirs.json>
        prev_closes/dirs e.g. '{"ANF":108.90}' '{"ANF":"call"}'
"""
import json, statistics, sys

SESSION_OPEN = "13:30:00Z"          # 09:30 ET, regular session
BASELINE_BARS = 6                   # late_entry_baseline_bars
BASELINE_SKIP_OPEN = 3              # late_entry_baseline_skip_open_bars
# §1.3's volume leg is median(previous BASELINE_BARS bars, skipping the session's
# first BASELINE_SKIP_OPEN). That set is not complete until bar 10, so a ratio
# computed before then is NOT the metric the rule defines. Found 2026-08-27 at
# bar 4: the guard let the script run and emit a nan ratio that read like a real
# evaluation. Emitting a confident-looking number from insufficient data is the
# exact failure this file exists to prevent, so it is now refused explicitly.
MIN_BARS = BASELINE_SKIP_OPEN + BASELINE_BARS + 1   # = 10

def load(arg):
    return json.loads(arg) if arg.strip().startswith("{") else json.load(open(arg))

def guard(results):
    """Refuse a truncated or malformed series. Raises SystemExit on failure."""
    problems = []
    for r in results:
        bars = r.get("bars") or []
        sym = r.get("symbol", "?")
        if not bars:
            problems.append(f"{sym}: no bars"); continue
        first = bars[0]["begins_at"]
        if not first.endswith(SESSION_OPEN):
            problems.append(
                f"{sym}: first bar is {first}, expected the session open "
                f"(...T{SESSION_OPEN}). TRUNCATED PULL — re-pull with "
                f"start_time=<date>T13:30:00Z before evaluating anything.")
        if len(bars) < MIN_BARS:
            have = max(0, len(bars) - 1 - BASELINE_SKIP_OPEN)
            problems.append(
                f"{sym}: {len(bars)} bars — §1.3 needs {MIN_BARS} "
                f"(baseline is {BASELINE_BARS} bars skipping the session's first "
                f"{BASELINE_SKIP_OPEN}; only {have} of {BASELINE_BARS} available). "
                f"NOT a data error — the legs are undefined this early. Log the "
                f"refusal; do not compute a partial-baseline ratio.")
    if problems:
        print("REFUSING TO EVALUATE — pull failed the session-start guard:\n",
              file=sys.stderr)
        for p in problems:
            print(f"  * {p}", file=sys.stderr)
        raise SystemExit(2)

def evaluate(r, prev, direction, cfg):
    """Evaluate a raw get_equity_historicals result. Thin adapter over
    evaluate_ohlcv, which holds the actual rule."""
    b = [(float(x["open_price"]), float(x["high_price"]), float(x["low_price"]),
          float(x["close_price"]), int(x["volume"])) for x in r["bars"]]
    d = evaluate_ohlcv(b, prev, direction, cfg)
    d["symbol"] = r["symbol"]
    return d


def evaluate_ohlcv(b, prev, direction, cfg):
    """THE rule. b is a list of (open, high, low, close, volume) tuples for the
    session so far; the LAST tuple is the bar being judged.

    This function is the single source of truth for §1.3. The backtest
    (tools/backtest_legs.py) imports it rather than reimplementing it. It used
    to reimplement it, and the two drifted apart badly — see that file's header.
    Anything added here must be added to config.yaml, not hard-coded."""
    n = len(b)
    op, last = b[0][0], b[n-1][3]
    day = (last - prev) / prev * 100
    vwap = sum(((h+l+c)/3)*v for o, h, l, c, v in b) / sum(x[4] for x in b)
    hi = max(x[1] for x in b); lo = min(x[2] for x in b)
    call = direction == "call"

    magnitude = abs(day) >= cfg["min_day_change_pct"]
    beyond_open = last > op if call else last < op
    beyond_vwap = last > vwap if call else last < vwap
    gap_fade = (call and last <= prev) or (not call and last >= prev)
    base = magnitude and beyond_open and beyond_vwap and not gap_fade

    # baseline: previous 6 bars, skipping the session's first 3
    window = [b[i][4] for i in range(3, n-1)][-6:]
    med = statistics.median(window) if window else float("nan")
    vr = b[n-1][4] / med if window else float("nan")

    streak = 0
    for i in range(n-1, -1, -1):
        o, h, l, c, v = b[i]
        if (call and c > o) or (not call and c < o):
            streak += 1
        else:
            break

    o, h, l, c, v = b[n-1]
    gate_a = c > o if call else c < o
    prev_hi = max(x[1] for x in b[:n-1]); prev_lo = min(x[2] for x in b[:n-1])
    if call:
        new_extreme = h > prev_hi; pullback = l > b[n-2][2]; seq = h >= hi
        guard_pct = (hi - last) / hi * 100
        guard_pct_prior = (prev_hi - last) / prev_hi * 100
    else:
        new_extreme = l < prev_lo; pullback = h < b[n-2][1]; seq = l <= lo
        guard_pct = (last - lo) / lo * 100
        guard_pct_prior = (last - prev_lo) / prev_lo * 100
    gate_b = new_extreme or pullback

    # ---- STRUCTURAL CONFLICT DETECTOR (added 2026-08-28) -------------------
    # `seq` requires this bar to set the session extreme. `guard_pct` measures
    # distance FROM the session extreme. When seq holds, the session extreme IS
    # this bar's extreme, so guard_pct collapses to the bar's own high-to-close
    # giveback and can only clear a 1.0% threshold if the bar closes >1% off its
    # own high — which gate_a (close beyond open) and a momentum entry make
    # essentially impossible.
    #
    # This is not a tuning observation. Measured over the whole 58 name-day
    # corpus (tools/backtest_legs.py), the rule produced 14 qualifications and
    # the guard blocked 14 of 14; guard_pct equalled the bar's own giveback in
    # every case to three decimals, and the largest value seen was 0.459%
    # against a 1.0% threshold. Re-referencing the guard to the PRIOR bars'
    # extreme (guard_pct_prior) does not help: it still blocks 14 of 14,
    # because a bar that sets a new extreme is by construction at or beyond the
    # prior one.
    #
    # So `seq` and a non-zero chase guard are mutually exclusive by
    # construction, at any threshold. One of them has to go; that is an owner
    # decision, not something to quietly tune. Flagged here rather than left as
    # a comment because notes have not held this week and downstream guards have.
    guard_structural_conflict = seq and guard_pct < cfg["chase_guard_all_session_pct"]

    # `seq` also makes gate_b's pullback branch unreachable: seq implies
    # h >= max(prev_hi, h) >= prev_hi, i.e. new_extreme. gate_b therefore
    # never decides anything while seq is required.
    gate_b_pullback_is_dead_code = seq and pullback and not new_extreme

    legs = (vr >= cfg["late_entry_min_volume_ratio"]
            and streak >= cfg["late_entry_min_bars"]
            and gate_a and gate_b and seq)
    return dict(direction=direction, bars=n, last=last,
                day=day, vwap=vwap, hi=hi, lo=lo, open=op, base=base,
                magnitude=magnitude, beyond_open=beyond_open,
                beyond_vwap=beyond_vwap, gap_fade=gap_fade, vr=vr, median=med,
                bar_volume=v, streak=streak, gate_a=gate_a, gate_b=gate_b,
                new_extreme=new_extreme, pullback=pullback, seq=seq,
                qualified=base and legs, guard_pct=guard_pct,
                guard_pct_prior=guard_pct_prior,
                guard_structural_conflict=guard_structural_conflict,
                gate_b_pullback_is_dead_code=gate_b_pullback_is_dead_code,
                guard_blocks=guard_pct < cfg["chase_guard_all_session_pct"])

def main():
    payload = load(sys.argv[1])
    prev_closes = load(sys.argv[2])
    dirs = load(sys.argv[3])
    cfg = dict(min_day_change_pct=2.0, late_entry_min_volume_ratio=1.5,
               late_entry_min_bars=3, chase_guard_all_session_pct=1.0)

    results = payload["data"]["results"] if "data" in payload else payload["results"]
    guard(results)
    print(f"session-start guard PASSED — all {len(results)} symbols begin at "
          f"...T{SESSION_OPEN}\n")

    for r in results:
        sym = r["symbol"]
        if sym not in prev_closes or sym not in dirs:
            print(f"{sym}: skipped, no prev_close/direction supplied"); continue
        e = evaluate(r, prev_closes[sym], dirs[sym], cfg)
        flag = "*** FULL §1.3 QUALIFICATION ***" if e["qualified"] else ""
        print(f"{e['symbol']:5s} {e['direction']:4s} bar {e['bars']:2d}  "
              f"day {e['day']:+7.2f}%  last {e['last']:9.3f}  vwap {e['vwap']:9.3f} {flag}")
        print(f"      base={e['base']}  (mag={e['magnitude']} beyondOpen="
              f"{e['beyond_open']} beyondVWAP={e['beyond_vwap']} "
              f"noGapFade={not e['gap_fade']})")
        print(f"      vol={e['vr']:.4f} ({e['bar_volume']:,} / med {e['median']:,.1f})"
              f"  streak={e['streak']}  a={e['gate_a']}  b={e['gate_b']}"
              f"(ext={e['new_extreme']} pull={e['pullback']})  seq={e['seq']}")
        print(f"      guard {e['guard_pct']:.3f}% -> "
              f"{'BLOCK' if e['guard_blocks'] else 'CLEAR'}"
              f"   (vs prior-bar extreme {e['guard_pct_prior']:+.3f}%)"
              f"   [open {e['open']:.3f} hi {e['hi']:.3f} lo {e['lo']:.3f}]")
        if e["guard_structural_conflict"]:
            print("      !! STRUCTURAL CONFLICT: this bar set the session "
                  "extreme (seq), so the chase guard is measuring the bar's "
                  "own\n         giveback, not chase. It cannot clear at any "
                  "sane threshold. The signal is blocked by construction,\n"
                  "         not by market conditions. See tools/eval_entry.py "
                  "and journal 2026-08-28.")

if __name__ == "__main__":
    main()
