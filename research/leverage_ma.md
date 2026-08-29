# Constant leverage + a moving-average circuit breaker

**Question:** does holding a *fixed* leverage target on the Nasdaq, and stepping aside to
T-bills when a moving-average circuit breaker trips, beat simply owning QQQ? The owner
asked one thing specifically: **is the 50dma the right breaker, or the 200dma?**

---

## The bar, answered in the first line

**On the period you could actually have chosen a rule from — 2010-02-11 to 2019-12-31 —
nothing beat unleveraged QQQ buy-and-hold on Sharpe except *not filtering at all*.**
Fifteen of the 105 grid cells cleared QQQ B&H's search Sharpe of **0.98**, and all fifteen
are the `bh` (no-breaker) cells. **Every single circuit-breaker rule, at every leverage
level, at every buffer width, lost to QQQ buy-and-hold on the search period.** The best
filtering config managed **0.86** (`L2.0_fast_out_b1`); the 200dma family, the best-behaved
of them, managed **0.59–0.74**.

On the 2020+ holdout the picture inverts — 68 of 105 cells beat QQQ B&H's **0.74**, and the
200dma family reaches **0.90–0.96** — but **that inversion was not selectable in advance**,
and the top holdout performer turns out to be an artifact (§6). This is the sixth negative
result in this repo, and it is negative for the same structural reason as the fifth: *a
crash filter can only be validated on crashes, and the period you get to fit on doesn't
have any.*

**Recommendation: none of these.** See §10.

---

## 1. What was tested

Constant leverage when invested, cash when the breaker trips. **No conviction scaling and
no shorts** — both are ruled out by `research/kairos_five_factor.md`, which found the
conviction score *inverted* at the daily horizon (four independent confirmations) and the
short side worse than cash (SQQQ −4.43% while QQQ fell −5.21%). Exposure here is therefore
**fixed when on**.

| Dimension | Values |
|---|---|
| Base leverage **L** | 1.0, 1.5, 2.0, 2.5, 3.0 |
| Route to L | **lowest-multiple ladder** — L≤1: QQQ+cash; 1<L≤2: QQQ/QLD; 2<L≤3: QLD/TQQQ. Rebalanced **only on a breaker flip**, never daily |
| Breaker rule | `bh` (no filter), `ma50`, `ma100`, `ma200`, `ma50_and_200`, `fast_out` (exit on 50dma break, re-enter above 200dma), `slow_out` (exit on 200dma break, re-enter above 50dma) |
| Buffer band | 0%, 1%, 2% — enter above `ma·(1+b)`, exit below `ma·(1−b)`, otherwise **hold** the prior state |

**5 × 7 × 3 = 105 grid cells.** The fifteen `bh` cells consult no MA, so the buffer is
inert for them: **95 configurations are distinct.**

> **Multiple testing, stated up front.** The best of 95 is expected to look good by chance.
> The full grid is printed below, not just the winners, and **no configuration is
> recommended because it topped a table.** The load-bearing result is §5 — what the search
> period would have selected *in advance*, and how that selection then behaved.

## 2. Method

- **Window** 2010-02-11 → 2026-08-27, **4,160 trading days**. Search = **2,488 days** to
  2019-12-31; holdout = **1,672 days** from 2020-01-02, opened once with everything frozen.
- **No lookahead.** The breaker is computed from day *t*'s close and acted on at day *t+1*'s
  **open** (primary) or as a same-day **MOC** (secondary; both reported, §8). Two assertions
  run every time: the state acted on row *i* equals the condition evaluated at row *i−1*'s
  close in **4,158/4,158 rows**, and every rule × buffer is **truncation-invariant** at four
  cut points (**0 mismatches**) — a rule that peeked forward would fail this.
- **Real TQQQ and QLD prices**, never synthetic multiples of QQQ. TQQQ's ~280 pre-inception
  interpolated bars were dropped upstream; the engine asserts its first bar is 2010-02-11.
  QQQ history from 2009-01-02 is loaded **only** to warm the 200dma, and is never traded.
- **Position-based accounting.** The engine holds *shares* and lets weights drift between
  flips. This matters because the prior study established that leveraged-ETF decay is an
  artifact of *not* rebalancing: with daily rebalancing, 2x via TQQQ+cash and 2x via QLD
  differ by 0.16%/yr (noise), while between signal flips the lower-multiple route wins by
  ~0.8–0.9% per 126-day hold. This strategy holds, so the ladder is used.
- **Costs** swept **0/5/10/20bp round trip**, charged as bps/2 on each leg's notional and
  applied to actual turnover. Base 10bp.
- **Risk-free rate** DGS3MO, forward-filled across FRED's ~200 holiday gaps; used both for
  cash accrual and as the Sharpe denominator's benchmark.
- **Price-only returns, no dividends** — on the strategies *and* on the benchmarks. QQQ's
  ~0.5%/yr yield is missing from the QQQ B&H bar too, which biases **in favour of** the
  strategies and against the benchmark they must beat.

> **The periods are not equivalent, and this conditions everything below.** 2010–2019 is an
> almost uninterrupted Nasdaq bull market; a crash filter has nearly nothing to prove there
> and will tend to look useless or actively harmful. The holdout contains the 2020 COVID
> crash, the 2022 bear and the 2025 drawdown — essentially *all* of the stress this strategy
> exists to handle. A good holdout number is therefore partly luck about which period got
> which stress, and a weak search number is not by itself damning. Both are shown.

## 3. Benchmarks

| Period | | CAGR | Vol | **Sharpe** | max DD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| **SEARCH** | QQQ B&H | 17.40% | 17.23% | **0.98** | −23.16% | 0.75 |
| | QLD B&H | 34.13% | 34.18% | 1.01 | −42.46% | 0.80 |
| | TQQQ B&H | 48.65% | 50.98% | 1.02 | −58.08% | 0.84 |
| | SPY B&H | 11.69% | 14.68% | 0.79 | −20.18% | 0.58 |
| **HOLDOUT** | QQQ B&H | 19.92% | 24.94% | **0.74** | −35.62% | 0.56 |
| | QLD B&H | 30.38% | 49.92% | 0.73 | −63.79% | 0.48 |
| | TQQQ B&H | 32.48% | 73.83% | 0.72 | −81.75% | 0.40 |
| | SPY B&H | 13.92% | 20.22% | 0.60 | −34.10% | 0.41 |
| **FULL** | QQQ B&H | 18.52% | 20.68% | 0.85 | −35.62% | 0.52 |
| | QLD B&H | 32.86% | 41.23% | 0.86 | −63.79% | 0.52 |
| | TQQQ B&H | 42.33% | 61.20% | 0.86 | −81.75% | 0.52 |
| | SPY B&H | 12.64% | 17.12% | 0.69 | −34.10% | 0.37 |

These reproduce `kairos_five_factor.md` §5 exactly — an independent re-derivation from the
same cached prices through a freshly written engine, which is worth having as a cross-check.

**The reframing this study inherits and re-confirms:** over the holdout, **QQQ buy-and-hold
had a better Sharpe than TQQQ buy-and-hold (0.74 vs 0.72) at less than half the drawdown
(−35.62% vs −81.75%)**. Leverage bought return, not risk-adjusted return.

## 4. Does leverage change anything? No.

Holdout Sharpe by rule × leverage, buffer 1%:

| rule | L1.0 | L1.5 | L2.0 | L2.5 | L3.0 | **spread** |
|---|---:|---:|---:|---:|---:|---:|
| `bh` | 0.74 | 0.72 | 0.73 | 0.71 | 0.72 | 0.03 |
| `ma50` | 0.76 | 0.75 | 0.76 | 0.75 | 0.76 | **0.01** |
| `ma100` | 0.67 | 0.66 | 0.66 | 0.66 | 0.66 | **0.01** |
| `ma200` | 0.96 | 0.93 | 0.94 | 0.93 | 0.94 | 0.02 |
| `ma50_and_200` | 0.80 | 0.78 | 0.79 | 0.79 | 0.79 | **0.01** |
| `fast_out` | 0.69 | 0.71 | 0.72 | 0.73 | 0.74 | 0.05 |
| `slow_out` | 1.10 | 1.08 | 1.10 | 1.09 | 1.10 | 0.02 |

**The leverage dimension is inert on a risk-adjusted basis.** Tripling L moves Sharpe by
0.01–0.05. The *breaker* sets the risk-adjusted return; **L only sets how much of it you
take on** — CAGR and drawdown both scale, roughly together. There is no leverage level at
which a bad breaker becomes good, and none at which a good one becomes better.

This collapses the study from two dimensions to one. Everything that matters is the breaker.

## 5. What the search period selects — the load-bearing result

| | Count |
|---|---|
| Grid cells evaluated | **105** (95 distinct) |
| Beating **QQQ B&H** Sharpe (0.98) on SEARCH | **15 of 105** |
| …and all 15 are | **the `bh` cells — i.e. no circuit breaker at all** |
| Circuit-breaker configs beating QQQ B&H on SEARCH | **0 of 90** |
| Beating **TQQQ B&H** Sharpe (1.02) on SEARCH | 3 of 105 (the `L3.0_bh` cells) |
| Beating QQQ B&H Sharpe (0.74) on HOLDOUT | 68 of 105 |

Ranking by the search period and then reading the holdout — the only honest simulation of a
decision made in December 2019:

