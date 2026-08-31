# SPMO Core + TQQQ Regime Satellite — strategy specification

Self-contained spec. Derived 2026-08-29 from a study in `research/leverage_ma.md`
(16.5 years of QQQ/QLD/TQQQ data) and the SPMO Mirror Study. Everything needed to
implement it is below; no other context required.

## 1. Idea in one sentence

Hold the SPMO top-15 momentum book unlevered as the core, and express all leverage
through a single TQQQ satellite whose size is set by a market-regime state machine —
so the stock book is never margined and only one position is ever resized.

## 2. Instruments

| sleeve | instrument | role |
|---|---|---|
| core | SPMO top-15 mirror at the fund's own weights | stock selection, always 1x |
| satellite | TQQQ (3x Nasdaq-100) | all leverage, size varies |

No margin. No shorts. No inverse ETFs. Cash is never held — when the satellite is 0%,
the portfolio is 100% core.

## 3. Regime state machine — computed on QQQ, not on the stock book

The signal is a **market** signal. Do not rebuild it on SPMO: SPMO traded off QQQ's
averages beat SPMO traded off its own by 0.10 of Sharpe.

Daily, after the close, on QQQ daily closes:

```
ma50  = 50-day simple moving average of close
ma200 = 200-day simple moving average of close
BUF   = 0.01                       # 1% hysteresis band

# two hysteretic flags; each HOLDS its previous value inside the band
if close > ma50  * (1 + BUF):  above50  = True
elif close < ma50  * (1 - BUF): above50  = False
# else: above50 unchanged

if close > ma200 * (1 + BUF):  above200 = True
elif close < ma200 * (1 - BUF): above200 = False
# else: above200 unchanged

cross = (ma50 > ma200)             # no hysteresis on this one
```

Six reachable states (the other two combinations are arithmetically impossible):

| state | condition | meaning | ~time |
|---|---|---|---|
| **A** | above50 & above200 & cross | established uptrend | 62% |
| **B** | above50 & above200 & !cross | reclaim — price back above both, MAs not yet crossed | 5% |
| **C** | above50 & !above200 | bounce inside a downtrend (dead-cat) | 4% |
| **D** | !above50 & above200 | pullback inside an uptrend | 16% |
| **E** | !above50 & !above200 & cross | breakdown — lost both, MAs still crossed | 6% |
| **F** | !above50 & !above200 & !cross | established downtrend | 7% |

## 4. Allocation rule

```
satellite_weight = {A: 0.35, B: 0.35, C: 0.00, D: 0.20, E: 0.00, F: 0.00}
core_weight      = 1 - satellite_weight
```

Effective market exposure = `1 + 2 x satellite_weight`, i.e. 1.70x in A/B, 1.40x in D,
1.00x in C/E/F.

**Revised 2026-08-29: E dropped from 0.15 to 0.00, D raised from 0.15 to 0.20.**
E is the fast-crash state. It occupies only 4.2% of all days but **37.5% of the 2020
crash and 60.0% of the 2025 tariff drawdown** — because losing both averages before the
50 has crossed the 200 is exactly what a fast decline looks like. (The slow 2022 bear is
dominated by F instead, at 46.5%.) Zeroing E improved every measure at once: Sharpe
0.91 → 0.94, max drawdown −41.0% → −40.7%, worst 12 months −23.5% → −22.0%, 2022 −19.1%
→ −17.9%, and the recent-half Sharpe 0.77 → 0.81, while CAGR *rose* 27.2% → 27.4%.
Of the two changes, zeroing E is the well-supported one — it has an independent
mechanistic reason and improves both halves of the sample. Raising D 15→20 is a smaller
tuning call made on the full sample; D = 0.15 is a defensible alternative costing about
0.5pp of CAGR.

**The portfolio never de-risks below 1x.** In the weak states the satellite goes to
zero and the book is 100% SPMO — still fully invested. This is deliberate: measured
forward 21-day returns are HIGHEST in the weakest states (F +10.73%, E +8.66%) and
LOWEST in the strongest (A +2.71%). The correct response to a weak tape is to stop
adding leverage, not to sell equity.

## 5. Operating procedure

1. After each close, recompute the state from QQQ.
2. If the state's target satellite weight differs from the current weight, rebalance
   to target at the next open (or next close — tested both, no material difference).
3. Otherwise do nothing. Let both sleeves drift between changes; do NOT rebalance
   daily — daily rebalancing destroys the benefit and multiplies turnover.
4. The core follows the SPMO mirror's own rules independently; this overlay does not
   change which stocks are held or their weights.

