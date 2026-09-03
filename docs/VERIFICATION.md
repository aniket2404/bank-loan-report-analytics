# Verification Report

Every number below was produced by running this repository against the full
`financial_loan.csv` dataset (38,576 rows) on the date of platform implementation, using:

```bash
python -m bank_loan_report validate
python -m bank_loan_report report
python -m bank_loan_report insights
python -m bank_loan_report charts
python -m bank_loan_report export
ruff check src tests
pytest -q
```

These are the reference values for cross-checking the Power BI, Excel and Tableau
rebuilds. If your dashboard disagrees with this table, the dashboard is wrong.

---

## Environment checks

| Check | Result |
|---|---|
| `pip install -r requirements.txt` | ✅ succeeds |
| `pip install -r requirements-dev.txt` | ✅ succeeds |
| `python -m bank_loan_report validate` | ✅ 9 PASS, 2 WARN, 2 INFO, 0 blocking failures, exit code 0 |
| `python -m bank_loan_report report` | ✅ runs, exit code 0 |
| `python -m bank_loan_report insights` | ✅ prints all 12 risk tables, exit code 0 |
| `python -m bank_loan_report charts` | ✅ writes 10 PNGs to `reports/figures/` (6 Overview + 4 risk) |
| `python -m bank_loan_report charts --risk-only` | ✅ writes the 4 risk PNGs |
| `python -m bank_loan_report export` | ✅ writes 21 CSVs to `reports/tables/` (9 KPI + 12 risk) |
| `python -m bank_loan_report quality` | ✅ per-column profile, exit code 0 |
| All six subcommands on `--sample` | ✅ exit code 0 on the bundled 600-row sample; sample output is written to `reports/sample/` and cannot overwrite the published figures |
| Committed figures — visual inspection | ✅ all 10 PNGs opened and read individually against `docs/INSIGHTS.md`; axis magnitudes confirm the full 38,576-row dataset (e.g. `01_monthly_trend` runs 2,332 → 4,314 applications and $25.0M → $54.0M funded). This check is required, not optional — see `AUDIT.md` P1-9 |
| `ruff check src tests` | ✅ no violations |
| `pytest` | ✅ **123 passed, 4 skipped** — the 4 skips are exact-figure SQL assertions that require an MTD window the scripts do not compute; they are deliberate, not failures |
| Notebook `notebooks/01_bank_loan_analysis.ipynb` | ✅ executes top to bottom via nbconvert |
| Imports / file paths | ✅ package imports cleanly as `bank_loan_report` |
| SQL scripts — static validation | ✅ all 6 files parse as T-SQL via `sqlglot` (split on `GO`), plus text assertions on casing, `DATEFORMAT`, derived period boundaries, volume floors and absence of destructive verbs (`tests/test_sql.py`) |
| SQL scripts — execution | ⚠️ **not executed** — no SQL Server instance was available in the build environment. See "Known limitations". |
| Secret scan | ✅ no credentials, tokens, keys, connection strings or `.env` file in the tree; `.env.example` holds placeholders only |

## Dataset facts

| Property | Value |
|---|---|
| Rows | 38,576 |
| Columns | 24 |
| Distinct `id` | 38,576 (no duplicates) |
| `issue_date` range | 2021-01-01 → **2021-12-12** |
| Nulls | 1,438 in `emp_title` only (3.7%); every other column complete |
| `loan_status` values | `Fully Paid`, `Current`, `Charged Off` |
| MTD period | December 2021 |
| PMTD period | November 2021 |

## Dashboard 1 — Summary KPIs

| KPI | Total | MTD | PMTD | MoM |
|---|---|---|---|---|
| Total Loan Applications | 38,576 | 4,314 | 4,035 | +6.91% |
| Total Funded Amount | $435,757,075 | $53,981,425 | $47,754,825 | +13.04% |
| Total Amount Received | $473,070,933 | $58,074,380 | $50,132,030 | +15.84% |
| Average Interest Rate | 12.05% | 12.36% | 11.94% | +3.47% |
| Average DTI | 13.33% | 13.67% | 13.30% | +2.73% |

## Good Loan vs Bad Loan

| Category | Share | Applications | Funded Amount | Amount Received |
|---|---|---|---|---|
| Good Loan (`Fully Paid`, `Current`) | 86.18% | 33,243 | $370,224,850 | $435,786,170 |
| Bad Loan (`Charged Off`) | 13.82% | 5,333 | $65,532,225 | $37,284,763 |

## Loan Status grid