| Ranked by SEARCH | pick | search Sharpe | → **holdout Sharpe** | holdout CAGR | holdout maxDD |
|---|---|---:|---:|---:|---:|
| Sharpe | `L3.0_bh` | 1.03 | **0.72** | 32.92% | −81.75% |
| CAGR | `L3.0_bh` | 1.03 (49.06%) | **0.72** | 32.92% | −81.75% |
| Calmar | `L3.0_bh` | 0.84 | **0.72** | 32.92% | −81.75% |

**Every ranking criterion selects the same thing: don't filter.** And that selection then
*fails the bar on the holdout too* — 0.72 against QQQ B&H's 0.74. A pre-registered run of
this study delivers a strategy that loses to owning QQQ, twice over.

This is the identical shape the five-factor study found: of 198 configs, the only 6 that
beat B&H on search *were* B&H. Two unrelated signal families, same answer.

## 6. The 50dma question — the owner's direct question

At every leverage level, buffer 0%:

| L | rule | SEARCH CAGR | Sharpe | t/yr | HOLDOUT CAGR | **Sharpe** | maxDD | t/yr | cost drag |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | `bh` | 17.50% | 0.99 | 0.1 | 20.05% | 0.74 | −35.62% | 0.2 | 0.02% |
| 1.0 | **`ma50`** | 5.85% | 0.51 | 16.9 | 14.35% | **0.75** | −17.64% | 15.4 | 1.76% |
| 1.0 | `ma100` | 6.61% | 0.53 | 12.5 | 11.63% | 0.56 | −26.47% | 9.5 | 1.06% |
| 1.0 | **`ma200`** | 8.68% | 0.61 | 7.4 | 19.50% | **0.92** | −23.17% | 3.5 | 0.41% |
| 1.0 | `ma50_and_200` | 3.55% | 0.32 | 17.5 | 13.77% | 0.76 | −17.64% | 14.8 | 1.68% |
| 1.0 | `fast_out` | 4.36% | 0.35 | 49.5 | 12.80% | 0.64 | −25.12% | 45.5 | 5.14% |
| 1.0 | `slow_out` | 10.33% | 0.73 | 10.2 | 23.05% | 1.07 | −18.32% | 14.6 | 1.80% |
| 2.0 | `bh` | 34.37% | 1.02 | 0.1 | 30.66% | 0.73 | −63.79% | 0.2 | 0.02% |
| 2.0 | **`ma50`** | 13.62% | 0.65 | 16.9 | 23.79% | **0.75** | −33.46% | 15.4 | 1.90% |
| 2.0 | `ma100` | 13.20% | 0.60 | 12.5 | 17.53% | 0.56 | −46.64% | 9.5 | 1.12% |
| 2.0 | **`ma200`** | 19.46% | 0.74 | 7.4 | 33.81% | **0.91** | −42.47% | 3.5 | 0.46% |
| 2.0 | `ma50_and_200` | 9.71% | 0.50 | 17.5 | 23.05% | 0.76 | −32.81% | 14.8 | 1.82% |
| 2.0 | `fast_out` | 12.68% | 0.57 | 49.5 | 22.06% | 0.68 | −44.95% | 45.5 | 5.56% |
| 2.0 | `slow_out` | 22.15% | 0.84 | 10.2 | 42.56% | 1.08 | −34.45% | 14.6 | 2.09% |
| 3.0 | `bh` | 49.06% | 1.03 | 0.1 | 32.92% | 0.72 | −81.75% | 0.2 | 0.02% |
| 3.0 | **`ma50`** | 16.26% | 0.60 | 16.9 | 31.36% | **0.76** | −50.15% | 15.4 | 2.02% |
| 3.0 | `ma100` | 17.01% | 0.59 | 12.5 | 20.04% | 0.56 | −61.46% | 9.5 | 1.14% |
| 3.0 | **`ma200`** | 22.87% | 0.69 | 7.4 | 44.64% | **0.91** | −57.73% | 3.5 | 0.50% |
| 3.0 | `ma50_and_200` | 9.07% | 0.41 | 17.5 | 30.82% | 0.77 | −45.82% | 14.8 | 1.93% |
| 3.0 | `fast_out` | 14.83% | 0.54 | 49.5 | 28.94% | 0.71 | −59.72% | 45.5 | 5.87% |
| 3.0 | `slow_out` | 29.12% | 0.81 | 10.2 | 59.54% | 1.09 | −48.14% | 14.6 | 2.33% |

**The 200dma beats the 50dma, decisively and at every leverage level, on every axis that
matters.** Holdout Sharpe **0.90–0.96 vs 0.74–0.76** at buffers 0–1% — and 0.82–0.84
vs 0.74–0.76 at a 2% buffer, so **every one of the fifteen 200dma cells beats every one of
the fifteen 50dma cells**; search Sharpe 0.61–0.74 vs 0.51–0.65;
turnover **3.5 vs 15.4** rebalances/yr; cost drag **0.41–0.50% vs 1.76–2.02%**. The 50dma's
one genuine advantage is a shallower drawdown at low leverage (−17.64% vs −23.17% at L=1.0)
— bought by sitting in cash 30% of the time, which is also why its CAGR is a third of the
200dma's.

**The 100dma is worse than both** (holdout Sharpe 0.56), so this is not a monotone
"longer is better" story. It is specifically the 200dma.

### The 2025 claim does not survive contact with the data

The premise was that in calendar 2025 the 50dma rule on TQQQ returned **+93.80%** against
**+46.06%** for QQQ>200dma. **Neither number reproduces here, and the ordering reverses:**

| rule | 0bp next-open | 0bp same-close | 10bp next-open | 10bp same-close | **open−close gap** |
|---|---:|---:|---:|---:|---:|
| `bh` (=TQQQ) | 30.94% | 33.25% | 30.87% | 33.18% | −2.31% |
| **`ma50` b0** | **27.65%** | **45.70%** | 26.57% | 44.47% | **−17.89%** |
| `ma50` b1 | 35.94% | 37.73% | 35.33% | 37.11% | −1.79% |
| `ma200` b0 | 29.76% | 34.14% | 29.56% | 33.94% | −4.38% |
| `ma50_and_200` b0 | 12.41% | 25.26% | 11.46% | 24.20% | −12.74% |
| `slow_out` b0 | 33.04% | 57.41% | 32.45% | 56.70% | −24.25% |
| `fast_out` b0 | 45.10% | 23.54% | 42.73% | 21.51% | **+21.21%** |

TQQQ buy-and-hold returned **+33.25%** in 2025. The 50dma rule returned **+27.65%** —
**it lost to doing nothing**, and to the 200dma's +29.76%. Nothing tested reaches +93.80%.

But the more damning column is the last one. **The 50dma rule's own 2025 answer moves from
+27.65% to +45.70% purely on whether you fill at today's close or tomorrow's open.** An
18-point swing inside a single year, from an assumption that is not part of the strategy.
`fast_out` swings 21 points and flips sign. A rule that fragile does not have a 16-year edge
to defend; it has a fill assumption. The 8 separate runs the 50dma generated in 2025 are
exactly the mechanism — every extra round trip is another chance for the two fill
conventions to diverge.

### `slow_out`'s Sharpe of 1.10 is an artifact, not a finding

The asymmetric "slow out, fast in" rule tops the holdout at **1.06–1.10** Sharpe. It should
not be believed, for a reason visible in the state machine rather than the returns.

| rule | buf | flips | invested runs | **median run** | 1-day runs | days invested |
|---|---:|---:|---:|---:|---:|---:|
| `ma200` | 1% | 46 | 24 | **56 days** | 2 | 3,462 |
| `slow_out` | 0% | 196 | 99 | **1 day** | **67** | 3,496 |
| `slow_out` | 1% | 138 | 70 | **1 day** | 46 | 3,516 |
| `fast_out` | 0% | 791 | 396 | **1 day** | **287** | 3,139 |

**`slow_out` is not holding a position; it is flickering,** and by construction. After it
exits below the 200dma, it re-enters on a 50dma cross *while still below the 200dma* — at
which point its own exit test is already true, so it exits again on the next bar. The rule
contradicts itself in exactly the region it was designed for.

Those flicker days are where its edge lives, and the contribution **flips sign with the
buffer**:

| buffer | above-200dma days | cum TQQQ | below-200dma *flicker* days | **cum TQQQ** |
|---:|---:|---:|---:|---:|
| 0% | 3,420 | 159.72× | 75 | **2.156×** |
| 1% | 3,424 | 161.02× | 91 | **1.359×** |
| 2% | 3,419 | 121.45× | 104 | **0.970×** |

**Seventy-five isolated one-day bets more than doubled the money at buffer 0%, and lost
money at buffer 2%.** A one-percentage-point change in an arbitrary parameter reverses the
sign of the entire effect. That is a draw, not a mechanism — and it is a coherent draw: the
prior study documented that leveraged Nasdaq rebounds violently off crash lows, so a rule
that accidentally samples single days near bottoms will look brilliant in a period
containing two crashes.

Two counterfactuals confirm it. Forbidding sub-200dma entries costs ~9pp of holdout CAGR and
0.10 Sharpe (`L3.0_slow_out_gated_b0`: 50.27% / 0.99 vs 59.54% / 1.09). And forcing a
minimum hold:

