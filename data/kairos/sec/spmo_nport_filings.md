# SPMO NPORT-P filing index

Series S000050154 (Invesco S&P 500 Momentum ETF), within Invesco Exchange-Traded
Fund Trust II (CIK 1378872). Pulled 2026-08-29 via EDGAR — not parsed, index only.

Source: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000050154&type=NPORT-P&dateb=&owner=include&count=40

27 filings, monthly-ish, 2020-01-29 through 2026-07-28. Document folder for any
accession: https://www.sec.gov/Archives/edgar/data/1378872/<accession-no-dashes>/

| filing_date | accession_number |
|---|---|
| 2026-07-28 | 0001378872-26-001362 |
| 2026-04-28 | 0001378872-26-000821 |
| 2026-01-29 | 0001378872-26-000328 |
| 2025-10-30 | 0001378872-25-000401 |
| 2025-07-28 | 0001752724-25-180531 |
| 2025-04-25 | 0001752724-25-091932 |
| 2025-01-28 | 0001752724-25-017721 |
| 2024-10-28 | 0001752724-24-240580 |
| 2024-07-29 | 0001752724-24-169075 |
| 2024-04-25 | 0001752724-24-089930 |
| 2024-01-29 | 0001752724-24-016884 |
| 2023-10-30 | 0001752724-23-242006 |
| 2023-07-28 | 0001752724-23-166926 |
| 2023-05-01 | 0001752724-23-092062 |
| 2023-01-30 | 0001752724-23-017306 |
| 2022-10-31 | 0001752724-22-243740 |
| 2022-07-29 | 0001752724-22-170575 |
| 2022-04-26 | 0001752724-22-093512 |
| 2022-01-31 | 0001752724-22-018016 |
| 2021-10-29 | 0001752724-21-231935 |
| 2021-07-30 | 0001752724-21-161170 |
| 2021-04-29 | 0001752724-21-088207 |
| 2021-01-29 | 0001752724-21-016818 |
| 2020-10-30 | 0001752724-20-219852 |
| 2020-07-30 | 0001752724-20-148736 |
| 2020-04-28 | 0001752724-20-082966 |
| 2020-01-29 | 0001752724-20-015634 |

## Not yet done

- **Holdings not parsed.** Each accession is an XML NPORT-P with position-level
  detail (ticker, shares, market value, weight). None has been fetched or parsed
  into a usable table — this file is the index only.
- **2016-2019 cohorts (N-CSR/N-CSRS) not indexed.** NPORT-P only exists from 2020
  onward; the SPMO Mirror Study's earlier cohorts came from annual reports filed
  under the trust-level CIK (1378872), which have not been located here.
- The Robinhood MCP `get_sec_filing_index` tool does not reach this data for SPMO
  — querying it by symbol returns only unrelated 13F-NT institutional-ownership
  notices. This index was built via `WebFetch` on the EDGAR company-browse pages
  directly, keyed to the series ID, not the trust CIK.