| Loan Status | Applications | Funded | Received | MTD Funded | MTD Received | Avg Int Rate | Avg DTI |
|---|---|---|---|---|---|---|---|
| Charged Off | 5,333 | $65,532,225 | $37,284,763 | $8,732,775 | $5,324,211 | 13.88% | 14.00% |
| Current | 1,098 | $18,866,500 | $24,199,914 | $3,946,625 | $4,934,318 | 15.10% | 14.72% |
| Fully Paid | 32,145 | $351,358,350 | $411,586,256 | $41,302,025 | $47,815,851 | 11.64% | 13.17% |

## Dashboard 2 — Overview

### Monthly trend

| Month | Applications | Funded | Received |
|---|---|---|---|
| Jan | 2,332 | $25,031,650 | $27,578,836 |
| Feb | 2,279 | $24,647,825 | $27,717,745 |
| Mar | 2,627 | $28,875,700 | $32,264,400 |
| Apr | 2,755 | $29,800,800 | $32,495,533 |
| May | 2,911 | $31,738,350 | $33,750,523 |
| Jun | 3,184 | $34,161,475 | $36,164,533 |
| Jul | 3,366 | $35,813,900 | $38,827,220 |
| Aug | 3,441 | $38,149,600 | $42,682,218 |
| Sep | 3,536 | $40,907,725 | $43,983,948 |
| Oct | 3,796 | $44,893,800 | $49,399,567 |
| Nov | 4,035 | $47,754,825 | $50,132,030 |
| Dec | 4,314 | $53,981,425 | $58,074,380 |

Applications and both amounts rise monotonically from February onwards.

### Term

| Term | Applications | Funded | Received |
|---|---|---|---|
| 36 months | 28,237 (73.2%) | $273,041,225 | $294,709,458 |
| 60 months | 10,339 (26.8%) | $162,715,850 | $178,361,475 |

### Top states by funded amount

| State | Applications | Funded | Received |
|---|---|---|---|
| CA | 6,894 | $78,484,125 | $83,901,234 |
| NY | 3,701 | $42,077,050 | $46,108,181 |
| TX | 2,664 | $31,236,650 | $34,392,715 |

50 states in total.

### Home ownership

| Category | Applications | Funded | Received |
|---|---|---|---|
| RENT | 18,439 | $185,768,475 | $201,823,056 |
| MORTGAGE | 17,198 | $219,329,150 | $238,474,438 |
| OWN | 2,838 | $29,597,675 | $31,729,129 |
| OTHER | 98 | $1,044,975 | $1,025,257 |
| NONE | 3 | $16,800 | $19,053 |

### Employment length

| Bucket | Applications | Funded | Received |
|---|---|---|---|
| < 1 year | 4,575 | $44,210,625 | $47,545,011 |
| 1 year | 3,229 | $32,883,125 | $35,498,348 |
| 2 years | 4,382 | $44,967,975 | $49,206,961 |
| 3 years | 4,088 | $43,937,850 | $47,551,832 |
| 4 years | 3,428 | $37,600,375 | $40,964,850 |
| 5 years | 3,273 | $36,973,625 | $40,397,571 |
| 6 years | 2,228 | $25,612,650 | $27,908,658 |
| 7 years | 1,772 | $20,811,725 | $22,584,136 |
| 8 years | 1,476 | $17,558,950 | $19,025,777 |
| 9 years | 1,255 | $15,084,225 | $16,516,173 |
| 10+ years | 8,870 | $116,115,950 | $125,871,616 |

### Top purposes

| Purpose | Applications | Funded | Received |
|---|---|---|---|
| Debt consolidation | 18,214 | $232,459,675 | $253,801,871 |
| credit card | 4,998 | $58,885,175 | $65,214,084 |
| other | 3,824 | $31,155,750 | $33,289,676 |

Note the inconsistent capitalisation in the source data (`Debt consolidation` vs
`credit card`) — it is preserved rather than silently corrected.

## Risk layer reference numbers

Added after the original platform implementation. Produced by `risk.py`, asserted by
`tests/test_risk.py`, and explained in `docs/INSIGHTS.md`.