| rule | min hold | search CAGR | search Sharpe | holdout CAGR | **holdout Sharpe** | t/yr |
|---|---:|---:|---:|---:|---:|---:|
| `slow_out` | 1d | 29.48% | 0.82 | 61.58% | **1.10** | 12.8 |
| `slow_out` | 3d | 31.98% | **0.86** | 49.97% | **0.96** | 2.9 |
| `slow_out` | 5d | 32.95% | **0.88** | 52.70% | 0.99 | 2.6 |
| `slow_out` | 10d | 33.10% | 0.87 | 45.07% | 0.90 | 3.5 |
| `ma200` | 1d | 24.33% | 0.72 | 47.24% | 0.94 | 1.7 |
| `ma200` | 3d | 25.34% | 0.73 | 42.25% | 0.86 | 1.7 |
| `ma200` | 10d | 29.34% | 0.80 | 44.56% | 0.88 | 1.7 |

**Merely forbidding one-day holds drops `slow_out` from 1.10 to 0.96 while its *search*
Sharpe rises from 0.82 to 0.86.** The flicker helped only on the holdout. That is the
signature of luck. `ma200`, which never flickers, is essentially unmoved.

## 7. Turnover and cost drag

Holdout, L=3.0. Cost drag = CAGR@0bp − CAGR@20bp.

| rule | buf | t/yr | turnover | CAGR@0bp | @10bp | @20bp | **drag** | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `bh` | 0% | 0.2 | 1.0 | 32.93% | 32.92% | 32.91% | **0.02%** | 0.72 |
| `ma50` | 0% | 15.4 | 102.1 | 32.37% | 31.36% | 30.35% | 2.02% | 0.76 |
| `ma50` | 1% | 8.0 | 53.0 | 32.24% | 31.71% | 31.18% | 1.05% | 0.76 |
| `ma50` | 2% | 5.6 | 37.0 | 31.07% | 30.70% | 30.34% | 0.73% | 0.75 |
| `ma100` | 2% | 3.5 | 23.0 | 37.92% | 37.68% | 37.45% | 0.48% | 0.83 |
| **`ma200`** | 0% | 3.5 | 23.0 | 44.89% | 44.64% | 44.39% | 0.50% | 0.91 |
| **`ma200`** | **1%** | **1.7** | **11.0** | 47.36% | **47.24%** | 47.12% | **0.24%** | **0.94** |
| `ma200` | 2% | 1.7 | 11.0 | 38.59% | 38.48% | 38.36% | 0.23% | 0.83 |
| `ma50_and_200` | 0% | 14.8 | 98.0 | 31.79% | 30.82% | 29.86% | 1.93% | 0.77 |
| **`fast_out`** | 0% | **45.5** | **302.2** | 31.91% | 28.94% | 26.04% | **5.87%** | 0.71 |
| `fast_out` | 1% | 30.3 | 201.1 | 33.07% | 31.07% | 29.10% | 3.97% | 0.74 |
| `slow_out` | 1% | 12.8 | 85.0 | 62.62% | 61.58% | 60.55% | 2.07% | 1.10 |

**Costs are not what kills this strategy** — the 200dma family trades 1.7–3.5 times a year
and pays 0.24% even at a punitive 20bp. `fast_out` is the exception and is uninvestable on
turnover alone: **45.5 rebalances/yr bleeding 5.87%/yr**.

**The buffer works and is close to free.** On `ma200` it halves turnover (3.5 → 1.7/yr),
cuts drag from 0.50% to 0.24%, *and raises* CAGR 44.64% → 47.24% and Sharpe 0.91 → 0.94.
This replicates the prior study's finding that a no-trade band improves returns while
cutting trades. Note the 2% buffer then gives it all back (38.48%, 0.83) — the band is
helpful but not monotone, and 1% vs 2% is a 9-point CAGR swing on an arbitrary choice.

## 8. Execution timing

Next-open minus same-close (MOC) CAGR, L=3.0, buffer 0%:

| config | SEARCH | HOLDOUT | FULL |
|---|---:|---:|---:|
| `bh` | +0.42% | −0.49% | +0.24% |
| `ma50` | −4.31% | −1.77% | −3.17% |
| `ma100` | −0.71% | −10.08% | −4.16% |
| `ma200` | −2.52% | +0.02% | −1.40% |
| `ma50_and_200` | −4.35% | −1.36% | −3.10% |
| `fast_out` | −8.06% | +1.85% | −4.08% |
| `slow_out` | −5.14% | +5.36% | −1.15% |

Same-close is the more optimistic convention for almost every rule, by 1–10 points a year —
much larger and less sign-consistent than the five-factor study's ±2%. **Next-open is
reported as primary throughout precisely because it is the conservative, implementable one.**
`ma200` is the least sensitive rule here (−1.40% full-period), which is one more reason it is
the only family worth taking seriously.

## 9. Per-year, drawdown depth and drawdown duration

Fixed shortlist at constant leverage, chosen before ranking, so the 50-vs-200 difference is
visible year by year:

| year | `L3.0_ma50_b1` | `L3.0_ma200_b1` | `L3.0_slow_out_b1` | `L2.0_ma200_b1` | TQQQ B&H | QQQ B&H |
|---|---:|---:|---:|---:|---:|---:|
| 2010 | 59.55% | 24.89% | 63.77% | 30.51% | 78.06% | 24.71% |
| 2011 | −48.59% | −36.92% | −43.40% | −24.90% | −8.05% | 2.52% |
| 2012 | 30.24% | 27.03% | 25.37% | 19.27% | 52.29% | 16.66% |
| 2013 | 74.50% | 119.21% | 119.21% | 70.55% | 139.73% | 35.05% |
| 2014 | 34.26% | 59.14% | 59.14% | 38.44% | 57.04% | 17.38% |
| 2015 | −12.32% | −16.59% | −16.50% | −13.53% | 17.22% | 8.34% |
| 2016 | 4.77% | −7.36% | 9.31% | −3.79% | 11.38% | 5.92% |
| 2017 | 92.37% | 113.72% | 113.72% | 67.97% | 118.06% | 31.47% |
| **2018** | −4.25% | −4.61% | **23.45%** | 0.80% | **−19.90%** | −0.96% |
| 2019 | 47.09% | 51.91% | 27.75% | 35.49% | 133.67% | 37.83% |
| **2020** | 109.64% | 74.18% | **128.43%** | 55.05% | 110.05% | 47.57% |
| 2021 | 9.70% | 80.63% | 80.63% | 53.12% | 82.98% | 26.81% |
| **2022** | **−31.93%** | **−26.35%** | **−16.37%** | **−17.61%** | **−79.20%** | −33.07% |
| 2023 | 101.35% | 125.50% | 161.04% | 81.49% | 193.06% | 53.79% |
| 2024 | 27.40% | 60.30% | 60.30% | 44.97% | 56.07% | 24.84% |
| 2025 | 35.33% | 17.35% | 29.63% | 15.66% | 33.25% | 20.16% |
| 2026 YTD | 9.79% | 27.18% | 23.74% | 21.75% | 39.04% | 17.39% |

**The edge is concentrated in exactly two years and it is entirely crash-avoidance.**
`L3.0_ma200_b1` beats TQQQ B&H in **4 of 17 years** — 2014 (59.14% vs 57.04%), 2018 (−4.61%
vs −19.90%), **2022 (−26.35% vs −79.20%)** and 2024 (60.30% vs 56.07%). It trails in the
other thirteen, several severely: 2010 (−53pp), 2019 (−82pp), 2023 (−68pp), 2021 (−2pp),
2011 (−29pp). **2022 alone is the strategy.** Strip 2022 and there is nothing here.

That is what a crash filter *is*, and it is priced like insurance: it costs return in every
year without a crash. The problem is not that the insurance is bad — it is that you have to
pick the policy in 2019, and in 2019 this policy had spent a decade losing.

### Drawdown depth *and* duration (holdout)

Max drawdown alone hides how long you sit underwater, so both are reported:

| config | max DD | **worst 12m** | **longest DD (months)** | CAGR | Sharpe |
|---|---:|---:|---:|---:|---:|
| `L3.0_ma50_b1` | −47.72% | −34.48% | **32.9** | 31.71% | 0.76 |
| `L3.0_ma200_b1` | −58.64% | −30.50% | 18.0 | 47.24% | 0.94 |
| `L3.0_slow_out_b1` | −48.14% | −32.69% | 14.3 | 61.58% | 1.10 |
| **`L2.0_ma200_b1`** | **−43.16%** | **−20.37%** | **17.8** | 35.41% | 0.94 |
| `L2.0_slow_out_b1` | −34.45% | −22.23% | 14.2 | 43.95% | 1.10 |
| **QQQ B&H** | **−35.62%** | **−35.24%** | **24.7** | 19.92% | 0.74 |
| `L1.5_bh` | −52.88% | −52.31% | 27.1 | 25.98% | 0.72 |
| `L2.0_bh` | −63.79% | −63.20% | 30.0 | 30.66% | 0.73 |
| `L2.5_bh` | −74.08% | −73.40% | 31.2 | 31.82% | 0.71 |
| **TQQQ B&H** | **−81.75%** | **−81.14%** | **36.5** | 32.48% | 0.72 |

Three things worth saying plainly:

1. **The one place a breaker genuinely delivers is duration and worst-12m, not max DD.**
   `L2.0_ma200_b1` cuts the worst rolling year to **−20.37%** against QQQ B&H's **−35.24%**,
   and time underwater to **17.8 months** against **24.7**. That is a real, mechanically
   sensible improvement — you are in T-bills for the worst of it.
2. **But its max drawdown is *deeper* than QQQ's** (−43.16% vs −35.62%). A strategy sold on
   drawdown reduction does not, at 2x, reduce the number the buyer will actually look at.
