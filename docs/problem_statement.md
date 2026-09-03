# Problem Statement — Bank Loan Report

A bank needs a reporting layer over its loan book to monitor lending activity, track
portfolio health, and spot trends that should feed into lending strategy. The
deliverable is three dashboards, each built on the same dataset.

---

## Dashboard 1 — Summary

### Headline KPIs

Each KPI is reported three ways: the all-time total, the month-to-date value, and the
month-over-month change against the previous month-to-date.

| KPI | Definition |
|---|---|
| Total Loan Applications | Count of loan applications received |
| Total Funded Amount | Total principal disbursed (`SUM(loan_amount)`) |
| Total Amount Received | Total repaid by borrowers (`SUM(total_payment)`) |
| Average Interest Rate | Mean interest rate across loans, shown as a percentage |
| Average Debt-to-Income Ratio | Mean DTI across borrowers, shown as a percentage |

### Good Loan vs Bad Loan

Loan quality is judged purely on `loan_status`:

- **Good Loan** — status is `Fully Paid` or `Current`
- **Bad Loan** — status is `Charged Off`

For each category, report: share of applications, application count, funded amount,
and amount received.

### Loan Status grid

One row per `loan_status`, with columns for total applications, total funded amount,
total amount received, MTD funded amount, MTD amount received, average interest rate
and average DTI.

## Dashboard 2 — Overview

Six visuals, each showing the same three measures — applications, funded amount and
amount received — broken down a different way.

| # | Visual | Dimension | Question it answers |
|---|---|---|---|
| 1 | Line chart | Month of `issue_date` | Is lending growing, and is there seasonality? |
| 2 | Filled map | `address_state` | Where is lending concentrated? |
| 3 | Donut chart | `term` | How do loans split across 36- vs 60-month terms? |
| 4 | Bar chart | `emp_length` | Does employment history correlate with borrowing? |
| 5 | Bar chart | `purpose` | Why are borrowers taking loans? |
| 6 | Tree map | `home_ownership` | How does housing status relate to lending? |

## Dashboard 3 — Details

A single flat table giving loan-level access to the portfolio: identifiers, purpose,
grade, home ownership, issue date, status, term, employment length, state,
verification status, income, DTI, interest rate, instalment, funded amount and amount
received. It exists so a user can drill from an aggregate straight to the underlying
rows.

## Cross-cutting requirements

- Every dashboard is filterable by `grade`, `sub_grade`, `purpose`, `term`,
  `home_ownership`, `verification_status`, `address_state` and a date range.
- All three dashboards are linked by navigation buttons.
- The same numbers must appear whichever tool is used — SQL, Python, Power BI, Excel
  or Tableau.

## Implementation notes

| Rule | Where enforced |
|---|---|
| MTD = latest month in the data; PMTD = the month before it | `kpis.latest_period()`, `sql/02_summary_kpis.sql` |
| `int_rate` and `dti` are decimal fractions — multiply by 100 exactly once | every layer |
| `issue_date` is day-first (`DD-MM-YYYY`) | `config.SOURCE_DATE_FORMAT`, `SET DATEFORMAT dmy` |
| Good/Bad rule lives in one place per layer | `config.GOOD_LOAN_STATUSES` |

The original requirements document, domain-knowledge brief and field glossary ship with
the original specification's data folder — see `data/README.md` for the link.
