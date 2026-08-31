# SPMO top-15 holdings

As reported in the NPORT-P filing for the period ending **2026-05-31**
(filed 2026-07-28, accession `0001378872-26-001362`). Parsed directly from the filing's
`primary_doc.xml`; not hand-transcribed or estimated.

Total net assets: **$19,940,968,240**. 102 total holdings.
Top-15 concentration: **63.40%** of net assets.

| rank | ticker | name | % of net assets | value (USD) |
|---|---|---|---|---|
| 1 | MU | Micron Technology, Inc. | 10.73% | $2,134,655,139 |
| 2 | NVDA | NVIDIA Corp. | 8.46% | $1,683,304,149 |
| 3 | AVGO | Broadcom Inc. | 7.58% | $1,508,266,480 |
| 4 | GOOGL | Alphabet Inc. | 4.81% | $957,081,110 |
| 5 | AMD | Advanced Micro Devices, Inc. | 4.14% | $824,045,000 |
| 6 | JNJ | Johnson & Johnson | 3.85% | $766,551,028 |
| 7 | GOOG | Alphabet Inc. | 3.82% | $759,016,136 |
| 8 | LRCX | Lam Research Corp. | 3.54% | $703,885,750 |
| 9 | INTC | Intel Corp. | 2.95% | $587,772,500 |
| 10 | XOM | Exxon Mobil Corp. | 2.78% | $553,035,325 |
| 11 | CAT | Caterpillar Inc. | 2.60% | $517,880,910 |
| 12 | SNDK | Sandisk Corp. | 2.46% | $489,389,880 |
| 13 | CSCO | Cisco Systems, Inc. | 2.02% | $401,815,168 |
| 14 | STX | Seagate Technology Holdings PLC | 1.88% | $374,487,750 |
| 15 | AMAT | Applied Materials, Inc. | 1.77% | $352,830,388 |

Alphabet appears as two separate share classes (GOOGL Class A and GOOG Class C) — this is
how the S&P 500 index itself, and therefore SPMO's momentum-weighted tracking, holds it;
it is not a duplicate entry.

NPORT-P does not carry ticker symbols natively (only CUSIP/ISIN/LEI) — tickers above are
hand-mapped from company name and CUSIP for the top 15 only. The full 102-holding parse,
unmapped, is in `spmo_holdings_2026-05-31.csv` in this directory.

Source: https://www.sec.gov/Archives/edgar/data/1378872/000137887226001362/primary_doc.xml