3. **The 50dma is the worst of all worlds on duration** — 32.9 months underwater, longer
   than QQQ buy-and-hold's 24.7 and nearly TQQQ's 36.5, for a Sharpe of 0.76. It trades
   15.4 times a year to be underwater longer than doing nothing.

## 10. Verdict

**Nothing here should be traded.**

- **Against the bar the owner set** — beat unleveraged QQQ B&H on Sharpe — **the answer on
  the search period is a flat no for every circuit breaker tested** (0 of 90). On the holdout
  the 200dma family clears it comfortably (0.90–0.96 vs 0.74), but a rule you could only have
  found by looking at the holdout is not a rule you had.
- **Between the 50dma and the 200dma, the 200dma wins and it is not close** — better Sharpe
  in every single cell of the grid (0.82–0.96 vs 0.74–0.76 on the
  holdout), a quarter of the turnover (3.5 vs 15.4/yr), a
  quarter of the cost drag, less execution sensitivity, and 15 fewer months underwater. The
  2025 result that motivated the question does not reproduce: the 50dma made **+27.65%** in
  2025 against TQQQ buy-and-hold's **+33.25%**, and swings to **+45.70%** on the fill
  convention alone.
- **The leverage dimension is inert.** Sharpe varies by 0.01–0.05 from L=1.0 to L=3.0.
  Leverage is a decision about how much drawdown to accept, not a source of edge —
  re-confirming the prior study's reframing on an entirely different signal.
- **The best-looking result in the grid is an artifact.** `slow_out`'s 1.10 Sharpe rests on
  ~75 one-day exposures whose contribution flips from 2.156× to 0.970× on a 1pp buffer change,
  and collapses to 0.96 the moment one-day holds are forbidden.
- **The one honest positive:** a 200dma breaker with a 1% buffer materially improves
  *drawdown duration* and *worst-12-month* return (17.8 months / −20.37% at L=2.0, versus
  24.7 months / −35.24% for QQQ B&H), at 1.7 trades a year and 0.24% of cost. If the goal
  were specifically "spend less time underwater", that is the only thing in 95 configurations
  with a defensible claim to it. It still would not have been chosen in 2019, and its max
  drawdown is worse than QQQ's.

`data/leverage/daily_series.csv` exports **`L2.0_ma200_b1`** — chosen on **mechanism and
turnover** (the only family with a stable state machine: median invested run 56 days, 2
one-day runs, 1.7 trades/yr), explicitly **not** on holdout rank. It is the most defensible
thing in the grid to examine closely. It is not a recommendation.

**This is the sixth consecutive negative result in this repo, and the pattern is itself the
finding:** every strategy tested here that tries to time the Nasdaq has failed the same way —
the timing rule's entire value is crash avoidance, crashes are rare, and the sample of
crashes available to fit on is roughly three events. Sixteen years sounds like a lot of data.
For this question it is n≈3.

## 11. Limitations

1. **Multiple testing.** 105 cells, 95 distinct configurations, evaluated on the holdout. The
   best of 95 is expected to look good by chance; §5 is the load-bearing result, not the best
   holdout row.
2. **n ≈ 3.** 2010–2026 contains one secular Nasdaq bull market with three interruptions
   (2018, 2020, 2022, plus a 2025 scare). The entire value of every breaker rests on those.
3. **One market.** QQQ only. Nothing here says whether a 200dma breaker works on other
   indices, and the 2010–2026 Nasdaq is an unusually strong single draw.
4. **No dividends anywhere**, which flatters the strategies relative to QQQ B&H by roughly
   0.5%/yr — the true comparison is slightly *worse* for every rule than shown.
5. **Buffer granularity.** Only 0/1/2% tested, and `ma200`'s CAGR swings 47.24% → 38.48%
   between 1% and 2%. The band is a genuine sensitivity, not a solved parameter.
6. **Same-close variant assumes MOC fills at the official close.** For a pure price rule the
   MA and close are knowable minutes before the bell, so this is defensible, but next-open is
   primary throughout for good reason (§8).
7. **No slippage model beyond the bp sweep**, and no borrow/financing cost beyond what is
   embedded in the real QLD/TQQQ prices.

## 12. Files

| Path | Contents |
|---|---|
| `tools/leverage/backtest.py` | Breaker rules, ladder route, position engine, full grid, all robustness probes. `python3 tools/leverage/backtest.py`, ~3s, standard library only |
| `data/leverage/daily_series.csv` | 4,159-row audit trail for `L2.0_ma200_b1`: date, QQQ close, 50/100/200dma, breaker state (today and the one acted on), target and actual leverage, per-ETF weights, cash weight, trade flag, daily return, equity curve, drawdown |
| `data/kairos/etf/*.csv` | Reused price data (QQQ, QLD, TQQQ, SPY), pulled 2026-08-29 |
| `data/kairos/DGS3MO.csv` | Reused 3-month T-bill rate |
| `research/kairos_five_factor.md` | The prior study this builds on |

## Appendix: the full grid

All 105 cells. Ladder route, next-open execution, 10bp round trip. **Reported in full,
winners and losers together, because reporting only the top rows is how a grid this size
manufactures a result.**

