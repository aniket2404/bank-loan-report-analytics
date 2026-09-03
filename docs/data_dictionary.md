# Data Dictionary

Source file: `financial_loan.csv` — **38,576 rows × 24 columns**, one row per loan.
All loans were issued during calendar year 2021 (2021-01-01 → 2021-12-12; the last 19 days of December contain no originations).

## Source columns

| Column | Type | Description | Notes |
|---|---|---|---|
| `id` | int | Unique loan identifier | Primary key; 38,576 distinct values |
| `member_id` | int | Unique borrower identifier | |
| `address_state` | text | Two-letter US state code of the borrower | 50 distinct values |
| `application_type` | text | Application type | `INDIVIDUAL` only in this dataset |
| `emp_length` | text | Length of employment | 11 buckets, `< 1 year` → `10+ years` |
| `emp_title` | text | Borrower's job title | **1,438 nulls (3.7%)** — not used in any KPI |
| `grade` | text | Credit risk grade | `A`–`G` |
| `sub_grade` | text | Finer risk grade | e.g. `C4`, `E1` |
| `home_ownership` | text | Housing status | `RENT`, `MORTGAGE`, `OWN`, `OTHER`, `NONE` |
| `issue_date` | date | Loan origination date | Stored as `DD-MM-YYYY` text in the CSV |
| `last_credit_pull_date` | date | Last credit report pull | `DD-MM-YYYY` |
| `last_payment_date` | date | Most recent payment received | `DD-MM-YYYY` |
| `next_payment_date` | date | Expected next payment | `DD-MM-YYYY` |
| `loan_status` | text | Current loan state | `Fully Paid`, `Current`, `Charged Off` |
| `purpose` | text | Stated reason for the loan | 14 categories |
| `term` | text | Repayment period | `36 months`, `60 months` — **values have a leading space** |
| `verification_status` | text | Income verification outcome | `Verified`, `Source Verified`, `Not Verified` |
| `annual_income` | float | Borrower's yearly income (USD) | |
| `dti` | float | Debt-to-income ratio | **Decimal fraction** — multiply by 100 to display as % |
| `installment` | float | Fixed monthly payment (USD) | |
| `int_rate` | float | Annual interest rate | **Decimal fraction** — multiply by 100 to display as % |
| `loan_amount` | int | Principal disbursed (USD) | The "funded amount" measure |
| `total_acc` | int | Total credit accounts held by the borrower | |
| `total_payment` | int | Total repaid to date (USD) | The "amount received" measure |

## Derived columns

Added by `clean_loans()` in Python and by the SQL view `dbo.vw_bank_loan_enriched`.

| Column | Definition |
|---|---|
| `issue_year` | `YEAR(issue_date)` |
| `issue_month` | `MONTH(issue_date)` — used as the sort key for month names |
| `issue_month_name` | Full month name, e.g. `December` |
| `issue_month_short` | Three-letter month, e.g. `Dec` |
| `loan_quality` | `Good Loan` when `loan_status IN ('Fully Paid','Current')`, else `Bad Loan` |
| `term_clean` | `term` with surrounding whitespace trimmed (SQL view only) |

## Two traps worth knowing

1. **Dates are day-first.** `issue_date` values like `11-02-2021` mean 11 February
   2021, not 2 November 2021. A tool defaulting to a US locale will mis-parse them
   and silently break every MTD/PMTD figure. Python uses an explicit
   `format="%d-%m-%Y"`; SQL Server needs `SET DATEFORMAT dmy`; Power BI and Excel need
   "using locale → English (United Kingdom)".
2. **`int_rate` and `dti` are fractions, not percentages.** `0.1527` is 15.27%.
   Multiply by 100 exactly once — if you multiply *and* apply a percentage number
   format, values will be 100× too large.

## Business rules

| Term | Definition |
|---|---|
| Good Loan | `loan_status IN ('Fully Paid', 'Current')` |
| Bad Loan | `loan_status = 'Charged Off'` |
| Funded Amount | `SUM(loan_amount)` |
| Amount Received | `SUM(total_payment)` |
| MTD | The latest month present in the data — December 2021 for this dataset |
| PMTD | The month immediately before MTD — November 2021 |
| MoM | `(MTD − PMTD) / PMTD` |
