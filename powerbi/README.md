# Power BI Layer — Build Guide

The `.pbix` binary cannot be reconstructed from a video, so this folder contains
everything needed to rebuild the report from scratch: the DAX, the model, and a
page-by-page visual specification.

**Files**
- `calendar_table.dax` — the date dimension expression
- `measures.dax` — all 32 measures (totals, MTD, PMTD, MoM, good/bad loan, dynamic switch)
- `power_query_steps.md` — the transformation steps applied in Power Query

---

## 1. Connect the data

Two supported paths:

| Path | How | When to use |
|---|---|---|
| SQL Server (as in the standard) | Home → Get data → SQL Server → server `localhost`, database `bank_loan_db` → select view `vw_bank_loan_enriched` → **Import** | Recommended; the derived columns already exist in the view |
| CSV | Home → Get data → Text/CSV → `data/raw/financial_loan.csv` | No SQL Server installed |

Use **Import** mode, not DirectQuery — the MTD/PMTD time-intelligence measures need it.

## 2. Transform

Apply the steps in `power_query_steps.md` (date parsing, trimming `term`,
type assignment, column profiling).

## 3. Build the model

1. Create the date table from `calendar_table.dax`.
2. Mark it as a date table on the `Date` column.
3. Create the relationship `date_table[Date]` **1 → \*** `bank_loan_data[issue_date]`,
   single cross-filter direction.
4. Create the disconnected `measure_selection` table (see section 7 of `measures.dax`).
5. Paste in all measures from `measures.dax`.

## 4. Report pages

### Page 1 — Summary

| Element | Visual | Fields |
|---|---|---|
| KPI cards (row 1) | Card ×3 | `Total Loan Applications`, `Total Funded Amount`, `Total Amount Received` — each with MTD and MoM in a subtitle/multi-row card |
| KPI cards (row 2) | Card ×2 | `Avg Interest Rate`, `Avg DTI` (+ MTD and MoM) |
| Good Loan panel | Donut/gauge + 3 cards | `Good Loan Percentage`, `Good Loan Applications`, `Good Loan Funded Amount`, `Good Loan Amount Received` |
| Bad Loan panel | Donut/gauge + 3 cards | `Bad Loan Percentage`, `Bad Loan Applications`, `Bad Loan Funded Amount`, `Bad Loan Amount Received` |
| Loan Status grid | Matrix | Rows `loan_status`; Values `Total Loan Applications`, `Total Funded Amount`, `Total Amount Received`, `MTD Funded Amount`, `MTD Amount Received`, `Avg Interest Rate`, `Avg DTI` |

### Page 2 — Overview

| # | Visual | Axis / Category | Value |
|---|---|---|---|
| 1 | Line chart | `date_table[Month Short]` | `Selected Measure` |
| 2 | Filled map | `address_state` | `Selected Measure` |
| 3 | Donut chart | `term_clean` | `Selected Measure` |
| 4 | Bar chart | `emp_length` | `Selected Measure` |
| 5 | Bar chart | `purpose` | `Selected Measure` |
| 6 | Tree map | `home_ownership` | `Selected Measure` |

A slicer on `measure_selection[Measure Name]` drives all six visuals at once.

### Page 3 — Details

A single Table visual with: `id`, `purpose`, `home_ownership`, `grade`, `sub_grade`,
`issue_date`, `loan_status`, `term_clean`, `emp_length`, `address_state`,
`verification_status`, `annual_income`, `dti`, `int_rate`, `installment`,
`loan_amount`, `total_payment`.

### Slicers (present on all three pages)

`grade`, `sub_grade`, `purpose`, `term_clean`, `home_ownership`,
`verification_status`, `address_state`, and a date-range slicer on `date_table[Date]`.
Use Sync slicers so the selection carries across pages.

### Navigation

Three buttons (blank buttons with text) on every page — SUMMARY / OVERVIEW / DETAILS.
Set Action → Type: *Page navigation* → Destination: the target page.

## 5. Expected numbers

Validate the report against `docs/VERIFICATION.md`. The Summary page should show
38,576 applications, $435.76M funded, $473.07M received, 12.05% average interest
rate and 13.33% average DTI, with a 86.18% / 13.82% good-vs-bad split.