| config | S CAGR | S Sharpe | S maxDD | S Calmar | S t/yr | H CAGR | H Sharpe | H maxDD | H Calmar | H t/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `L1.0_bh_b0` | 17.50% | 0.99 | -23.16% | 0.76 | 0.1 | 20.05% | 0.74 | -35.62% | 0.56 | 0.2 |
| `L1.0_bh_b1` | 17.50% | 0.99 | -23.16% | 0.76 | 0.1 | 20.05% | 0.74 | -35.62% | 0.56 | 0.2 |
| `L1.0_bh_b2` | 17.50% | 0.99 | -23.16% | 0.76 | 0.1 | 20.05% | 0.74 | -35.62% | 0.56 | 0.2 |
| `L1.0_ma50_b0` | 5.85% | 0.51 | -19.01% | 0.31 | 16.9 | 14.35% | 0.75 | -17.64% | 0.81 | 15.4 |
| `L1.0_ma50_b1` | 7.43% | 0.64 | -23.30% | 0.32 | 7.6 | 14.76% | 0.76 | -17.52% | 0.84 | 8.0 |
| `L1.0_ma50_b2` | 5.11% | 0.44 | -22.14% | 0.23 | 5.6 | 14.38% | 0.75 | -17.31% | 0.83 | 5.6 |
| `L1.0_ma100_b0` | 6.61% | 0.53 | -21.65% | 0.31 | 12.5 | 11.63% | 0.56 | -26.47% | 0.44 | 9.5 |
| `L1.0_ma100_b1` | 6.78% | 0.54 | -20.35% | 0.33 | 6.4 | 13.79% | 0.67 | -26.78% | 0.51 | 5.3 |
| `L1.0_ma100_b2` | 6.95% | 0.55 | -20.45% | 0.34 | 3.7 | 17.22% | 0.84 | -19.74% | 0.87 | 3.5 |
| `L1.0_ma200_b0` | 8.68% | 0.61 | -24.46% | 0.35 | 7.4 | 19.50% | 0.92 | -23.17% | 0.84 | 3.5 |
| `L1.0_ma200_b1` | 9.28% | 0.65 | -23.34% | 0.40 | 3.7 | 20.26% | 0.96 | -23.48% | 0.86 | 1.7 |
| `L1.0_ma200_b2` | 8.33% | 0.59 | -30.16% | 0.28 | 2.5 | 17.80% | 0.84 | -23.96% | 0.74 | 1.7 |
| `L1.0_ma50_and_200_b0` | 3.55% | 0.32 | -23.50% | 0.15 | 17.5 | 13.77% | 0.76 | -17.64% | 0.78 | 14.8 |
| `L1.0_ma50_and_200_b1` | 6.55% | 0.58 | -19.82% | 0.33 | 7.4 | 14.54% | 0.80 | -17.52% | 0.83 | 6.8 |
| `L1.0_ma50_and_200_b2` | 3.59% | 0.32 | -21.01% | 0.17 | 5.4 | 14.78% | 0.83 | -17.31% | 0.85 | 4.7 |
| `L1.0_fast_out_b0` | 4.36% | 0.35 | -28.96% | 0.15 | 49.5 | 12.80% | 0.64 | -25.12% | 0.51 | 45.5 |
| `L1.0_fast_out_b1` | 8.62% | 0.68 | -22.22% | 0.39 | 30.9 | 14.06% | 0.69 | -24.17% | 0.58 | 30.3 |
| `L1.0_fast_out_b2` | 7.25% | 0.56 | -24.21% | 0.30 | 17.1 | 14.37% | 0.72 | -20.27% | 0.71 | 22.2 |
| `L1.0_slow_out_b0` | 10.33% | 0.73 | -22.00% | 0.47 | 10.2 | 23.05% | 1.07 | -18.32% | 1.26 | 14.6 |
| `L1.0_slow_out_b1` | 10.59% | 0.74 | -21.58% | 0.49 | 5.6 | 23.75% | 1.10 | -18.32% | 1.30 | 12.8 |
| `L1.0_slow_out_b2` | 10.22% | 0.71 | -24.42% | 0.42 | 3.1 | 19.13% | 0.89 | -22.59% | 0.85 | 8.9 |
| `L1.5_bh_b0` | 28.28% | 1.00 | -38.24% | 0.74 | 0.1 | 25.98% | 0.72 | -52.88% | 0.49 | 0.2 |
| `L1.5_bh_b1` | 28.28% | 1.00 | -38.24% | 0.74 | 0.1 | 25.98% | 0.72 | -52.88% | 0.49 | 0.2 |
| `L1.5_bh_b2` | 28.28% | 1.00 | -38.24% | 0.74 | 0.1 | 25.98% | 0.72 | -52.88% | 0.49 | 0.2 |
| `L1.5_ma50_b0` | 9.90% | 0.60 | -26.62% | 0.37 | 16.9 | 19.41% | 0.74 | -26.17% | 0.74 | 15.4 |
| `L1.5_ma50_b1` | 11.82% | 0.70 | -33.48% | 0.35 | 7.6 | 19.97% | 0.75 | -26.28% | 0.76 | 8.0 |
| `L1.5_ma50_b2` | 8.19% | 0.50 | -32.11% | 0.26 | 5.6 | 19.33% | 0.74 | -26.06% | 0.74 | 5.6 |
| `L1.5_ma100_b0` | 10.16% | 0.58 | -30.61% | 0.33 | 12.5 | 14.84% | 0.55 | -37.29% | 0.40 | 9.5 |
| `L1.5_ma100_b1` | 9.88% | 0.57 | -29.54% | 0.33 | 6.4 | 18.13% | 0.66 | -37.74% | 0.48 | 5.3 |
| `L1.5_ma100_b2` | 10.78% | 0.60 | -29.11% | 0.37 | 3.7 | 23.47% | 0.82 | -28.82% | 0.81 | 3.5 |
| `L1.5_ma200_b0` | 14.48% | 0.70 | -34.80% | 0.42 | 7.4 | 27.39% | 0.90 | -33.44% | 0.82 | 3.5 |
| `L1.5_ma200_b1` | 14.30% | 0.69 | -34.59% | 0.41 | 3.7 | 28.43% | 0.93 | -33.97% | 0.84 | 1.7 |
| `L1.5_ma200_b2` | 12.94% | 0.64 | -43.10% | 0.30 | 2.5 | 24.35% | 0.82 | -34.57% | 0.70 | 1.7 |
| `L1.5_ma50_and_200_b0` | 6.81% | 0.44 | -32.61% | 0.21 | 17.5 | 18.72% | 0.76 | -26.17% | 0.72 | 14.8 |
| `L1.5_ma50_and_200_b1` | 10.36% | 0.64 | -28.89% | 0.36 | 7.4 | 19.76% | 0.78 | -26.28% | 0.75 | 6.8 |
| `L1.5_ma50_and_200_b2` | 5.88% | 0.39 | -30.52% | 0.19 | 5.4 | 20.05% | 0.81 | -25.95% | 0.77 | 4.7 |
| `L1.5_fast_out_b0` | 8.75% | 0.50 | -39.36% | 0.22 | 49.5 | 17.85% | 0.66 | -35.72% | 0.50 | 45.5 |
| `L1.5_fast_out_b1` | 14.93% | 0.80 | -32.18% | 0.46 | 30.9 | 19.42% | 0.71 | -34.55% | 0.56 | 30.3 |
| `L1.5_fast_out_b2` | 13.24% | 0.71 | -28.05% | 0.47 | 17.1 | 19.48% | 0.72 | -29.53% | 0.66 | 22.2 |
| `L1.5_slow_out_b0` | 16.62% | 0.80 | -31.24% | 0.53 | 10.2 | 33.36% | 1.06 | -26.76% | 1.25 | 14.6 |
| `L1.5_slow_out_b1` | 16.04% | 0.76 | -31.93% | 0.50 | 5.6 | 34.33% | 1.08 | -26.76% | 1.28 | 12.8 |
| `L1.5_slow_out_b2` | 15.36% | 0.73 | -35.92% | 0.43 | 3.1 | 26.71% | 0.88 | -33.63% | 0.79 | 8.9 |
| `L2.0_bh_b0` | 34.37% | 1.02 | -42.46% | 0.81 | 0.1 | 30.66% | 0.73 | -63.79% | 0.48 | 0.2 |
| `L2.0_bh_b1` | 34.37% | 1.02 | -42.46% | 0.81 | 0.1 | 30.66% | 0.73 | -63.79% | 0.48 | 0.2 |
| `L2.0_bh_b2` | 34.37% | 1.02 | -42.46% | 0.81 | 0.1 | 30.66% | 0.73 | -63.79% | 0.48 | 0.2 |
| `L2.0_ma50_b0` | 13.62% | 0.65 | -33.51% | 0.41 | 16.9 | 23.79% | 0.75 | -33.46% | 0.71 | 15.4 |
| `L2.0_ma50_b1` | 15.87% | 0.74 | -42.04% | 0.38 | 7.6 | 24.65% | 0.76 | -32.78% | 0.75 | 8.0 |
| `L2.0_ma50_b2` | 10.99% | 0.54 | -40.45% | 0.27 | 5.6 | 23.89% | 0.75 | -34.23% | 0.70 | 5.6 |
| `L2.0_ma100_b0` | 13.20% | 0.60 | -38.64% | 0.34 | 12.5 | 17.53% | 0.56 | -46.64% | 0.38 | 9.5 |
| `L2.0_ma100_b1` | 12.46% | 0.58 | -37.30% | 0.33 | 6.4 | 21.83% | 0.66 | -47.26% | 0.46 | 5.3 |
| `L2.0_ma100_b2` | 14.07% | 0.63 | -36.94% | 0.38 | 3.7 | 29.17% | 0.83 | -36.89% | 0.79 | 3.5 |
| `L2.0_ma200_b0` | 19.46% | 0.74 | -43.20% | 0.45 | 7.4 | 33.81% | 0.91 | -42.47% | 0.80 | 3.5 |
| `L2.0_ma200_b1` | 18.57% | 0.72 | -41.89% | 0.44 | 3.7 | 35.41% | 0.94 | -43.16% | 0.82 | 1.7 |
| `L2.0_ma200_b2` | 16.89% | 0.67 | -51.81% | 0.33 | 2.5 | 29.95% | 0.83 | -43.83% | 0.68 | 1.7 |
| `L2.0_ma50_and_200_b0` | 9.71% | 0.50 | -40.62% | 0.24 | 17.5 | 23.05% | 0.76 | -32.81% | 0.70 | 14.8 |
| `L2.0_ma50_and_200_b1` | 13.86% | 0.67 | -36.65% | 0.38 | 7.4 | 24.58% | 0.79 | -32.78% | 0.75 | 6.8 |
| `L2.0_ma50_and_200_b2` | 7.88% | 0.42 | -38.62% | 0.20 | 5.4 | 25.12% | 0.82 | -32.37% | 0.78 | 4.7 |
| `L2.0_fast_out_b0` | 12.68% | 0.57 | -48.43% | 0.26 | 49.5 | 22.06% | 0.68 | -44.95% | 0.49 | 45.5 |
| `L2.0_fast_out_b1` | 20.89% | 0.86 | -40.62% | 0.51 | 30.9 | 24.12% | 0.72 | -43.65% | 0.55 | 30.3 |
| `L2.0_fast_out_b2` | 18.97% | 0.78 | -35.63% | 0.53 | 17.1 | 24.13% | 0.73 | -37.86% | 0.64 | 22.2 |
| `L2.0_slow_out_b0` | 22.15% | 0.84 | -39.16% | 0.57 | 10.2 | 42.56% | 1.08 | -34.45% | 1.24 | 14.6 |
| `L2.0_slow_out_b1` | 20.76% | 0.79 | -39.26% | 0.53 | 5.6 | 43.95% | 1.10 | -34.45% | 1.28 | 12.8 |
| `L2.0_slow_out_b2` | 19.88% | 0.76 | -43.45% | 0.46 | 3.1 | 33.22% | 0.89 | -41.06% | 0.81 | 8.9 |
| `L2.5_bh_b0` | 43.34% | 1.02 | -53.97% | 0.80 | 0.1 | 31.82% | 0.71 | -74.08% | 0.43 | 0.2 |
| `L2.5_bh_b1` | 43.34% | 1.02 | -53.97% | 0.80 | 0.1 | 31.82% | 0.71 | -74.08% | 0.43 | 0.2 |
| `L2.5_bh_b2` | 43.34% | 1.02 | -53.97% | 0.80 | 0.1 | 31.82% | 0.71 | -74.08% | 0.43 | 0.2 |
| `L2.5_ma50_b0` | 15.17% | 0.62 | -40.68% | 0.37 | 16.9 | 27.91% | 0.75 | -42.71% | 0.65 | 15.4 |
| `L2.5_ma50_b1` | 18.46% | 0.72 | -49.88% | 0.37 | 7.6 | 28.45% | 0.75 | -40.43% | 0.70 | 8.0 |
| `L2.5_ma50_b2` | 11.89% | 0.51 | -48.37% | 0.25 | 5.6 | 27.50% | 0.74 | -44.25% | 0.62 | 5.6 |
| `L2.5_ma100_b0` | 15.35% | 0.60 | -46.03% | 0.33 | 12.5 | 19.02% | 0.56 | -54.59% | 0.35 | 9.5 |
| `L2.5_ma100_b1` | 15.01% | 0.59 | -45.00% | 0.33 | 6.4 | 24.47% | 0.66 | -55.33% | 0.44 | 5.3 |
| `L2.5_ma100_b2` | 15.90% | 0.61 | -44.48% | 0.36 | 3.7 | 33.69% | 0.82 | -44.67% | 0.75 | 3.5 |
| `L2.5_ma200_b0` | 21.61% | 0.71 | -49.78% | 0.43 | 7.4 | 39.83% | 0.90 | -50.60% | 0.79 | 3.5 |
| `L2.5_ma200_b1` | 21.89% | 0.72 | -48.86% | 0.45 | 3.7 | 41.80% | 0.93 | -51.43% | 0.81 | 1.7 |
| `L2.5_ma200_b2` | 19.34% | 0.66 | -59.47% | 0.33 | 2.5 | 34.58% | 0.82 | -52.06% | 0.66 | 1.7 |
| `L2.5_ma50_and_200_b0` | 9.58% | 0.45 | -48.57% | 0.20 | 17.5 | 27.23% | 0.77 | -40.11% | 0.68 | 14.8 |
| `L2.5_ma50_and_200_b1` | 16.02% | 0.66 | -44.00% | 0.36 | 7.4 | 28.63% | 0.79 | -40.43% | 0.71 | 6.8 |
| `L2.5_ma50_and_200_b2` | 8.00% | 0.40 | -46.28% | 0.17 | 5.4 | 29.30% | 0.81 | -39.93% | 0.73 | 4.7 |
| `L2.5_fast_out_b0` | 14.01% | 0.56 | -55.33% | 0.25 | 49.5 | 25.91% | 0.70 | -52.85% | 0.49 | 45.5 |
| `L2.5_fast_out_b1` | 23.79% | 0.82 | -48.53% | 0.49 | 30.9 | 27.93% | 0.73 | -51.43% | 0.54 | 30.3 |
| `L2.5_fast_out_b2` | 19.68% | 0.71 | -42.69% | 0.46 | 17.1 | 27.65% | 0.73 | -45.58% | 0.61 | 22.2 |
| `L2.5_slow_out_b0` | 26.02% | 0.82 | -45.07% | 0.58 | 10.2 | 51.52% | 1.07 | -41.61% | 1.24 | 14.6 |
| `L2.5_slow_out_b1` | 25.48% | 0.80 | -47.10% | 0.54 | 5.6 | 53.17% | 1.09 | -41.61% | 1.28 | 12.8 |
| `L2.5_slow_out_b2` | 23.97% | 0.76 | -50.51% | 0.47 | 3.1 | 38.97% | 0.88 | -49.99% | 0.78 | 8.9 |
| `L3.0_bh_b0` | 49.06% | 1.03 | -58.08% | 0.84 | 0.1 | 32.92% | 0.72 | -81.75% | 0.40 | 0.2 |
| `L3.0_bh_b1` | 49.06% | 1.03 | -58.08% | 0.84 | 0.1 | 32.92% | 0.72 | -81.75% | 0.40 | 0.2 |
| `L3.0_bh_b2` | 49.06% | 1.03 | -58.08% | 0.84 | 0.1 | 32.92% | 0.72 | -81.75% | 0.40 | 0.2 |
| `L3.0_ma50_b0` | 16.26% | 0.60 | -47.08% | 0.35 | 16.9 | 31.36% | 0.76 | -50.15% | 0.63 | 15.4 |
| `L3.0_ma50_b1` | 20.68% | 0.71 | -56.53% | 0.37 | 7.6 | 31.71% | 0.76 | -47.72% | 0.66 | 8.0 |
| `L3.0_ma50_b2` | 12.45% | 0.50 | -55.08% | 0.23 | 5.6 | 30.70% | 0.75 | -52.01% | 0.59 | 5.6 |
| `L3.0_ma100_b0` | 17.01% | 0.59 | -52.70% | 0.32 | 12.5 | 20.04% | 0.56 | -61.46% | 0.33 | 9.5 |
| `L3.0_ma100_b1` | 17.06% | 0.60 | -51.52% | 0.33 | 6.4 | 26.52% | 0.66 | -62.33% | 0.43 | 5.3 |
| `L3.0_ma100_b2` | 17.08% | 0.59 | -51.23% | 0.33 | 3.7 | 37.68% | 0.83 | -51.56% | 0.73 | 3.5 |
| `L3.0_ma200_b0` | 22.87% | 0.69 | -55.27% | 0.41 | 7.4 | 44.64% | 0.91 | -57.73% | 0.77 | 3.5 |
| `L3.0_ma200_b1` | 24.33% | 0.72 | -53.80% | 0.45 | 3.7 | 47.24% | 0.94 | -58.64% | 0.81 | 1.7 |
| `L3.0_ma200_b2` | 21.00% | 0.65 | -65.09% | 0.32 | 2.5 | 38.48% | 0.83 | -59.22% | 0.65 | 1.7 |
| `L3.0_ma50_and_200_b0` | 9.07% | 0.41 | -55.45% | 0.16 | 17.5 | 30.82% | 0.77 | -45.82% | 0.67 | 14.8 |
| `L3.0_ma50_and_200_b1` | 17.81% | 0.65 | -50.33% | 0.35 | 7.4 | 32.29% | 0.79 | -46.17% | 0.70 | 6.8 |
| `L3.0_ma50_and_200_b2` | 7.83% | 0.38 | -52.89% | 0.15 | 5.4 | 33.27% | 0.82 | -45.60% | 0.73 | 4.7 |
| `L3.0_fast_out_b0` | 14.83% | 0.54 | -61.33% | 0.24 | 49.5 | 28.94% | 0.71 | -59.72% | 0.48 | 45.5 |
| `L3.0_fast_out_b1` | 26.11% | 0.80 | -55.26% | 0.47 | 30.9 | 31.07% | 0.74 | -58.24% | 0.53 | 30.3 |
| `L3.0_fast_out_b2` | 19.82% | 0.65 | -57.15% | 0.35 | 17.1 | 30.68% | 0.73 | -52.45% | 0.58 | 22.2 |
| `L3.0_slow_out_b0` | 29.12% | 0.81 | -50.23% | 0.58 | 10.2 | 59.54% | 1.09 | -48.14% | 1.24 | 14.6 |
| `L3.0_slow_out_b1` | 29.48% | 0.82 | -53.64% | 0.55 | 5.6 | 61.58% | 1.10 | -48.14% | 1.28 | 12.8 |
| `L3.0_slow_out_b2` | 27.42% | 0.77 | -55.57% | 0.49 | 3.1 | 43.91% | 0.89 | -56.04% | 0.78 | 8.9 |
*(S = search 2010-02-11→2019-12-31; H = holdout 2020-01-02→2026-08-27. The three `bh` rows
at each leverage are identical by construction — no MA is consulted, so the buffer is inert.)*

