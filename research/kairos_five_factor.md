# A five-factor regime filter for leveraged Nasdaq exposure

**Question:** does a daily five-factor "healthy / fragile" regime score — Credit, VIX,
Breadth, Trend, Utilities — decide well enough between TQQQ and T-bills to justify the
performance claimed by kairosalgo.com (40.6% CAGR, Sharpe 1.39, −24.5% max drawdown,
2020–2026) or raincheck.fund (+37.83% in 2024, +57.24% in 2025, Sharpe 2.37)?

**Answer, up front:** No — and the reason is specific and reproducible.

1. **A 40.6% CAGR is reachable. A −24.5% max drawdown is not.** Across **198
   configurations** evaluated on the holdout, the best CAGR was **42.01%** — but that
   configuration drew down **−64.83%**. The *shallowest* drawdown any configuration
   achieved was **−29.20%**, and it earned only **9.23%** CAGR at Sharpe 0.36. **No
   configuration came within a factor of two of the claimed drawdown while earning
   anything like the claimed return.** The best Sharpe achieved anywhere was **0.88**,
   against a claimed 1.39.
2. **The honest pre-registered answer is "don't filter."** Of 198 configurations, the
   only **6** that beat buy-and-hold TQQQ on the search period (2010–2019) were
   `binary_T0` — which *is* buy-and-hold. A rule frozen on the search period would have
   been "hold TQQQ and don't time it."
3. **Every configuration that beat buy-and-hold on the holdout did so because it was
   flat during 2020 and 2022.** In the calm 2023–2026 stretch the best filter earned
   62.77% versus buy-and-hold's 81.27%. The filter is crash insurance, and it is priced
   like insurance: it costs return in every year without a crash.