| Measure | Value |
|---|---|
| Net cash margin (received − funded) | +$37,313,858 |
| Portfolio recovery rate | 108.56% |
| Default rate — all loans | 13.8247% |
| Default rate — closed loans only (n=37,478) | 14.2297% |
| Open book still amortising | 2.85% |
| Recovery on charged-off loans | 56.90% |
| Net cash lost to charge-offs | $28,247,462 |
| Charge-off loss as share of funded | 6.48% |
| Default rate by grade A → G | 5.70 / 11.50 / 16.02 / 20.69 / 24.80 / 30.25 / 31.31 % |
| Avg interest rate by grade A → G | 7.35 / 11.03 / 13.55 / 15.71 / 17.71 / 19.74 / 21.40 % |
| Default rate 36 mo vs 60 mo | 10.71% vs 22.34% (2.09×) |
| Worst term × grade segment (closed, ≥100 loans) | 60 months grade F — 34.22% on 751 loans (2.40×) |
| Best term × grade segment | 36 months grade A — 5.57% on 9,274 loans (0.39×) |
| Term × grade segments clearing the 100-loan floor | 13 |
| Pricing power across 35 sub-grades (≥20 loans) | Spearman ρ = 0.9585, Pearson r = 0.9337 |
| Only loss-making purpose | small business — 1,776 loans, 25.62% default, 98.72% recovery, −$308,283 |
| Concentration — CA / top-3 / top-10 states (of 50) | 18.01% / 34.84% / 64.94% of funded |
| Concentration — Debt consolidation / top-3 purposes | 53.35% / 74.51% of funded |
| Income quintile default Q1 → Q5 | 17.04 / 14.90 / 14.47 / 12.20 / 10.50 % (monotonic) |
| Growth Jan → Dec | applications +85.0%, funded +115.7% |

## Cross-checks Against Reference Benchmarks

Values stated on screen in the video match this platform implementation:

| Figure | Reference | This Platform |
|---|---|---|
| Row count | 38,576 | 38,576 ✅ |
| Total funded amount | $435.76M | $435,757,075 ✅ |
| MTD funded amount | $53.98M | $53,981,425 ✅ |
| Total amount received | $473.07M | $473,070,933 ✅ |
| MTD applications (Dec) | 4,314 | 4,314 ✅ |
| Average interest rate | ~12.05% | 12.0488% ✅ |
| Average DTI | 13.33% | 13.3274% ✅ |
| Bad loan applications | 5,333 | 5,333 ✅ |
| Bad loan share | 13.82% | 13.8247% ✅ |
| Good loan share | ~86% | 86.1753% ✅ |

## Known limitations

1. **SQL scripts are not executed in CI.** They were written for Microsoft SQL Server,
   but no SQL Server instance existed in the build environment. Two mitigations are in
   place, and neither is a substitute for running them: (a) `tests/test_sql.py` parses
   every script as T-SQL with `sqlglot` and text-asserts its structure, which catches
   syntax errors, mis-cased status literals, hard-coded period boundaries and missing
   `SET DATEFORMAT dmy`; (b) the analytical logic of `sql/06` section 7 is reimplemented
   in `risk.term_grade_risk` and the figures written into the SQL comments are asserted
   against it by `test_term_grade_risk_matches_sql_06_section_7`. Static parsing is not
   execution. **NEEDS VERIFICATION: run `sql/01`–`sql/06` against a real SQL Server
   instance and confirm the result sets match this document.**
2. **The three dashboard binaries (`.pbix`, `.xlsx`, `.twbx`) are not in this repo.**
   They cannot be extracted from a video recording. What is provided instead is a
   complete build specification per tool — every DAX measure, every Tableau
   calculated field, every pivot table and every visual with its fields — plus the
   reference numbers above to validate the result. **NEEDS VERIFICATION: the exact
   pixel layout, colour hex codes, fonts and background images of the original
   dashboards.** The narrated colour values in the recording were not reliably
   recoverable.
3. **`term` values in the raw CSV carry a leading space.** Handled in both the Python
   cleaning step and the SQL view; watch for it if you connect a BI tool directly to
   the raw table.
4. **The full dataset is not committed.** Only a 600-row sample is included. See
   `data/README.md` for the download link. Exact-figure tests are marked
   `requires_full` and skip themselves when the CSV is absent, so CI verifies structure
   and business rules on the sample while the figures above are asserted locally.
5. **Two dataset defects are open and will not be fixed.** 15,453 rows (40.1%) have a
   `last_payment_date` earlier than their `issue_date`, and 100% of Fully Paid 36-month
   loans appear to close within a year (median 3 days). They are reported as `WARN` by
   the validation suite on every run and documented with their analytical consequences
   in `docs/DATA_QUALITY.md`. They rule out all vintage, seasoning and time-to-default
   analysis. No KPI in this document reads the affected columns.
