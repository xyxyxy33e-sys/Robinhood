# data/kairos — sources and provenance

All data pulled **2026-08-29**. Backtest window **2010-02-11 → 2026-08-27** (TQQQ
inception → last complete session). Everything here is regenerable; see §Regenerating.

## FRED series (CSV endpoint, no API key)

`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>&cosd=2008-01-01&coed=2026-08-28`

| File | FRED ID | Description | Rows | Range |
|---|---|---|---|---|
| `BAA10Y.csv` | `BAA10Y` | Moody's Baa Corporate Bond Yield minus 10-Year Treasury. **The Credit factor actually used.** | 4868 | 2008-01-02 → 2026-08-27 |
| `VIXCLS.csv` | `VIXCLS` | CBOE Volatility Index, close | 4868 | 2008-01-02 → 2026-08-27 |
| `DGS3MO.csv` | `DGS3MO` | 3-Month Treasury constant-maturity rate. Used both as the cash leg and as the risk-free rate in every Sharpe ratio. | 4868 | 2008-01-02 → 2026-08-27 |
| `BAMLH0A0HYM2.csv` | `BAMLH0A0HYM2` | ICE BofA US High Yield OAS. **Retained only as a 3-year cross-check** — see below. | 796 | 2023-08-29 → 2026-08-27 |

### Why the specified HY series could not be used

The brief specified `BAMLH0A0HYM2`. FRED's CSV endpoint serves only a **rolling 3-year
window** for it — 796 rows beginning exactly 3 years before the pull date — **regardless
of the `cosd`/`coed` parameters**. Verified across three URL variants (bare id;
id+cosd+coed; full graph-parameter form): all returned 796 rows starting 2023-08-29. The
same holds for other ICE BofA series (`BAMLC0A0CM` → 796 rows), while non-ICE series on
the identical endpoint honour `cosd` and return full history. This is a licensing
restriction on ICE BofA proprietary index data, not a fetch failure. The alternate
`https://fred.stlouisfed.org/data/BAMLH0A0HYM2.txt` endpoint returned empty.

Three years cannot support a 16-year backtest, so **`BAA10Y` is substituted**. It is
validated against the restricted series over the 752-day overlap by
`tools/kairos/factors.py`, which prints on every run:

- level correlation **0.546**
- daily-change correlation **0.615**

`BAMLH0A0HYM2.csv` is retained so that check remains reproducible, and its values appear
in the `hy_oas` column of the daily series (blank before 2023-08-29).

## Price data

Source: `mcp__robinhood__get_equity_historicals`, `interval='day'`,
`adjustment_type='split'`, `bounds='regular'`, from `2009-01-01`.

**Split-adjusted, NOT dividend-adjusted.** Equity-leg returns are price-only, which
understates the buy-and-hold benchmarks by roughly 0.5–1.8%/yr. This biases *against* the
benchmarks — i.e. in the strategy's favour — so the true comparison is slightly worse for
the regime filter than reported.

| Directory | Contents |
|---|---|
| `etf/` | `TQQQ`, `QQQ`, `QLD`, `SPY`, `XLU`, `BIL` — daily `d,o,c` (open kept because the primary execution assumption fills at the next open) |
| `universe/` | 501 S&P 500 constituent close series (`d,c`), used only for the Breadth factor |

### Interpolated bars are dropped

The API returns bars back to 2009-01-02 for every symbol, including ones that did not yet
exist. Those carry `interpolated: true`, `volume: 0`, and identical OHLC. For TQQQ, 280
such bars precede its real inception. `tools/kairos/extract_dumps.py` drops every
interpolated bar; **TQQQ's first real bar is 2010-02-11**, matching its actual inception.
Retaining them would have fabricated a flat 2009 price history.

### Universe caveats

- Membership is **today's** S&P 500 (`data/sp500_members.csv`, retrieved 2026-08-28), not
  point-in-time. Breadth is therefore **survivorship-biased upward**. Documented in the
  write-up; not fixable without point-in-time membership data.
- `BF-B` and `BRK-B` were not resolvable (dot-notation tickers) — 501 of 503 names, which
  is immaterial for a percentage. Symbols with genuinely later listing dates (GEV, SOLV,
  RDDT, SNDK, SW, …) enter the breadth denominator only once they have 200 prior closes.
- `QLD.csv` was supplied by the coordinator as `d,c`; it was re-pulled to obtain opens.
  The two agree exactly — **0 mismatches across all 4,168 common rows**.

## Generated files

| File | Produced by |
|---|---|
| `factors.csv` | `tools/kairos/factors.py` — 4,160-day panel: raw factor values + booleans + score |
| `daily_series*.csv` | `tools/kairos/backtest.py` — per-policy audit trail (raw factors, booleans, score, net_score, target/actual leverage, per-fund weights, traded flag, returns, equity curve, drawdown) |

## Regenerating

```sh
python3 tools/kairos/extract_dumps.py   # only if raw API dumps are still present
python3 tools/kairos/factors.py         # -> factors.csv
python3 tools/kairos/backtest.py        # -> daily_series*.csv + all result tables
```

Standard library only (no numpy/pandas in this environment); ~20s total.