Expected turnover: **~8 rebalances per year**, one instrument each.

## 6. Measured results

2015-10-01 → 2026-08-27 (10.9 years), price-only, 10bp round-trip costs, T-bill
risk-free rate.

| | CAGR | Max DD | Vol | Sharpe | months underwater |
|---|---|---|---|---|---|
| **This strategy (35% satellite)** | **27.2%** | **−41.0%** | 28.4% | **0.91** | **19.7** |
| SPMO buy-and-hold (1x) | 17.7% | −31.3% | 20.6% | 0.78 | 25.2 |
| QQQ buy-and-hold (1x) | 19.7% | −35.6% | 22.2% | 0.82 | 24.7 |
| QQQ regime ladder alone | 27.7% | −35.3% | 30.6% | 0.88 | 18.2 |
| Same satellite held FLAT at 35% | 28.9% | −47.9% | 34.8% | 0.84 | 26.2 |

The last row is the control: regime-sizing the satellite rather than holding it flat
is worth **+0.07 Sharpe, 7pp of drawdown, and 6.5 months underwater.**

Variants if a different risk level is wanted: 25% max satellite → 24.5% CAGR / −38.1%
/ 0.89; 50% max → 31.4% CAGR / −45.9% / 0.93.

## 7. Known limitations — read before trusting this

1. **Crash-contingent.** Every result of this shape wins in crash years and loses in
   calm ones. The related pure-index study beat buy-and-hold in only 4 of 17 years,
   with 2022 alone carrying the edge. Expect to underperform in quiet markets.
2. **The 1% buffer is the fragile parameter.** Sharpe by buffer: 0% → 0.79, 0.75% →
   0.88, 1.0% → 0.88, 1.25% → 0.87, 2% → 0.81. There is a genuine plateau at
   0.75–1.25% and the 2010-2019 search period independently selects 1.00%, so it is
   not fitted to the test period — but do not use a buffer below ~0.5%. A narrow band
   is worse than none (0.25% scores 0.78 against 0.80 at 0%): it adds lag without
   suppressing whipsaw. QQQ's daily sigma is ~1.3%, so the band must be comparable to
   a typical day's move to filter anything.
3. **Price-only returns.** SPMO holds ~2%-yielding names, TQQQ yields nothing, so the
   core's contribution is understated by roughly 1.5%/yr and the satellite's is not.
   **Tested 2026-08-29: this does NOT reorder the variants.** Adding 0/1/1.5/2% a year to
   the SPMO sleeve alone gives 25%-satellite Sharpe 0.89/0.93/0.94/0.96 against
   35%-satellite 0.91/0.94/0.95/0.97 — the 35% variant leads at every level. The lighter
   variant gains marginally more from dividends (+2.1pp of CAGR at 2% versus +2.0pp) but
   nowhere near enough to close a 2.7pp CAGR gap. An earlier version of this spec said the
   ordering might reverse; it does not.
4. **Small effective sample.** ~3 independent drawdown events in the window. Sixteen
   years sounds like a lot; for a strategy whose value is crash behaviour, it is not.
5. **On the pure-index version, the 2010-2019 search period still ranked plain
   buy-and-hold highest.** The decision to time at all is not supported by the earlier
   half of the data — only by the later, more crash-heavy half.
6. **Drawdown is deeper than either component** (−41.0% vs −31.3% core / −35.3%
   ladder). This strategy shortens time underwater; it does not reduce the worst point.

## 8. What was tested and rejected

- **Margining the 15 stocks** instead of using a satellite: Sharpe 0.79 vs 0.78 for
  unlevered SPMO. Retail borrowing at rf+3% eats the entire benefit.
- **Conviction-scaled leverage** (exposure proportional to a signal strength score):
  rejected four independent ways — such scores are inverted, allocating most when
  forward returns are lowest.
- **Going to cash in weak states** instead of holding the core: worse on every metric
  (Sharpe 0.81 vs 0.88, 30.9 months underwater vs 19.0).
- **50dma-only or 100dma-only breakers**: 50dma runs 5.6–16.9 rebalances/yr with
  32.9 months longest drawdown; 200dma runs 1.7–3.5/yr with 18.0. 100dma is worse
  than both.
- **Golden/death cross (50dma vs 200dma) as the sole state**: ~20pp deeper drawdowns,
  and high search Sharpe with low holdout Sharpe.
- **Overweighting state C** (the dead-cat bounce): deepens max drawdown ~7pp. C is the
  only state with a negative mean forward return (−1.97%).