4. **The composite score is inverted at the daily horizon.** Days scoring 0/5 ("most
   fragile") were followed by a mean next-day TQQQ return of **+0.4865%**; days scoring
   5/5 ("healthiest") by **+0.0674%**. Whatever the score measures, it is not next-day
   direction.

---

## 1. What the two sites claim, and what they do not disclose

| | kairosalgo.com | raincheck.fund |
|---|---|---|
| Signal | Five factors checked daily at 3:50pm ET: Credit (spreads), VIX, Breadth, Trend, Utilities | One "Market Signal", integer **−9…+9**, from "statistical trends in price action of QQQ **and its holdings**" |
| Output | Binary: Healthy → Nasdaq exposure; Fragile → T-bills | Regime = consecutive same-sign days; long TQQQ in uptrends, cash in downtrends |
| Sizing | Not disclosed | 67–75% TQQQ at start of uptrend; 20–30% reserved; remainder TBIL; "leverage is reduced as the Market Signal declines" |
| Claimed | 40.6% CAGR vs SPY 15.5%; Sharpe 1.39 vs 0.81; max DD −24.5% vs −33.7%; ~11 trades/yr; $100K → $896K, 2020–2026 | +37.83% 2024 (QQQ +25.58%); +57.24% 2025 (QQQ +20.77%); Sharpe 2.37 |
| Disclosed formulas | **None** | **None** |

Neither site discloses a formula, weight, threshold, or lookback. Kairos never states
whether "Nasdaq" means QQQ or TQQQ. **This is not a reverse-engineering exercise** — it
is an independent construction using the same five named factors, reported honestly.

Two things about the claims are worth flagging before any results:

- **Raincheck's flagship case study is a maximum-favourable-excursion number.** They
  headline "+45.03%" for their 2024-05-06 → 2024-07-25 uptrend, but that is the *peak*
  on 2024-07-10. Entry-to-exit is TQQQ **+8.04%**; QQQ over the identical window was
  **+4.09%**. TQQQ delivered **1.97x**, not 3x — decay ate a third of the leverage in 55
  days of chop.
- **Within an uptrend, their strategy *is* buy-and-hold TQQQ.** The signal contributes
  nothing while long. All of any edge must come from what it avoids while flat. Their
  live record also begins 2023-11-02 — ~2.8 years spanning one of the strongest Nasdaq
  runs on record, i.e. a window containing very little of the sustained loss the filter
  exists to avoid.

**This is why the primary benchmark in this report is buy-and-hold TQQQ, not SPY.**
Beating SPY with a 3x fund is not evidence of skill; it is what leverage does in a rising
market.

---

## 2. Data

All cached under `data/kairos/`, pulled **2026-08-29**.

| Series | Source | Coverage |
|---|---|---|
| TQQQ, QQQ, QLD, SPY, XLU, BIL daily OHLC | `mcp__robinhood__get_equity_historicals`, split-adjusted | 2009-01-02 → 2026-08-27 (TQQQ real data from **2010-02-11**, its inception) |
| Breadth universe: 501 of 503 S&P 500 names | same | 2009-01-02 → 2026-08-27 |
| `VIXCLS`, `DGS3MO`, `BAA10Y`, `BAMLH0A0HYM2` | FRED CSV endpoint | 2008-01-02 → 2026-08-27 (except as below) |

**Backtest window: 2010-02-11 → 2026-08-27, 4,160 trading days (16.5 years).**

Two data problems worth recording, both of which would have silently corrupted results:

**(a) TQQQ's pre-inception bars are synthetic.** The historicals API returns bars back to
2009-01-02 for TQQQ, but 280 of them are flagged `interpolated` with `volume: 0` and
OHLC all equal — synthetic padding before the fund existed. `extract_dumps.py` drops
every interpolated bar. Using them would have fabricated a flat price history through
2009 and inflated every early-period statistic.

**(b) The specified credit series is licence-restricted to a rolling 3 years.** The brief
specified `BAMLH0A0HYM2` (ICE BofA US High Yield OAS). FRED's CSV endpoint serves only
**796 rows starting 2023-08-29** for it, *regardless* of the `cosd`/`coed` parameters —
verified across three URL variants. Every ICE BofA `BAML*` series behaves this way
(`BAMLC0A0CM` likewise returns 796 rows), while non-ICE series on the identical endpoint
honour `cosd` and return full history. Three years cannot support a 16-year backtest.

**Substitution:** `BAA10Y` (Moody's Baa corporate yield minus 10-Year Treasury), a
full-history daily credit spread. Justified empirically rather than asserted — over the
752-day overlap:

- level correlation with HY OAS: **0.546**
- **daily-change correlation: 0.615**

(An earlier version of this check reported 0.007 for the change correlation. That was an
alignment bug — the lagged BAA10Y series was being compared against the unlagged HY
series. It is noted here because it is exactly the kind of artefact that gets mistaken
for a finding.)

---

## 3. Factor definitions

Every threshold was fixed from finance convention **before any backtest output was
produced**, and none was tuned. Each factor emits a boolean; `score` = count of healthy
factors (0–5). Also reported as **`net_score` = 2·score − 5**, a symmetric −5…+5 scale
matching the shape of Raincheck's disclosed −9…+9 signal.

| # | Factor | Healthy when | Why this rule |
|---|---|---|---|
| 1 | **Credit** | `BAA10Y` ≤ its own trailing **252-day median** | Spread *levels* are regime-dependent across 16 years (post-GFC / ZIRP / 2022); a self-referencing percentile avoids betting on the era. **Lagged one trading day** — Moody's/Treasury series are not reliably available at 3:50pm, and this removes a genuine lookahead channel. |
| 2 | **VIX** | `VIXCLS` ≤ **20.0** | The canonical calm/stressed cutoff, and — crucially — a number chosen from *outside* this dataset, so it cannot have been fitted to it. A trailing percentile would adapt to a high-vol regime and call it "healthy", which is the wrong behaviour for a risk-off filter. |
| 3 | **Breadth** | **>50%** of universe above own 200dma | Classic. A name enters the denominator only once it has 200 prior closes, so 2024–25 listings (GEV, SOLV, RDDT, SNDK) join at the right time rather than being back-filled. |
| 4 | **Trend** | QQQ close > its own **200dma** | The classic unfitted trend filter. |
| 5 | **Utilities** | XLU trailing 60-day return **≤** SPY's | Utilities *leading* is the defensive-rotation tell. Sign stated explicitly because it is the easiest thing to get backwards: **utilities leading is UNHEALTHY.** |

Observed healthy rates: Credit 59.6%, VIX 71.3%, Breadth 82.4%, Trend 83.9%,
Utilities 59.4% of days.

### Survivorship bias in Breadth — stated loudly

The universe is **today's** S&P 500, not point-in-time. Names that fell out of the index
between 2010 and 2026 are absent, so historical breadth is biased **upward** — the
survivors are the ones that trended up. This flatters any strategy using breadth as a
risk-on trigger, and it cannot be fixed without point-in-time membership data. Breadth
is healthy 82.4% of days in this construction, which is almost certainly too high.

---

## 4. Method

- **No lookahead.** Factors come from day *t*'s close. Primary execution is
  **next-open**: the signal is filled at day *t+1*'s open, with cash accruing overnight,
  the rebalance at the open, and valuation at that close. A **same-close (MOC)** variant
  is also reported. Validated programmatically: **0 of 4,159 rows** use a signal other
  than the strictly prior day's score.
- **Real TQQQ, never synthetic 3×QQQ.** Actual traded prices, embedding the real expense
  ratio, daily-rebalancing decay and structural quirks.
- **Position-based accounting.** The engine holds **shares** and lets weights drift
  between rebalances; it rebalances *only* when the target moves by more than the
  no-trade band, never on a daily schedule. This matters: with daily rebalancing, a
  target leverage is route-independent (⅓ TQQQ + ⅔ cash rebalanced daily reproduces 1x
  QQQ to within 0.02%/yr here — leveraged-ETF decay is a consequence of *not*
  rebalancing). The routes differ only when positions are held between flips.
- **Costs** charged on notional traded (`bps × |Δnotional|`), so a graded mapping shuffling
  10% of the book pays a tenth of a full flip. Base **2bp**; stressed to 5/10/20bp,
  which also stands in for TQQQ's wider spreads in 2010–2012.
- **Search / holdout.** Search = inception → 2019-12-31. Holdout = 2020-01-01 → end,
  **deliberately aligned with Kairos's claimed 2020–2026 window.**

> **The search period is a near-uninterrupted Nasdaq bull market**, where a risk filter
> has almost nothing to prove and will tend to look useless or harmful. The holdout
> contains the 2020, 2022 and 2025 drawdowns. A good holdout result is therefore partly
> luck about which period got which stress, and a weak search result is not damning.
> Both are reported; neither is hidden.

### Allocation policies

Policies map score → target **effective leverage** L ∈ [0,3]:

- **binary_T** (T = 0…5): L = 3 if score ≥ T else 0 — the baseline sweep
- **linear**: L = 3·score/5 · **convex_sq**: L = 3·(score/5)² · **convex_step**: 0,0,0,1,2,3
- **cap70_\***: same shapes capped at **L = 2.1** (70% of 3x — what Raincheck actually discloses holding)
- **hyst_H\_L**: hysteresis — enter at score ≥ H, exit at score ≤ L
- **ema3/5/10**: EMA-smoothed score mapped linearly
- **minhold5/10/21**: once in, hold ≥ N days
- **age_ramp**: leverage ramps up with streak age
- **TB_\***: **Trend + Breadth only** (the Raincheck ablation), score2 ∈ 0…2

### Routes

- **ladder** — reach L with the lowest-multiple combination: L≤1 → QQQ + cash;
  1<L≤2 → QQQ/QLD; 2<L≤3 → QLD/TQQQ
- **pure_tqqq** — scale one 3x fund against cash

---

## 5. Benchmarks

| Period | Strategy | CAGR | Vol | Sharpe | max DD |
|---|---|---:|---:|---:|---:|
| **SEARCH** 2010-02-11→2019-12-31 | **TQQQ B&H** | **48.65%** | 50.98% | **1.02** | −58.08% |
| | QLD B&H | 34.13% | 34.18% | 1.01 | −42.46% |
| | QQQ B&H | 17.40% | 17.23% | 0.98 | −23.16% |
| | SPY B&H | 11.69% | 14.68% | 0.79 | −20.18% |
| **HOLDOUT** 2020-01-01→2026-08-27 | **TQQQ B&H** | **32.48%** | 73.83% | **0.72** | **−81.75%** |
| | QLD B&H | 30.38% | 49.92% | 0.73 | −63.79% |
| | QQQ B&H | 19.92% | 24.94% | 0.74 | −35.62% |
| | SPY B&H | 13.92% | 20.22% | 0.60 | −34.10% |
| **FULL** | TQQQ B&H | 42.33% | 61.20% | 0.86 | −81.75% |
| | QQQ B&H | 18.52% | 20.68% | 0.85 | −35.62% |
| | SPY B&H | 12.64% | 17.12% | 0.69 | −34.10% |

Kairos's claimed SPY comparator (15.5% CAGR, Sharpe 0.81) is close to the measured
13.92% / 0.60 for 2020–2026 — their benchmark is roughly right, which makes the
strategy-side claims the ones to scrutinise.

---

## 6. The threshold sweep — search and holdout side by side

Route = ladder, next-open, 2bp, band = 0. **Primary comparator is TQQQ B&H, bolded.**

| Policy | | SEARCH | | | | HOLDOUT | | |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| | CAGR | Sharpe | maxDD | tr/yr | CAGR | Sharpe | maxDD | tr/yr |
| **TQQQ B&H** | **48.65%** | **1.02** | **−58.08%** | **0** | **32.48%** | **0.72** | **−81.75%** | **0** |
| binary_T0 (=B&H) | 49.07% | 1.03 | −58.08% | 0.1 | 33.27% | 0.72 | −81.75% | 0.2 |
| binary_T1 | 34.13% | 0.86 | −54.63% | 4.8 | 34.41% | 0.75 | −74.41% | 5.9 |
| **binary_T2** | 36.03% | 0.92 | −51.92% | 5.8 | **42.01%** | **0.88** | −64.83% | 6.5 |
| binary_T3 | 31.40% | 0.88 | −60.38% | 7.8 | 25.13% | 0.65 | −50.29% | 10.7 |
| binary_T4 | 17.35% | 0.62 | −58.25% | 12.5 | 8.95% | 0.35 | −46.29% | 12.8 |
| binary_T5 | 9.01% | 0.49 | −43.03% | 15.3 | **−7.27%** | **−0.19** | −62.20% | 15.5 |
| linear | 25.40% | 0.83 | −47.24% | 41.2 | 21.60% | 0.61 | −52.19% | 46.0 |
| convex_sq | 21.24% | 0.80 | −39.59% | 41.2 | 11.64% | 0.41 | −41.34% | 46.0 |
| convex_step | 20.47% | 0.77 | −40.87% | 33.2 | 9.10% | 0.34 | −40.88% | 35.6 |
| cap70_linear | 19.98% | 0.87 | −35.49% | 41.2 | 18.21% | 0.62 | −39.45% | 46.0 |
| cap70_binary_T4 | 15.13% | 0.68 | −44.33% | 12.5 | 9.18% | 0.35 | −32.18% | 12.8 |
| cap70_convex_step | 15.36% | 0.78 | −30.24% | 33.2 | 9.23% | 0.36 | **−29.20%** | 35.6 |
| hyst_H3_L1 | 36.93% | **0.96** | −60.23% | 2.1 | 35.90% | 0.80 | −62.47% | 4.4 |
| hyst_H3_L0 | 31.89% | 0.86 | −60.23% | 1.7 | 36.24% | 0.79 | −67.38% | 2.0 |
| hyst_H2_L0 | 31.50% | 0.83 | −53.71% | 2.9 | 38.75% | 0.82 | −74.02% | 2.3 |
| hyst_H4_L1 | 35.13% | 0.94 | −60.35% | 1.5 | 20.83% | 0.58 | −61.46% | 3.2 |
| hyst_H4_L2 | 28.10% | 0.83 | −61.94% | 4.0 | 8.38% | 0.34 | −57.39% | 5.0 |
| hyst_H5_L2 | 21.15% | 0.74 | −45.47% | 1.9 | −3.99% | 0.03 | −67.12% | 2.9 |
| hyst_H5_L3 | 9.37% | 0.43 | −57.85% | 4.0 | −0.09% | 0.11 | −51.10% | 5.3 |
| ema3 | 27.29% | 0.87 | −42.08% | 233.4 | 22.61% | 0.63 | −51.86% | 242.6 |
| ema5 | 28.52% | 0.90 | −40.77% | 248.1 | 22.90% | 0.63 | −50.94% | 249.7 |
| ema10 | 29.56% | 0.92 | −40.48% | 251.6 | 22.66% | 0.63 | −50.06% | 249.7 |
| ema5_cap70 | 21.25% | **0.91** | −30.23% | 248.1 | 19.02% | 0.64 | −38.37% | 249.7 |
| minhold5_T3 | 31.74% | 0.87 | −59.65% | 6.0 | 29.38% | 0.71 | −53.55% | 6.8 |
| minhold10_T3 | 28.67% | 0.81 | −65.19% | 5.2 | 26.10% | 0.66 | −65.52% | 6.5 |
| minhold21_T3 | 29.80% | 0.81 | −67.68% | 4.0 | 18.80% | 0.54 | −80.05% | 5.3 |
| age_ramp_T3 | 23.92% | 0.76 | −57.95% | 11.1 | 11.53% | 0.41 | −46.80% | 14.9 |
| **TB_binary_T1** (trend+breadth) | 32.58% | 0.85 | −53.09% | 4.6 | **41.77%** | **0.86** | −61.09% | 5.6 |
| TB_binary_T2 | 24.70% | 0.74 | −62.44% | 7.8 | 18.43% | 0.54 | −50.69% | 7.7 |
| TB_linear | 27.86% | 0.79 | −57.67% | 11.4 | 30.49% | 0.73 | −52.75% | 12.5 |
| TB_cap70_T2 | 21.17% | 0.79 | −51.16% | 7.8 | 16.67% | 0.54 | −38.39% | 7.7 |

**Monotonicity is absent and the direction is wrong.** Raising the threshold — demanding
*more* factors agree — makes results monotonically **worse**, from binary_T1 (34.41%
holdout) down to binary_T5 (**−7.27%**, Sharpe **−0.19**). Requiring all five factors to
be healthy was the single worst rule tested. That is the opposite of what the premise
predicts.

### Trade count

The claimed "~11 trades/year" is plausible for a binary rule: **binary_T3 produces 10.7
round trips/yr** on the holdout, binary_T2 6.5/yr, hysteresis variants 2.0–5.3/yr.
**Graded mappings do not:** linear runs **46.0/yr** and EMA variants **~250/yr** without a
no-trade band. Any product claiming ~11 trades/year is running a binary or hysteretic
rule, not a daily-recomputed graded one.

---

## 7. The discipline result — what the search period actually selects

This is the most important table in the report.

| | Count |
|---|---|
| Configurations evaluated (policy × route × band) | **198** |
| Beating TQQQ B&H **CAGR** on SEARCH | **6 of 198** |
| Beating TQQQ B&H **Sharpe** on SEARCH | **6 of 198** |
| …and all 6 are | **`binary_T0`, which *is* buy-and-hold** |
| Beating TQQQ B&H Sharpe on HOLDOUT | 49 of 198 |

**A rule frozen on the search period would have been "hold TQQQ, don't time it."** The
49 configurations that beat buy-and-hold on the holdout were not selectable in advance.

Among genuinely-filtering configs, ranking by search Sharpe and then reading the holdout:

| Config | Search Sharpe | Search CAGR | → Holdout Sharpe | Holdout CAGR |
|---|---:|---:|---:|---:|
| ema5_cap70 | **0.97** (best) | 21.82% | **0.63** | 18.22% |
| hyst_H3_L1 | 0.96 | 36.93% | 0.80 | 35.90% |
| ema5 | 0.95 | 30.89% | 0.64 | 22.84% |

The **top** search pick *loses* to buy-and-hold on the holdout (0.63 vs 0.72). The #2 pick
modestly wins (0.80). That is noise-level discrimination, not a validated edge.

---

## 8. Graded vs binary, turnover and the no-trade band

The hypothesis was that graded exposure would reduce whipsaw damage. **It did not.**

| Policy | band | trades/yr | turnover | CAGR@0bp | CAGR@20bp | **cost drag** |
|---|---:|---:|---:|---:|---:|---:|
| binary_T2 | 0.00 | 6.5 | 43 | 42.20% | 40.36% | **1.83%** |
| binary_T3 | 0.00 | 10.7 | 71 | 25.40% | 22.74% | 2.66% |
| **linear** | 0.00 | **46.0** | 304 | 22.72% | 11.94% | **10.77%** |
| linear | 0.60 | 27.4 | 235 | 21.75% | 13.41% | 8.34% |
| convex_sq | 0.00 | 46.0 | 374 | 12.91% | 0.84% | **12.07%** |
| cap70_linear | 0.60 | 8.7 | 63 | 21.75% | 19.46% | 2.29% |
| **ema5** | 0.00 | **249.7** | 171 | 23.53% | 17.33% | 6.20% |
| ema5 | 0.60 | 9.4 | 70 | 25.73% | 23.09% | 2.63% |
| hyst_H4_L2 | 0.00 | 5.0 | 33 | 8.49% | 7.41% | 1.08% |
| TB_binary_T1 | 0.00 | 5.6 | 37 | 41.92% | 40.35% | 1.58% |

Findings, on the holdout:

- **Graded loses to binary on risk-adjusted terms.** Best graded Sharpe 0.64
  (`ema5_cap70`); best binary 0.88 (`binary_T2`). Partial exposure through ambiguous
  regimes did not help — it diluted the recoveries, which is where leveraged Nasdaq
  makes its money.
- **Graded costs 4–7× the turnover.** At 20bp, `linear` bleeds **10.77%/yr** and
  `convex_sq` **12.07%/yr** — enough to erase the entire strategy.
- **The no-trade band is essential and it works.** It cuts `ema5` from 249.7 to 9.4
  trades/yr and *improves* CAGR (23.53% → 25.73%); `cap70_linear` from 46.0 to 8.7
  trades/yr with drag falling 6.67% → 2.29%. A graded system without a band is not
  viable at any realistic cost level.

**The capped (70%) variants do exactly what a real product would want** — `cap70_convex_step`
posts the shallowest drawdown of anything tested (**−29.20%**) — but at 9.23% CAGR.

---

## 9. The leverage ladder (QQQ / QLD / TQQQ)

Does composing exposure across 1x/2x/3x beat scaling one 3x fund against cash?

**Only if you hold long enough.** The ladder edge is a monotone function of holding
period, and it is *negative* at the trade frequencies these policies actually generate:

| Policy | Period | band 0.0 | band 0.3 | band 0.6 | band 1.0 |
|---|---|---:|---:|---:|---:|
| linear | SEARCH | −1.84% | −1.84% | −0.73% | −0.63% |
| linear | HOLDOUT | −0.62% | −0.62% | **+0.08%** | **+0.97%** |
| ema5 | SEARCH | −1.13% | −0.78% | −0.32% | −0.02% |
| ema5 | HOLDOUT | −0.30% | **+0.53%** | **+1.36%** | **+2.51%** |
| cap70_linear | HOLDOUT | +0.18% | +0.18% | **+1.21%** | **+1.20%** |

(Ladder CAGR minus pure-TQQQ CAGR. For **binary** policies the edge is exactly **0.00%** —
at L=3 the ladder holds 100% TQQQ, so the routes are identical by construction.)

Mechanism: switching between funds turns over more notional than adjusting one position
against cash, so at band 0 the extra trading cost exceeds the decay saved. As the band
widens and holds lengthen, the decay saving dominates. It also only pays in the holdout —
consistent with the lower-multiple route losing less in a crash.

**Verdict: the ladder is real but conditional and small.** It is worth implementing only
alongside a wide no-trade band, and it is not what separates these strategies from
buy-and-hold.

---

## 10. Regime churn and streak age

The signal is noisy in exactly the way sign-persistence logic exists to fix:

> **146 regime flips over 4,160 days (8.8/yr); 74 completed healthy runs; median run
> length 6 days; 36 of 74 runs (49%) last ≤5 days.**

Forward TQQQ return by age of the healthy streak (score ≥ 3):

| Streak age | days | **distinct runs** | fwd 1m | fwd 3m | t-inflation |
|---|---:|---:|---:|---:|---:|
| 1–5 | 254 | 74 | **+7.18%** | **+16.55%** | 1.85× |
| 6–20 | 440 | 38 | +6.72% | +12.06% | 3.40× |
| 21–60 | 699 | 21 | +2.03% | +5.55% | 5.77× |
| 61–120 | 544 | 14 | **−0.43%** | +3.80% | 6.23× |
| 121+ | 1344 | **6** | +4.07% | +11.74% | **14.97×** |

These are **overlapping daily observations, not independent draws**. Naive t-statistics
are inflated by ≈ √(days/runs) — the column above. The 121+ bucket rests on **6 distinct
runs**; it carries essentially no independent evidence and no t-stat from it should be
quoted.

**This kills the age-ramp idea.** Returns are best in the first ~20 days of a fresh
regime and worst at 61–120 days. Ramping leverage *up* with age holds you underweight
exactly when returns are strongest and fully weighted through the dead zone. Measured:
`age_ramp_T3` returns **11.53% / Sharpe 0.41** on the holdout — worse than binary_T2's
42.01% / 0.88 and worse than buy-and-hold. **Tested as asked; not recommended.**

Hysteresis is the better answer in principle — it suppresses flip-flopping without
delaying genuine entries, and `hyst_H3_L1` cuts trading to 2.1/yr on search while posting
the best filtered search Sharpe (0.96). But the (H,L) grid is fragile: across eight pairs
the holdout CAGR ranges from **−3.99%** (`hyst_H5_L2`) to **+38.75%** (`hyst_H2_L0`). That
spread across a small parameter grid is a fragility warning, not a tuning opportunity.

---

## 11. Year by year

`binary_T2` (best holdout config), ladder, next-open, 2bp:

| Year | Strategy | TQQQ B&H | QQQ B&H | SPY B&H | mean lev | vs TQQQ |
|---|---:|---:|---:|---:|---:|---:|
| 2010 | 50.86% | 78.06% | 24.71% | 16.30% | 2.50 | −27.20% |
| 2011 | −30.86% | −8.05% | 2.52% | −0.20% | 1.94 | −22.81% |
| 2012 | 44.78% | 52.29% | 16.66% | 13.47% | 2.99 | −7.50% |
| 2013 | 123.58% | 139.73% | 35.05% | 29.69% | 3.00 | −16.16% |
| 2014 | 53.40% | 57.04% | 17.38% | 11.29% | 2.93 | −3.64% |
| 2015 | −16.42% | 17.22% | 8.34% | −0.81% | 2.55 | −33.64% |
| 2016 | 21.47% | 11.38% | 5.92% | 9.64% | 2.49 | **+10.08%** |
| 2017 | 113.79% | 118.06% | 31.47% | 19.38% | 3.00 | −4.27% |
| 2018 | −19.09% | −19.90% | −0.96% | −6.35% | 2.46 | **+0.80%** |
| 2019 | 97.13% | 133.67% | 37.83% | 28.79% | 2.77 | −36.54% |
| **2020** | 129.58% | 110.05% | 47.57% | 16.16% | 2.56 | **+19.53%** |
| 2021 | 80.68% | 82.98% | 26.81% | 27.04% | 3.00 | −2.30% |
| **2022** | −60.49% | −79.20% | −33.07% | −19.48% | 0.78 | **+18.71%** |
| 2023 | 168.04% | 193.06% | 53.79% | 24.29% | 2.95 | −25.02% |
| **2024** | 60.35% | 56.07% | 24.84% | 23.30% | 3.00 | **+4.27%** |
| 2025 | 7.58% | 33.25% | 20.16% | 16.35% | 2.40 | −25.67% |
| 2026 (YTD) | 24.61% | 39.04% | 17.39% | 13.08% | 2.71 | −14.43% |

**It beats TQQQ buy-and-hold in 5 of 17 years.** The entire edge is 2020 (+19.53%) and
2022 (+18.71%). Twelve of seventeen years are a drag, several severely (2015 −33.64%,
2019 −36.54%, 2023 −25.02%, 2025 −25.67%).

Sub-period decomposition makes the dependence explicit:

| Window | binary_T2 | TQQQ B&H | Verdict |
|---|---|---|---|
| Holdout full (2020-01→2026-08) | 42.01% / 0.88 | 32.48% / 0.72 | filter wins |
| 2020–2021 only | 106.62% / 1.51 | 91.36% / 1.21 | filter wins (2020 crash) |
| 2021–2026 (drop 2020) | 31.30% / 0.73 | 24.12% / 0.61 | filter wins (2022) |
| **2023–2026 only (no crash)** | **62.77% / 1.12** | **81.27% / 1.21** | **filter loses** |

**The filter only wins in windows containing a major drawdown.** That is what a regime
filter is *for* — but it means the headline number is crash-contingent, not a general
edge, and a live record that begins in November 2023 (as Raincheck's does) is precisely
the window in which this kind of filter looks worst-to-neutral, not best.

On Raincheck's specific annual claims: measured 2024 = **+60.35%** and 2025 = **+7.58%**
for binary_T2, versus their claimed +37.83% and +57.24%. The 2025 direction is badly
wrong — 2025 was a year this construction lost 25.67% to buy-and-hold.

---

## 12. Cost sensitivity and execution timing

**Costs** (holdout CAGR):

| Policy | 0bp | 2bp | 5bp | 10bp | 20bp |
|---|---:|---:|---:|---:|---:|
| binary_T2 | 42.20% | 42.01% | 41.74% | 41.28% | 40.36% |
| binary_T3 | 25.40% | 25.13% | 24.73% | 24.06% | 22.74% |
| TB_binary_T1 | 41.92% | 41.77% | 41.53% | 41.13% | 40.35% |
| hyst_H3_L1 | 36.02% | 35.90% | 35.72% | 35.43% | 34.84% |
| linear | 22.72% | 21.60% | 19.93% | 17.21% | **11.94%** |
| convex_sq | 12.91% | 11.64% | 9.77% | 6.71% | **0.84%** |

Binary and hysteretic rules are genuinely near-frictionless — TQQQ is among the most
liquid ETFs in existence and ~6–11 trades/yr costs under 2%/yr even at a punitive 20bp.
**Costs are not what defeats this strategy.** Graded mappings without a band are a
different story.

**Execution timing** — next-open vs same-close MOC, CAGR gap:

| Policy | SEARCH | HOLDOUT | FULL |
|---|---:|---:|---:|
| binary_T2 | +1.46% | −2.70% | **+0.15%** |
| binary_T3 | +2.80% | −0.72% | +1.65% |
| linear | +1.60% | −0.37% | +1.09% |
| ema5 | +0.03% | −0.57% | +0.09% |
| hyst_H4_L2 | −0.29% | **+4.67%** | +2.18% |

The gap is small and **sign-inconsistent** — no systematic advantage either way, and
essentially nil over the full window for the headline rules. **The result is not an
artefact of execution timing.** (`hyst_H4_L2`'s +4.67% swing is another fragility signal
for that particular pair.)

---

## 13. Does the two-factor (Raincheck) version add or lose anything?

`TB_binary_T1` — **Trend + Breadth only, Credit/VIX/Utilities discarded**:

| | SEARCH | HOLDOUT |
|---|---|---|
| TB_binary_T1 (2 factors) | 32.58% / 0.85 / −53.09% | **41.77% / 0.86 / −61.09%** |
| binary_T2 (5 factors) | 36.03% / 0.92 / −51.92% | **42.01% / 0.88 / −64.83%** |

**The two-factor version does essentially as well as the five-factor version** — 41.77% vs
42.01% CAGR, 0.86 vs 0.88 Sharpe, and a *shallower* drawdown (−61.09% vs −64.83%), with
fewer trades (5.6 vs 6.5/yr). Credit, VIX and Utilities add nothing detectable here.

Given the earlier finding that raising the threshold makes things monotonically worse,
the most likely reading is that **Trend is doing nearly all the work** and the other four
factors are mostly adding noise and turnover. That is consistent with the enormous
published literature on the 200-day moving average, and inconsistent with the premise
that a *five*-factor composite is the source of the edge.

**Per the standing instruction:** the two-factor version reaching 41.77% CAGR / 0.86
Sharpe on the holdout is **not** evidence of a real edge and does not approach the claimed
+37.83%/+57.24%/2.37. It is the same crash-contingent result as the five-factor version,
selected from 198 configurations, on a window containing two of the largest leveraged-ETF
drawdowns on record.

---

## 14. The score is inverted at the daily horizon

| score | net | days | % days | next-day TQQQ mean | annualised |
|---|---:|---:|---:|---:|---:|
| 0 | −5 | 373 | 9.0% | **+0.4865%** | +239.7% |
| 1 | −3 | 198 | 4.8% | −0.0321% | −7.8% |
| 2 | −1 | 308 | 7.4% | +0.4060% | +177.6% |
| 3 | +1 | 556 | 13.4% | +0.4934% | +245.7% |
| 4 | +3 | 1272 | 30.6% | +0.1752% | +55.4% |
| 5 | +5 | 1452 | 34.9% | **+0.0674%** | +18.5% |

**The "most fragile" state has the highest forward return and the "healthiest" the
lowest.** This is the rebound effect: score-0 days cluster inside crashes, and leveraged
Nasdaq rebounds violently off crash lows.

This does *not* mean the score is useless — the low-score days also carry enormous
volatility, which is why filtering them improves Sharpe even while it costs return. But
it does mean **the score is a volatility signal, not a direction signal**, and any
marketing that describes it as identifying when the market will *go up* is describing
something the data does not support.

---

## 15. Verdict on the claims

| Claim | Measured, best case | Verdict |
|---|---|---|
| Kairos: **40.6% CAGR** (2020–26) | **42.01%** (binary_T2, holdout) | **Reachable** — but so is 32.48% by simply holding TQQQ, and this required picking the best of 198 configs after the fact |
| Kairos: **Sharpe 1.39** | **0.88** best of 198 | **Not reproduced.** Nothing tested came close |
| Kairos: **max DD −24.5%** | **−29.20%** shallowest, at 9.23% CAGR / Sharpe 0.36 | **Not reproduced, and not reachable.** No config achieved a shallow drawdown *and* a high return |
| Kairos: **~11 trades/yr** | 6.5–10.7/yr (binary), 46–250/yr (graded) | **Plausible for a binary rule** |
| Kairos: **$100K → $896K** | $1,023,508 (binary_T2) vs **$645,531 just holding TQQQ** | Multiple is achievable; the comparison to SPY's $237,356 is the misleading part |
| Raincheck: **+37.83% 2024** | +60.35% | Direction right (2024 was a strong year for everything) |
| Raincheck: **+57.24% 2025** | **+7.58%** | **Badly wrong.** 2025 lost 25.67% to buy-and-hold here |
| Raincheck: **Sharpe 2.37** | 0.88 | **Not reproduced** |

### The single most important number

**−24.5% max drawdown.** Holding a 3x leveraged Nasdaq fund at all through 2020 and 2022
and suffering only −24.5% peak-to-trough requires exiting within days of each top and
re-entering near each bottom. The best drawdown across 198 configurations was **−29.20%**,
and it came with a 9.23% CAGR. **A −24.5% drawdown paired with a 40.6% CAGR did not occur
anywhere in the search space.** If that pairing is real, it is not being produced by
anything resembling the five named factors applied to TQQQ.

### The honest summary

A five-factor regime filter on TQQQ is **crash insurance with a real and substantial
premium**. It cost 12 of 17 years of relative performance to pay for two good ones. On a
holdout deliberately aligned with the vendor's own claimed window it beat buy-and-hold —
but the rule that did so was **not selectable from the search period**, where buy-and-hold
beat all 198 configurations. Two factors do as well as five. The composite is inverted at
the daily horizon. And the claimed drawdown is out of reach.

**This does not replicate the sites' claims.** The return claim is attainable in a
favourable window by hindsight selection; the risk claims are not attainable at all.

---

## 16. Limitations

1. **Survivorship bias in Breadth** (§3) — biases breadth upward, flatters the strategy.
2. **Multiple testing** — 198 configurations were evaluated on the holdout. The best of
   198 is expected to look good by chance. This is why §7 (what search selects) is the
   load-bearing result, not the best holdout row.
3. **One market, one regime.** 2010–2026 contains one secular Nasdaq bull market with
   three interruptions. Sixteen years sounds long; it is roughly **three** independent
   drawdown events, and the strategy's entire value rests on those three.
4. **Credit is a substitute series** (§2b), validated on a 752-day overlap only.
5. **VIX same-day** — the MOC variant uses VIXCLS as a stand-in for the ~3:50pm value.
   The next-open variant, which is the primary, is unaffected.
6. **No dividends on the equity legs.** QQQ/SPY/XLU/QLD returns are price-only
   (split-adjusted), understating buy-and-hold benchmarks by roughly 0.5–1.8%/yr. **This
   biases *against* the benchmarks, i.e. in the strategy's favour** — the true comparison
   is slightly worse for the filter than reported here.
7. **BF-B and BRK-B** missing from the 503-name universe (dot-notation tickers); 501 of
   503 is immaterial for a percentage.

---

## 17. Files

| Path | Contents |
|---|---|
| `tools/kairos/extract_dumps.py` | Converts API dumps → per-symbol CSVs; drops interpolated bars |
| `tools/kairos/factors.py` | Factor construction, pre-registration notes, credit-substitution check |
| `tools/kairos/backtest.py` | Policies, routes, position engine, sweeps, exports |
| `data/kairos/BAA10Y.csv`, `VIXCLS.csv`, `DGS3MO.csv`, `BAMLH0A0HYM2.csv` | FRED, pulled 2026-08-29 |
| `data/kairos/etf/*.csv` | TQQQ, QQQ, QLD, SPY, XLU, BIL daily OHLC |
| `data/kairos/universe/*.csv` | 501 S&P 500 constituent close series |
| `data/kairos/factors.csv` | 4,160-day factor panel, raw values + booleans + score |
| `data/kairos/daily_series*.csv` | Per-day audit trail: raw factors, booleans, score, net_score, target/actual leverage, per-fund weights, traded flag, returns, equity curve, drawdown |

Reproduce with `python3 tools/kairos/factors.py && python3 tools/kairos/backtest.py`
(~20s, standard library only).

---

## Appendix: auditing Raincheck's 2025 claim against real prices (2026-08-29)

Raincheck published its four 2025 uptrend windows, including the losing ones. That makes
the year auditable rather than a filtered sample. Verified against `data/kairos/etf/`:

| leg | QQQ claimed | QQQ actual | TQQQ claimed | TQQQ actual |
|---|---|---|---|---|
| Jan 2 → Jan 8 | +0.79% | +0.99% | +1.96% | +2.61% |
| Jan 17 → Feb 28 | −2.60% | −2.60% | −9.89% | −9.89% |
| May 1 → Nov 18 | +23.80% | +23.80% | +73.26% | +73.26% |
| Nov 26 → Dec 31 | +0.01% | +0.01% | −1.22% | −1.22% |

Three of four legs match to the basis point; leg 1 differs by an entry-timing convention.
Compounding the four legs gives **+58.25%** against their claimed **+57.24%**.

**The claim verifies.** TQQQ buy-and-hold returned +34.10% in 2025, so the filter genuinely
beat it by roughly 23pp.

**This corrects an earlier statement in this session.** The line "2025 measured +7.58%
against their claimed +57.24% — badly wrong" conflated two different things: +7.58% was
*our* five-factor system's 2025 result, which says nothing about whether *their* number is
accurate. Theirs is accurate. Ours was worse.

### Where the edge came from — one crash

| period | TQQQ | position |
|---|---|---|
| Feb 28 → May 1 (tariff drawdown) | **−24.23%** | in cash — avoided |
| Jan 8 → Jan 17 | +3.05% | in cash — missed |
| Nov 18 → Nov 26 | +8.52% | in cash — missed |

The whole year's outperformance is one avoided drawdown, partly offset by ~11.6pp of
opportunity cost in the two flat gaps, plus two losing trades (+2.61%, −9.89%).

### But 2025 does not demonstrate a proprietary signal

Standard textbook trend rules over the same calendar year, compounded across their own
in-market runs, no costs:

| rule | runs | 2025 compounded |
|---|---|---|
| **Raincheck (published)** | 4 | **+57.24%** (verified +58.25%) |
| **20dma > 50dma crossover** | 3 | **+57.76%** |
| QQQ > 200dma | 2 | +46.06% |
| QQQ > 50dma | 8 | +93.80% |
| QQQ > 20dma | 16 | +186.20% (unusable turnover) |
| TQQQ buy-and-hold | — | +34.10% |

A 20/50 moving-average crossover — two lines of code, free, public since the 1970s —
returned **+57.76%** against Raincheck's +57.24%, and picked structurally similar windows
(Jan 2–Mar 5, May 13–Dec 8, Dec 17–31). QQQ > 50dma beat them outright.

So 2025 is a year in which *every* trend filter beat buy-and-hold, because it contained one
clean crash and one clean recovery — precisely the crash-contingent regime the 16-year study
above identifies as where this family wins. The 2025 result is real, and it is evidence
about the year rather than about the signal.
