# Runbook: One-day reversal — forward paper validation (week of 2026-08-31)

> ## ⛔ PREMISE NOT SUPPORTED — DO NOT RUN THIS PROTOCOL (2026-08-28)
> The effect this runbook was written to validate **does not survive correct
> measurement.** It was found with two compounding errors: 2,127 signal legs were
> pooled as independent when they sit in only 430 trading days (~4.95 per day), and
> they were benchmarked against the all-period average rather than against what other
> stocks did *the same day*. Signal days cluster on market-wide selloffs, so the
> original number was measuring "the market rises after it falls", not stock selection.
>
> | measurement | excess | t |
> |---|---|---|
> | pooled legs vs all-day baseline (as first reported) | +0.289% | +5.01 |
> | one observation per day, same baseline | +0.101% | +1.69 |
> | one obs per day vs the **same day's** universe | **+0.037%** | **+0.34** |
>
> Open→close, day-clustered and same-day-benchmarked, the excess is **−0.050%
> (t=−0.62)**. No weighting scheme rescues it — equal, drop-weighted, sqrt(drop),
> inverse-volatility, dollar-volume and drop/vol were all tested and all sit inside
> noise. Single-name idiosyncratic drops are *negative* (−0.438%, t=−1.65).
>
> **Do not trade this basket, on paper or otherwise, and do not tune the threshold to
> find a version that works.** The protocol below is kept only as a record of what was
> proposed. Next step is an owner decision — see `journal/2026-08-28.md`.


Replaces the §1.3 momentum entry attempt for the entry phase. The momentum
premise is falsified; see `journal/2026-08-28.md` and `tools/backtest_legs.py --audit`.
This runbook does **not** place orders. `dry_run: true` remains a hard switch and
nothing here overrides it.

## What is being tested

Buying a name the session after it closed weak and hard down beats the
unconditional average by **+0.287%** (n=2,126, t=+5.00), and the excess sits in
the regular session (open→close +0.303%, t=+4.21) rather than the overnight gap
(+0.038%). Stable across 2024/2025/2026 and present with crypto and high-beta
names removed. Measured in-sample on `data/daily/` by `tools/swing_study.py`.

This is the well-known short-term reversal effect. It is not a discovery, and
that is a point in its favour — but in-sample is in-sample. **The purpose of this
week is forward, out-of-sample confirmation on paper.** Nothing is deployed on
the strength of the backtest alone.

## The signal

Prior session closed **≤ −2%** vs the session before it, AND closed **below its
own open**, AND closed **below its own mid-range** `(h+l)/2`.

## Protocol — daily

### 1. Pre-market (~8:00 ET)
```
python3 tools/reversal_screen.py screen <today>
```
Names are read from `data/daily/`, so refresh it first if the prior session is
missing (`get_equity_historicals(interval='day')`, 30-symbol universe, ≤10 per call).

Record the basket in the journal. **A day with no qualifying names is a valid
outcome** — the in-sample base rate is roughly 2,126 signals over 15,600
name-days, so about one name-day in seven. Do not relax `MIN_DROP` to fill a
basket; that is the same failure the momentum track made all month.

### 2. At the open (~9:35 ET)
Record each name's opening print. That is the paper entry. **Take every
qualifying name, equal-weighted, or take none** — per-trade sd is 4.01% against
a +0.436% mean, so a single name is noise and a basket is the signal. Choosing
among the names is not permitted; there is no evidence supporting selection.

### 3. At the close (~15:55 ET)
```
python3 tools/reversal_screen.py score <today>
```
Log the basket's open→close return to `data/reversal_log.csv`
(`date,symbol,signal_date,drop_pct,open,close,ret_pct,basket_n`).

### 4. EOD
Report the basket, the day's return, and the running total against the
in-sample +0.303% expectation. **Report the running number every day even when
it is bad** — especially when it is bad. One week is ~5 observations against a
per-trade sd of 4%; the standard error on a week is larger than the effect. Do
not declare the effect confirmed or dead on this week's data. Say so explicitly
in the report rather than letting a good or bad week read as a verdict.

## Explicitly out of scope this week

- **No orders, paper or real.** `dry_run` stays true; the paper ledger records
  the basket but no `place_*` tool is called for any reason.
- **No options.** +0.30% cannot clear a 6–8% round-trip spread; that is the
  arithmetic that killed the momentum track. If this effect is ever traded it is
  traded as equity.
- **No parameter tuning.** `MIN_DROP` is 2.0 because that is what was measured.
  Anything fitted on this week's five observations is overfitting.
- **No new entry rule for the momentum track.** It stays suspended.