---

## Appendix: does a MIX help? (`tools/leverage/mix.py`)

Two distinct meanings of "mix", both tested. Neither is the falsified graded allocation:
exposure here is never scaled by the inverted conviction score.

### Mix A — fixed blend of an untimed sleeve and a 200dma-timed sleeve

Monthly-rebalanced, w in untimed buy-and-hold, (1−w) in the timed version.

| config | full-period Sharpe | CAGR | maxDD | worst 12m | months underwater | search Sh | holdout Sh | **spread** |
|---|---|---|---|---|---|---|---|---|
| QQQ buy-and-hold | 0.85 | +18.52% | −35.6% | −35.2% | 24.7 | 0.98 | 0.74 | 0.24 |
| L2.0 pure timed | 0.82 | +25.04% | −43.2% | −40.4% | 25.8 | 0.71 | 0.94 | 0.23 |
| **L2.0 50/50 blend** | **0.89** | +29.57% | −46.7% | −43.4% | **19.5** | 0.91 | 0.86 | **0.05** |
| L2.0 pure untimed | 0.86 | +32.83% | −63.8% | −63.2% | 30.0 | 1.01 | 0.73 | 0.29 |

The 50/50 blend has the **best full-period Sharpe at every leverage level** — 0.87 / 0.89 /
0.88 at L=1/2/3, beating BOTH of its own components. That is real diversification: the
sleeves are imperfectly correlated because the timed sleeve's returns are buy-and-hold minus
the out-periods.

**It does not escape the selection trap.** On the search period the ranking is monotone in w
and still picks w=1.00 (no timing) at every L: 0.98 / 1.01 / 1.02. The holdout ranking then
inverts perfectly. A backtest-selected blend is the same failure as everything else.

**But w=0.50 does not have to be selected from the backtest.** Equal-weighting two strategies
under genuine uncertainty about which regime is coming is the 1/N prior, not a fitted
parameter — and it is the only parameter choice in this entire investigation that can be
justified a priori. On that basis it delivers two things that are mechanical rather than
fitted:

- **Regime dispersion collapses.** |search Sharpe − holdout Sharpe| is **0.02–0.06** for the
  blend versus 0.23–0.31 for either pure strategy. Five- to ten-fold more stable across the
  two regimes.
- **Time underwater falls sharply.** At L=2.0, **19.5 months versus 30.0** for pure
  buy-and-hold and 25.8 for pure timing. At L=3.0, 24.7 versus 36.5 and 40.4.

**What it does NOT fix: maximum drawdown.** −46.7% at L=2.0 is deeper than QQQ's −35.6%. The
blend shortens and stabilises the pain; it does not make the worst moment shallower.

**Statistical honesty.** The full-period Sharpe edge over QQQ (0.89 vs 0.85) is ~0.04 against
a standard error of roughly 0.25 over 16 years. **That difference is not significant and
should not be relied on.** The dispersion and duration results are structural consequences
of blending imperfectly correlated sleeves and do not depend on the Sharpe gap being real.

### Mix B — ensemble of the 50/100/200dma sleeves

Equal-weight the three rules. Holdout Sharpe 0.83–0.85 versus 0.94 for ma200 alone, so the
ensemble is **worse than the best single rule**. But it addresses the sensitivity the main
study left unsolved:

| across buffers 0% / 1% / 2% | holdout CAGR spread | holdout Sharpe spread |
|---|---|---|
| ma200 alone | 33.53 → 35.12 → 29.67 = **5.45pp** | 0.90 / 0.94 / 0.82 = 0.12 |
| ensemble | 25.48 → 27.75 → 28.24 = **2.76pp** | 0.78 / 0.83 / 0.85 = 0.07 |

**The ensemble halves the buffer sensitivity**, at a cost of roughly 7pp of CAGR. That is the
intended trade: it buys robustness to a parameter nobody knows how to set correctly.

## Appendix: SHIFTING leverage with the timing state (`tools/leverage/shift.py`)

The owner's framing: don't go to cash, **shift leverage**. This is distinct from the
falsified design — what is inverted is the CONVICTION SCORE, not the binary timing STATE.
Carrying L_high above the 200dma and L_low > 0 below it was never tested.

### Two-state grid: L_high above 200dma, L_low below

| L_high | L_low | full Sharpe | CAGR | maxDD | months uw | search | holdout | spread |
|---|---|---|---|---|---|---|---|---|
| 2.0 | **0.0** (cash) | 0.81 | +24.63% | −40.3% | 21.9 | 0.69 | 0.96 | 0.27 |
| 2.0 | **1.0** | **0.89** | +29.65% | −45.5% | **19.5** | 0.90 | 0.88 | **0.01** |
| 2.0 | 2.0 (B&H) | 0.86 | +32.86% | −63.8% | 30.0 | 1.01 | 0.73 | 0.29 |
| 3.0 | 0.0 (cash) | 0.82 | +33.23% | −54.9% | 28.3 | 0.70 | 0.95 | 0.25 |
| 3.0 | **1.5** | **0.89** | +40.26% | −61.0% | 24.6 | 0.91 | 0.88 | **0.03** |

**The owner's idea is validated.** At every L_high, shifting to a reduced leverage
dominates going to cash: higher full-period Sharpe (0.89 vs 0.81), higher CAGR, and far
shorter time underwater (19.5 vs 21.9 months at L=2; 20.3 vs 28.3 at L=3). Going flat
throws away the recovery; halving exposure keeps you in it.

The regime spread collapses to **0.01–0.03** at L_low ≈ L_high/2, versus 0.25–0.29 at
either extreme. "Halve exposure when the trend breaks" is a defensible prior, not a
fitted parameter.

### Three-state ladder on MA agreement

Above both 50 and 200dma / above 200 only / below both — graded on AGREEMENT, not score.

| levels | full Sharpe | CAGR | maxDD | months uw | tr/yr |
|---|---|---|---|---|---|
| QQQ buy-and-hold | 0.85 | +18.52% | −35.6% | 24.7 | 0 |
| 3.0 / 2.0 / 1.0 | 0.89 | +36.41% | −50.7% | 19.0 | 8.9 |
| 2.0 / 1.5 / 1.0 | **0.90** | +28.26% | −42.2% | 19.5 | 8.9 |
| **2.0 / 1.0 / 0.5** | 0.87 | **+24.16%** | **−32.2%** | **19.0** | 8.9 |

**`2.0/1.0/0.5` is the first configuration all day to beat QQQ buy-and-hold on all four
axes simultaneously** — higher Sharpe (0.87 vs 0.85), higher CAGR (+24.16% vs +18.52%),
*shallower* max drawdown (−32.2% vs −35.6%), and shorter time underwater (19.0 vs 24.7
months). Nothing in six prior studies managed a shallower drawdown than QQQ.

### Stress tests — what holds and what does not

**Robust to the leverage levels.** Perturbing them keeps the four-way win:
2.0/1.25/0.5 (0.87), 1.75/1.0/0.5 (0.87), 2.25/1.0/0.5 (0.86), 2.0/0.75/0.5 (0.86). Not
a knife edge.

**FRAGILE to the buffer.** Full Sharpe by buffer: **0% → 0.79, 1% → 0.87, 2% → 0.79.**
A sharp peak at the value used. At 0% or 2% it does NOT beat QQQ on all four. This is the
same unsolved buffer sensitivity flagged in the main study and it is the single biggest
reason to distrust this result.

**FRAGILE to costs.** 0bp → 0.89, 10bp → 0.87, **20bp → 0.84, 30bp → 0.81.** At 8.9
trades/yr the four-way win disappears above roughly 15bp round trip.

**The selection trap is not escaped.** The search period still ranks plain buy-and-hold
highest (1.01). A purely search-maximising pre-registration would still have chosen "don't
time it."

### Verdict

The mechanism — reduce leverage rather than exit — is sound and improves every config it
touches, independent of selection. The specific `2.0/1.0/0.5` ladder is the best thing
found, but its four-way win over QQQ rests on a 1% buffer that fails at 0% and 2%, and on
execution costs under ~15bp. Treat the mechanism as the finding and the exact
configuration as provisional. The obvious next step is averaging across buffers (an
ensemble over the fragile parameter), which halved buffer sensitivity elsewhere.

## Appendix: all FOUR states of (50, 200), and the buffer ensemble

The previous ladder collapsed "above 50, below 200" into the same bucket as "below both".
Split properly there are four states. Time spent in each: **S1 above both 67.5%, S2 above
200 only 15.7%, S3 below 200 but above 50 just 3.7%, S4 below both 13.1%.**

### S3 does NOT deserve more leverage — my own hypothesis, falsified

The streak-age result (best returns in the first ~20 days of a fresh regime) suggested S3,
the early-recovery state, should get MORE exposure than S2. It does not:

| S1/S2/S3/S4 | full Sharpe | CAGR | maxDD | months uw | beats QQQ 4 ways |
|---|---|---|---|---|---|
| 2.0/1.0/**0.5**/0.5 (S3 treated as weak) | 0.87 | +24.16% | **−32.2%** | 19.0 | **yes** |
| 2.0/1.0/1.0/0.5 (S3 = S2) | 0.86 | +24.29% | −34.6% | 18.9 | yes |
| 2.0/1.0/**1.5**/0.5 (S3 > S2) | 0.86 | +24.54% | −39.5% | 18.7 | **no** |

Giving S3 more leverage deepens max drawdown by 7pp and loses the four-way win. "Above the
50dma while still below the 200dma" is mostly a dead-cat bounce, not an early recovery —
the streak-age effect does not transfer to this state definition. **Treat S3 as weak.**

### The 50/200 crossover (golden/death cross) is worse

| config | full Sharpe | CAGR | maxDD | tr/yr | search | holdout |
|---|---|---|---|---|---|---|
| cross 2.0/1.0 | 0.86 | +30.54% | −51.7% | **1.3** | 0.95 | 0.79 |
| cross 3.0/1.5 | 0.87 | +40.32% | −69.9% | 1.3 | 0.96 | 0.78 |

Attractively low turnover (1.3 trades/yr), but max drawdown is ~20pp deeper and none
achieves the four-way win. Note the shape: high search Sharpe (0.95–0.96), low holdout
(0.78–0.80) — looks good in-sample, fails out. Price-vs-MA beats MA-vs-MA here.

### The buffer ensemble does not rescue the result — it confirms the fragility

Averaging the 0% / 1% / 2% buffer variants was the obvious fix for the knife-edge
sensitivity. It does not work:

| | full Sharpe | CAGR | maxDD | months uw | beats QQQ 4 ways |
|---|---|---|---|---|---|
| single, buffer 0% | 0.80 | +22.14% | −36.2% | 26.9 | no |
| single, buffer 1% | **0.86** | +24.30% | −34.6% | 18.9 | **yes** |
| single, buffer 2% | 0.79 | +21.64% | −34.2% | 19.3 | no |
| **ensemble over buffers** | **0.82** | +22.72% | −34.9% | 18.9 | **no** |

The ensemble lands near the average (0.82), not the peak, and **fails to beat QQQ's 0.85 on
Sharpe.** Averaging over the fragile parameter removes the edge along with the fragility,
which is the correct diagnosis: **the 1% buffer's advantage was specific to that buffer,
not a property of the strategy.**

### Revised verdict

This tempers the previous appendix. What survives:

- **The mechanism — reduce leverage rather than exit — is robust.** It improves every
  configuration it touches, at every leverage level, independent of selection. Time
  underwater falls from ~27–30 months to ~19 in essentially every variant.
- **The specific four-way win over QQQ does not survive buffer-averaging** and should be
  treated as a fitted result, not a finding.

Seven studies, and the honest score remains: the mechanism is real and worth using if one
is going to time at all; no specific configuration has demonstrated an edge that survives
its own parameter uncertainty.

## Appendix: SIX states — adding the 50-vs-200 cross as a third dimension

Price-vs-50, price-vs-200 and 50-vs-200 give six reachable states (two of the eight
combinations are arithmetically impossible). Time in each:

| state | definition | share |
|---|---|---|
| **A** | P>50, P>200, 50>200 — established uptrend | 62.2% |
| **B** | P>50, P>200, 50<200 — **reclaim**, price above both but MAs not yet crossed | 5.3% |
| **C** | P>50, P<200, 50<200 — bounce inside a downtrend | 3.7% |
| **D** | P<50, P>200, 50>200 — pullback inside an uptrend | 15.7% |
| **E** | P<50, P<200, 50>200 — **breakdown**, lost both averages, MAs still crossed | 6.0% |
| **F** | P<50, P<200, 50<200 — established downtrend | 7.1% |

### Forward returns are INVERTED against trend strength

Forward TQQQ return, 21 trading days ahead:

| state | n | mean | median |
|---|---|---|---|
| A established uptrend | 2570 | **+2.71%** | +3.76% |
| B reclaim | 222 | +5.15% | +4.60% |
| C bounce in downtrend | 154 | **−1.97%** | +3.08% |
| D pullback in uptrend | 649 | +6.83% | +8.99% |
| E breakdown | 249 | +8.66% | +5.95% |
| F established downtrend | 295 | **+10.73%** | **+14.32%** |

**The strongest state has the worst forward returns and the weakest state has the best** —
F (+10.73%) is nearly 4x A (+2.71%). This is the same inversion found four other ways today,
now visible directly in the state machine. It is the equity risk premium: expected returns
are highest after prices have fallen.

**This explains why going to cash is wrong.** The weak states are not low-return states —
they are the highest-return states. Leverage is reduced there for *risk control*, not
because the forward return is poor. Confirmed in the grid: forcing E and F to zero gives
Sharpe 0.81 / CAGR +21.72% / 30.9 months underwater, materially worse than holding 0.5x
through them, and raising E to 1.0x improves things further (Sharpe 0.88, CAGR +25.45%).

**C is the only genuinely bad state** — the one with a negative mean (−1.97%). Price above
the 50dma while both the 200dma and the cross are still negative is the dead-cat bounce, and
it independently confirms the earlier finding that this state should be treated as weak.

**B is real but small.** The reclaim state does have better forward returns than A (+5.15%
vs +2.71%), vindicating its separation — but at 5.3% of the time, setting B above, equal to
or below A moves full Sharpe only between 0.86 and 0.87.

### Best configurations

| A/B/C/D/E/F | full Sharpe | CAGR | maxDD | months uw | search | holdout |
|---|---|---|---|---|---|---|
| 2.0/2.0/0.5/1.0/**1.0**/0.5 | **0.88** | +25.45% | −35.3% | 18.9 | 0.89 | 0.87 |
| 2.0/2.0/0.5/1.0/0.5/0.5 | 0.87 | +24.16% | −32.2% | 19.0 | 0.84 | 0.89 |
| 2.0/2.0/0.5/1.0/**0.0/0.0** | 0.81 | +21.72% | −33.9% | 30.9 | 0.72 | 0.91 |

The top row is the most balanced result found: search 0.89 / holdout 0.87, a regime spread
of **0.02**, and it beats QQQ on all four axes.

### The buffer fragility is NOT fixed

Full Sharpe across 0% / 1% / 2% buffers: **0.79 / 0.87 / 0.79**, spread 0.08 — unchanged
from the four-state model. Richer state definition does not rescue the parameter
sensitivity, and the 1% peak remains the single weakest point in this whole family.

## Appendix: sweeping state B, and what the buffer is actually doing

Base config A=2.0, C=0.5, D=1.0, E=1.0, F=0.5; only B (the reclaim state) varies.

### B = 3.0 is marginally worse

| B | full Sharpe | CAGR | maxDD | months uw | search | holdout |
|---|---|---|---|---|---|---|
| 1.0 | 0.88 | +24.78% | −35.3% | 19.0 | 0.91 | 0.86 |
| **2.0** | **0.88** | +25.45% | −35.3% | 18.9 | 0.89 | 0.87 |
| 2.5 | 0.87 | +25.65% | −35.3% | 18.5 | 0.87 | 0.87 |
| **3.0** | **0.86** | +25.81% | −35.3% | 18.5 | 0.85 | 0.87 |

Monotone and unexciting: raising B buys **+0.36pp of CAGR** (24.78 → 25.81) and costs
**0.02 of Sharpe** (0.88 → 0.86). No free lunch, and B's 5.3% footprint means the whole
sweep moves nothing much. Max drawdown is pinned at −35.3% throughout — B never sets the
worst moment. B=3.0 also makes the buffer *more* fragile: spread 0.09 versus 0.07 at B=2.0.

**Verdict: keep B at 2.0.** The reclaim state's better forward return (+5.15% vs A's
+2.71%) is real but too small a slice to pay for the extra risk.

### THE IMPORTANT RESULT: the edge is the buffer, not the state machine

Running the identical configs on RAW price-vs-MA inequalities — labels meaning exactly
what they say, no hysteresis:

| | full Sharpe | CAGR | maxDD | months uw | trades/yr | beats QQQ 4 ways |
|---|---|---|---|---|---|---|
| **raw inequalities** | **0.79–0.81** | +22.1 to +23.1% | −35.3 to −39.6% | 19.5–28.8 | **17.5** | **none** |
| **buffered 1%** | **0.86–0.88** | +24.8 to +25.8% | −35.3% | 18.5–19.0 | **8.4** | all |

**Without the hysteresis band the strategy fails outright** — Sharpe ~0.80 against QQQ's
0.85, and not one variant beats QQQ on all four axes. The buffer halves turnover (17.5 →
8.4 trades/yr) and that is where the entire advantage comes from.

This reframes everything above. It is not "a six-state model that happens to use a buffer";
it is **a turnover-reduction device whose benefit peaks sharply at one parameter value**
(0.80 / 0.88 / 0.81 at 0% / 1% / 2%). The state machine is close to decoration — B, C and E
assignments barely move the result, while the buffer moves it by 0.08 of Sharpe.

Combined with the earlier finding that averaging over buffers destroys the edge, the honest
reading is that **this family has no demonstrated edge independent of one fitted smoothing
parameter.** The durable results remain the two structural ones: reduce leverage rather than
exit, and expect returns to be highest in the weakest states.

## Appendix: fine buffer sweep — the "knife edge" was an artifact of a coarse grid

Earlier appendices tested buffers at 0% / 1% / 2% only, saw 0.79 / 0.87 / 0.79, and
concluded the result rested on a fitted knife-edge parameter. **That conclusion was wrong.**
An 11-point sweep of the same config (A=2.0, B=2.0, C=0.5, D=1.0, E=1.0, F=0.5):

| buffer | full Sharpe | CAGR | months uw | trades/yr | **search** | holdout | beats QQQ 4 ways |
|---|---|---|---|---|---|---|---|
| 0.00% | 0.80 | +22.75% | 27.9 | 17.0 | 0.79 | 0.83 | |
| 0.25% | 0.78 | +22.10% | 28.7 | 14.2 | 0.75 | 0.82 | |
| 0.50% | 0.84 | +24.14% | 26.6 | 10.6 | 0.82 | 0.87 | |
| **0.75%** | **0.88** | +25.53% | 18.7 | 8.8 | 0.88 | 0.88 | **yes** |
| **1.00%** | **0.88** | +25.45% | 18.9 | 7.8 | **0.89** | 0.87 | **yes** |
| **1.25%** | **0.87** | +24.98% | 19.0 | 7.1 | 0.87 | 0.87 | **yes** |
| 1.50% | 0.85 | +24.50% | 18.9 | 6.4 | 0.85 | 0.86 | |
| 2.00% | 0.81 | +22.93% | 21.1 | 5.8 | 0.75 | 0.87 | |
| 3.00% | 0.76 | +21.26% | 26.7 | 4.7 | 0.66 | 0.86 | |

**It is a smooth hill with a plateau at 0.75–1.25%, not a spike.** The coarse grid happened
to sample the peak and both shoulders, which made a broad optimum look like a knife edge.

**And the peak is selectable in advance.** The SEARCH period alone (2010-2019) peaks at
1.00% with Sharpe 0.89, independently of the holdout. Freezing that choice delivers 0.87 on
the holdout, against the holdout's own best of 0.88. The buffer was not fitted to the
holdout.

### Ensembling over the plateau preserves the result

The earlier finding that "averaging over buffers destroys the edge" was an artifact of the
range averaged:

| ensemble range | full Sharpe | CAGR | maxDD | months uw | search | holdout | beats QQQ 4 ways |
|---|---|---|---|---|---|---|---|
| 0% / 1% / 2% (tested earlier) | 0.83 | +23.74% | −35.3% | 19.0 | 0.82 | 0.86 | no |
| **0.75% / 1.0% / 1.25%** | **0.87** | +25.33% | −35.3% | 18.9 | 0.88 | 0.88 | **yes** |
| **0.5% … 1.5%** | **0.87** | +24.94% | −35.3% | 18.9 | 0.87 | 0.87 | **yes** |
| all 11, 0%…3% | 0.83 | +23.64% | −35.9% | 19.3 | 0.81 | 0.86 | no |

Averaging across any plausible band width (0.5–1.5%) keeps the four-way win over QQQ. Only
ensembles that include 0% — effectively "no buffer at all" — or buffers wide enough to
suppress the signal destroy it.

### Revised standing

The buffer is a genuine parameter with a broad optimum, selectable from search data, and
robust to averaging within its sensible range. The two earlier characterisations — "knife
edge" and "averaging destroys the edge" — are **withdrawn**; both were artifacts of a
three-point grid.

What does NOT change: this family still loses to plain buy-and-hold on the search period
(0.89 vs 1.01 at L=2.0). Conditional on choosing to run a state machine at all, the buffer
is well behaved. The prior decision — to time rather than hold — remains the one the search
data does not support.

One oddity worth recording: 0.25% is *worse* than 0% (0.78 vs 0.80). A very narrow band
appears to add lag without meaningfully suppressing whipsaw — worse than either no band or
an adequate one.
