# Interview Guide — Bank Loan Report

How to talk about this repository in a job interview, honestly and precisely.

Every number quoted below was produced by running this repository against the full
`data/raw/financial_loan.csv` (38,576 rows). Every claim points at the file that
backs it, so you can open the file on screen if you are asked to prove it.

Ground rules for using this guide:

1. **Never quote a number that is not in `docs/VERIFICATION.md` or this file.** If you
   are unsure, say "I would have to check the export in `reports/tables/`".
2. **The dashboard structure came from a banking standard, and you say so if asked.** See
   "Was this from a banking standard?" in the Difficult questions section. The defensible part
   of your contribution is the extension layer: `src/bank_loan_report/risk.py`,
   `sql/06_risk_and_cohort_analysis.sql`, `src/bank_loan_report/validate.py`, the four
   risk charts in `src/bank_loan_report/risk_charts.py`, and the 123-test suite.
3. **When the repository cannot support an answer, say so.** Several answers below end
   with the sentence "This cannot currently be defended from the repository." Use that
   phrasing (or your own honest version of it) rather than improvising. Interviewers
   test the boundary of what you actually know; a clean "not verified, and here is what
   it would take to verify it" scores better than a bluff.

---

## Table of contents

- [Project in 60 seconds](#project-in-60-seconds)
- [Project in 5 minutes](#project-in-5-minutes)
- [Technical questions and answers](#technical-questions-and-answers)
  - [SQL](#sql)
  - [Data cleaning](#data-cleaning)
  - [Python and pandas](#python-and-pandas)
  - [Visualisation](#visualisation)
  - [Power BI and DAX](#power-bi-and-dax)
  - [Tableau](#tableau)
  - [Excel](#excel)
  - [Data modelling](#data-modelling)
  - [Validation and testing](#validation-and-testing)
  - [CI](#ci)
- [Difficult questions](#difficult-questions)
- [Questions you should ask them](#questions-you-should-ask-them)
- [Red flags to avoid saying](#red-flags-to-avoid-saying)

---

## Project in 60 seconds

Spoken script. Roughly 55–65 seconds at a normal pace. Learn the shape, not the words.

> "It is a lending analytics project on a portfolio of 38,576 loans — about
> 436 million dollars funded and 473 million received back.
>
> The data lands in SQL Server, where five T-SQL scripts build the table, the views and
> the KPI queries that feed three dashboards: a Summary page with headline KPIs and
> month-to-date comparisons, an Overview page with six breakdowns, and a Details table.
> The same KPIs are re-implemented in a tested Python package so the numbers can be
> reconciled tool-to-tool, and the dashboards themselves are specified for Power BI,
> Tableau and Excel — DAX measures, Tableau calculated fields and pivot definitions.
>
> The part I would want to talk about is the layer on top. The dashboards answer *how
> much we lent*. They do not answer *whether the lending was any good*. So I added a
> risk and profitability module, a second SQL script using CTEs and window functions,
> and an executable data-validation suite. That is where the findings came from: the
> book recovers 108.6 percent of principal overall but only 56.9 percent on charged-off
> loans; the default rate runs 5.7 percent in grade A to 31.3 percent in grade G; the
> 60-month term is twice as risky as the 36-month term inside every grade; and
> small-business lending is the only one of fourteen purposes that loses cash.
>
> The whole thing is unit tested — 123 tests — and runs in GitHub Actions."

If they only let you say one sentence, say this one:

> "Three dashboards over one 38,576-loan book, rebuilt in SQL and Python so the numbers
> reconcile, plus a risk layer I added that finds where the portfolio actually loses
> money."

---

## Project in 5 minutes

### 1. Business problem

A lender needs a reporting layer over its loan book: monitor origination volume, track
portfolio health, and feed trends back into lending strategy. The requirement is written
out in `docs/problem_statement.md` as three dashboards.

- **Summary** — five headline KPIs, each reported three ways (all-time total,
  month-to-date, and month-over-month against the previous month-to-date), plus a Good
  Loan vs Bad Loan block and a grid by loan status.
- **Overview** — six visuals, each showing the same three measures broken down a
  different way: month, state, term, employment length, purpose, home ownership.
- **Details** — one flat loan-level table so a user can drill from an aggregate to the
  underlying rows.

Cross-cutting requirements: every page filterable by grade, sub-grade, purpose, term,
home ownership, verification status, state and date range; navigation between pages; and
**the same numbers whichever tool is used**. That last requirement is the interesting
engineering constraint — it is why the repository has five implementations of the same
KPI set and a test suite that pins them together.

The extension I layered on top asks a second question the brief does not: *is this book
profitable, and where is the risk concentrated?* That is
`src/bank_loan_report/risk.py` and `sql/06_risk_and_cohort_analysis.sql`.

### 2. Data

One CSV, `financial_loan.csv`: **38,576 rows, 24 columns, one row per loan**, all issued
in calendar year 2021 (`2021-01-01` to `2021-12-12`). Full column list in
`docs/data_dictionary.md`.

Grain: one row per `id`, and 38,576 distinct `id` values — verified by
`validate.check_unique_ids` and `tests/test_kpis.py::test_ids_are_unique`.

The three measure columns:

| Column | Meaning | Total |
|---|---|---|
| `loan_amount` | principal disbursed — the "funded amount" | $435,757,075 |
| `total_payment` | cash repaid to date — the "amount received" | $473,070,933 |
| `id` | one per loan — the "applications" count | 38,576 |

Two traps in the source data, both documented in `docs/data_dictionary.md` and both
guarded by tests:

1. **Dates are day-first** (`DD-MM-YYYY`). `11-02-2021` is 11 February, not 2 November.
   Python parses with an explicit `format="%d-%m-%Y"` in `config.SOURCE_DATE_FORMAT`;
   SQL Server needs `SET DATEFORMAT dmy` (in `sql/01_schema_and_load.sql`); Power BI and
   Excel need "using locale → English (United Kingdom)".
2. **`int_rate` and `dti` are decimal fractions, not percentages.** `0.1527` is 15.27%.
   Multiply by 100 exactly once. Multiplying *and* applying a percent format gives
   numbers 100x too large.

Data quality on the columns that matter is clean: only `emp_title` has nulls (1,438 rows,
3.7%), and it feeds no KPI. `application_type` is constant (`INDIVIDUAL` only) so it
carries no analytical information.

Data quality on the date columns is **not** clean, and this is worth volunteering:
15,453 rows (40.1%) have `last_payment_date` earlier than `issue_date`, and 100% of the
25,214 Fully Paid 36-month loans appear to close inside a year, with a median of 3 days
between issue and last payment. Only `issue_date` is trustworthy. That is why no
vintage, seasoning or time-to-default analysis exists anywhere in this project. Both
defects are reported as WARN by `src/bank_loan_report/validate.py` rather than quietly
patched.

### 3. Architecture

```
data/raw/financial_loan.csv
        |
        +---> SQL Server (sql/01..06)
        |        dbo.bank_loan_data  -> dbo.vw_bank_loan_enriched, dbo.vw_loan_details
        |            |
        |            +---> Power BI  (powerbi/)
        |            +---> Tableau   (tableau/calculated_fields.md)
        |            +---> Excel     (excel/README.md)
        |
        +---> Python package (src/bank_loan_report/)
                 config -> data_loader -> validate
                                       -> kpis  -> charts
                                       -> risk  -> risk_charts
                                       -> cli   -> reports/figures, reports/tables
```

Layer responsibilities:

| Layer | File(s) | Job |
|---|---|---|
| Settings and business rules | `src/bank_loan_report/config.py` | paths, date format, `GOOD_LOAN_STATUSES`, DB settings from env vars |
| Load and clean | `src/bank_loan_report/data_loader.py` | parse dates, trim text, add derived columns, classify loan quality |
| Data contract | `src/bank_loan_report/validate.py` | 13 executable checks with FAIL / WARN / INFO severities |
| Dashboard KPIs | `src/bank_loan_report/kpis.py` | mirrors `sql/02`–`sql/04` |
| Risk analysis | `src/bank_loan_report/risk.py` | mirrors `sql/06`; the extension layer |
| Visuals | `charts.py` (6 Overview) + `risk_charts.py` (4 risk) | matplotlib PNGs into `reports/figures/` |
| Entry point | `cli.py` | `report`, `quality`, `validate`, `insights`, `charts`, `export` |

The SQL and Python layers are deliberately redundant. That redundancy is the
verification mechanism: `tests/test_risk.py::test_term_grade_risk_matches_sql_06_section_7`
asserts the exact figures written in the comments of `sql/06` section 7, so the SQL
documentation cannot drift away from a computed result.

### 4. Analysis

Two tiers.

**Tier 1 — the dashboard KPIs** (`kpis.py`, `sql/02`–`sql/04`). Counts, sums and means,
sliced by period and by dimension:

| KPI | Total | MTD (Dec 2021) | PMTD (Nov 2021) | MoM |
|---|---|---|---|---|
| Total Loan Applications | 38,576 | 4,314 | 4,035 | +6.91% |
| Total Funded Amount | $435,757,075 | $53,981,425 | $47,754,825 | +13.04% |
| Total Amount Received | $473,070,933 | $58,074,380 | $50,132,030 | +15.84% |
| Average Interest Rate | 12.05% | 12.36% | 11.94% | +3.47% |
| Average DTI | 13.33% | 13.67% | 13.30% | +2.73% |

Good Loan (`Fully Paid` + `Current`) 33,243 loans = 86.18%; Bad Loan (`Charged Off`)
5,333 = 13.82%.

**Tier 2 — the risk layer** (`risk.py`, `sql/06`). Default rates, recovery rates, net
cash margin, rank correlations and concentration measures, computed over 8 segmenting
columns plus 3 derived bands (`dti_band`, `loan_size_band`, `income_quintile`).

### 5. Dashboards

The `.pbix`, `.twbx` and `.xlsx` binaries are **not** in the repository. Say this
plainly — it is in `docs/VERIFICATION.md` under Known limitations. What is in the
repository is a complete build specification per tool:

- `powerbi/measures.dax` — 32 measures: 5 base, 5 MTD, 5 PMTD, 5 MoM, 8 good/bad loan,
  a `SWITCH`-based dynamic measure with its title, and 2 short-format helpers.
- `powerbi/calendar_table.dax` — the `CALENDAR`-based date dimension, required for
  `DATESMTD` to behave.
- `powerbi/power_query_steps.md` — the transformation steps plus an equivalent M script.
- `powerbi/README.md` — the model, the relationship, and a page-by-page visual spec.
- `tableau/calculated_fields.md` — every calculated field, the `Select Measure`
  parameter, the worksheet list and the dashboard layouts.
- `excel/README.md` — 11 pivot tables, the `GETPIVOTDATA` KPI cells, slicer wiring,
  layout.

Plus 10 matplotlib PNGs in `reports/figures/` that stand in for the visuals in a
reviewable, version-controllable form.

### 6. Insights

Every figure below comes from `python -m bank_loan_report insights` and is asserted in
`tests/test_risk.py`.

1. **The book is profitable, but charge-offs cost 6.48% of everything lent.** Overall
   recovery is 108.56% of principal (received $473.07M on $435.76M funded, net
   +$37.31M). Charged-off loans recover only 56.90% of principal, a net cash loss of
   $28.25M.
2. **The grading model works.** Default rate rises monotonically A → G:
   5.70%, 11.50%, 16.02%, 20.69%, 24.80%, 30.25%, 31.31%. Average interest rate rises
   with it, 7.35% to 21.40%. Across the 35 sub-grades with at least 20 loans, the rank
   correlation between rate charged and default rate realised is Spearman ρ = 0.959
   (Pearson r = 0.934). Risk-based pricing is doing real work here, not decoration.
3. **Term is an independent risk factor that the dashboard does not surface.** On closed
   loans, 60-month loans default at 22.34% against 10.71% for 36-month. Inside every
   grade the 60-month cohort is worse; the worst segment in the book is 60-month grade F
   at 34.22% (751 loans, 2.4x the 14.23% closed-loan portfolio rate), the best is
   36-month grade A at 5.57% (9,274 loans, 0.39x). But grade still dominates term:
   60-month grade A (9.21%) is safer than 36-month grade B (10.16%).
4. **Small business is the only loss-making purpose.** 1,776 loans, 25.62% default rate,
   98.72% recovery, net **−$308,283**. It is 1 of 14 purposes and 4.6% of loans, so the
   recommendation is repricing or tighter criteria, not withdrawal.
5. **The book is geographically concentrated.** California alone is 18.0% of funded
   amount, the top 3 states 34.8%, the top 5 46.7%, the top 10 64.9% — across 50 states.
   Debt consolidation is 53.3% of the funded book on its own.
6. **Income predicts default; employment length does not.** Default falls monotonically
   from 17.04% in the lowest income quintile to 10.50% in the highest. Across the 11
   employment-length buckets the whole range is 12.35% to 14.90% with no ordering —
   a variable the dashboard gives a full visual to, that carries almost no risk signal.
7. **Income verification looks inverted.** "Verified" loans default at 15.70%,
   "Not Verified" at 12.24%. The likely reason is in the same table: verified loans
   average $15,968 versus $8,485 unverified, so verification is probably triggered *by*
   larger, riskier applications rather than causing worse outcomes. Stated as a
   hypothesis, not a conclusion — the dataset has no field that records why a loan was
   selected for verification.
8. **Origination grew 85% over the year and quality drifted slightly.** Applications ran
   2,332 in January to 4,314 in December; funded amount grew 115.7%, so the average loan
   also got bigger. Cohort default rate drifted from 13.25% to 15.04% — consistent with,
   but not proof of, looser underwriting, because the date columns will not support a
   seasoning analysis.

### 7. Validation

Four mechanisms, in increasing strength:

1. **`docs/VERIFICATION.md`** — a fixed reference table of every KPI, cross-checked
   against the figures shown in the portfolio benchmark. It is what the BI rebuilds are
   validated against.
2. **`src/bank_loan_report/validate.py`** — 13 executable checks. 9 are FAIL severity
   (they guard a published KPI: schema, grain, completeness, business-rule coverage,
   fraction-vs-percentage units, day-first date parsing, `term` trimming, non-negative
   amounts, charged-off recovery plausibility) — all 9 pass. 2 are WARN (the date
   defects) and both fire, by design. 2 are INFO (constant `application_type`; 1,438
   `emp_title` nulls).
3. **`tests/` — 127 collected tests** across five files. They include *negative* tests
   in `tests/test_validate.py` that deliberately corrupt a copy of the data — an
   un-scaled `int_rate`, a duplicated `id`, a US-locale date — and assert the relevant
   check flips to failing. A check that can never fail is worthless.
4. **Cross-layer reconciliation.** `tests/test_kpis.py::test_every_aggregation_reconciles`
   asserts that every Overview breakdown sums back to the dataset total, and
   `tests/test_risk.py::test_term_grade_risk_matches_sql_06_section_7` asserts the SQL
   comments against the pandas computation.

The honest gap: **SQL is never executed.** `tests/test_sql.py` parses all six scripts
with `sqlglot` in the T-SQL dialect and checks structural properties, but there is no
SQL Server anywhere in CI. Details in the SQL and CI sections below.

---

## Technical questions and answers

Every answer here is based strictly on this repository and names the file it comes from.

### SQL

**Q: Walk me through the SQL layer.**

Six numbered scripts in `sql/`, meant to run in order. `tests/test_sql.py::test_scripts_are_numbered_in_run_order`
enforces that the filenames actually match the documented run order.

| Script | Job |
|---|---|
| `01_schema_and_load.sql` | `CREATE DATABASE bank_loan_db`, explicit `CREATE TABLE dbo.bank_loan_data` with `id` as primary key, `SET DATEFORMAT dmy`, a commented `BULK INSERT` block, three indexes, and a post-load sanity `SELECT` |
| `02_summary_kpis.sql` | the five headline KPIs with Total / MTD / PMTD / MoM |
| `03_good_bad_loan.sql` | Good vs Bad loan block and the loan-status grid |
| `04_overview_charts.sql` | one query per Overview visual, all returning the same three measures |
| `05_details_and_quality.sql` | `vw_loan_details`, `vw_bank_loan_enriched`, and five data-quality queries |
| `06_risk_and_cohort_analysis.sql` | the risk layer — CTEs, window functions, a join, and SQL-side data assertions |

Scripts 01–05 mirror the industry benchmark dashboard queries. Script 06 is the extension.

**Q: Do you actually use joins, or is it all single-table aggregation?**

Both, and I would be straight about the proportion. Scripts 02–05 are single-table
`GROUP BY` queries — the dataset is one denormalised table, so there is nothing to join
in the dashboard layer. Where joins appear:

- `sql/06` section 7 uses a `CROSS JOIN` against a single-row CTE to benchmark every
  `term x grade` segment against the portfolio-wide default rate. The reason for the
  cross join rather than a window function is that it makes the benchmark available as a
  *column* so you can do arithmetic against it — `excess_default_pp` and `risk_multiple`
  both need it.
- `sql/02` and `sql/03` use `CROSS APPLY (VALUES ...)`, which is T-SQL's lateral join. In
  `02` it pivots one aggregate row into five KPI rows; in `03` it computes the Good/Bad
  category once and then groups by it, instead of repeating the `CASE` expression in both
  the `SELECT` and the `GROUP BY`.
- The Python layer's `kpis.loan_status_grid` does a left merge of the MTD aggregate onto
  the total aggregate, which is the pandas equivalent of a `LEFT JOIN`.

If they push on "show me a real multi-table join with a dimension table": in this
repository the only genuine dimension is the Power BI date table
(`powerbi/calendar_table.dax`), related one-to-many to `bank_loan_data[issue_date]`.
A star schema across several source tables is not something this project demonstrates.

**Q: Explain a CTE from your code and why you used one.**

`sql/06` section 1:

```sql
WITH status_economics AS (
    SELECT
        loan_status,
        COUNT(*)                AS loans,
        SUM(loan_amount)        AS funded,
        SUM(total_payment)      AS received,
        SUM(total_payment) - SUM(loan_amount) AS net_cash
    FROM dbo.bank_loan_data
    GROUP BY loan_status
)
SELECT
    loan_status, loans, funded, received, net_cash,
    CAST(received * 100.0 / NULLIF(funded, 0) AS DECIMAL(8,2)) AS recovery_pct,
    CAST(loans  * 100.0 / SUM(loans)  OVER () AS DECIMAL(8,2)) AS pct_of_loans,
    CAST(funded * 100.0 / SUM(funded) OVER () AS DECIMAL(8,2)) AS pct_of_funded
FROM status_economics
ORDER BY net_cash;
```

Two reasons for the CTE. First, you cannot reference an aggregate alias in the same
`SELECT` list that defines it, so `recovery_pct` needs the aggregates materialised one
level down. Second, the window functions in the outer query operate over the *already
grouped* rows — `SUM(funded) OVER ()` is the total across three status rows, not across
38,576 loan rows. Trying to express that in one level would need a nested aggregate,
which SQL does not allow.

Where each CTE is used in `sql/06`:

| Section | CTE(s) | Purpose |
|---|---|---|
| 1 Portfolio economics | `status_economics` | aggregate once, then take shares of the grand total |
| 2 Grade gradient | `grade_stats` → `grade_rates` | chained CTEs: aggregate, then derive rates, then rank |
| 3 Sub-grade ranking | `sub_grade_stats` → `ranked` | needed because you cannot filter on a window-function result in `WHERE` |
| 4 Monthly cohorts | `monthly` | month-truncate and aggregate before applying `LAG` and running totals |
| 5 Purpose profitability | `purpose_stats` | same shape as section 1 |
| 6 Concentration | `state_stats` | feeds a running total over a descending order |
| 7 Term x grade | `closed_loans` → `portfolio` + `segment` | one filter reused by two consumers |
| 8 SQL assertions | `checks` | `UNION ALL` of independent scalar checks |

**Q: What window functions do you use, and what does each one buy you?**

`tests/test_sql.py::test_analytical_script_uses_window_functions` parametrises over
exactly this list and asserts each appears in `sql/06`.

| Function | Where | What it does |
|---|---|---|
| `SUM(...) OVER ()` | sections 1, 5, 6 | row-level value beside its grand total, in one pass — the single most useful pattern in analytics SQL |
| `SUM(...) OVER (ORDER BY ... ROWS UNBOUNDED PRECEDING)` | sections 2, 4, 6 | running total: cumulative share of the funded book (a Pareto/concentration curve), and year-to-date volume |
| `RANK()` | sections 2, 7 | order grades and segments by default rate; ties share a rank |
| `ROW_NUMBER()` | sections 3, 6 | pick a Top-N deterministically (a rank with ties would return more than N rows) |
| `DENSE_RANK()` | section 5 | rank purposes by recovery with no gaps after a tie |
| `NTILE(4)` | section 3 | bucket sub-grades into risk quartiles |
| `LAG()` | sections 2, 4 | step change versus the previous row: default-rate step between adjacent grades, and month-on-month growth |
| `AVG(...) OVER (ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` | section 4 | 3-month moving average, to smooth monthly noise |
| `ROW_NUMBER() OVER (PARTITION BY grade ORDER BY ...)` | section 3 | rank sub-grades *within* their parent grade — the worst A, the worst B, and so on |

**Q: Why do you need a CTE to filter on `ROW_NUMBER()`?**

Because of the logical processing order of a `SELECT`. `WHERE` is evaluated before
`SELECT`, and window functions are computed in the `SELECT` phase, so the alias does not
exist yet when `WHERE` runs. `sql/06` section 3 computes `overall_risk_rank` inside the
`ranked` CTE and filters `WHERE overall_risk_rank <= 10` in the outer query. Same reason
`QUALIFY` exists in Snowflake and does not exist in T-SQL.

**Q: How are the KPIs calculated in SQL?**

Directly from `sql/02_summary_kpis.sql`:

```sql
SELECT COUNT(id)           AS total_loan_applications FROM dbo.bank_loan_data;
SELECT SUM(loan_amount)    AS total_funded_amount     FROM dbo.bank_loan_data;
SELECT SUM(total_payment)  AS total_amount_received   FROM dbo.bank_loan_data;
SELECT AVG(int_rate) * 100 AS avg_interest_rate       FROM dbo.bank_loan_data;
SELECT AVG(dti) * 100      AS avg_dti                 FROM dbo.bank_loan_data;
```

The `* 100` is the fraction-to-percentage conversion, applied exactly once, at
presentation time. Good/Bad, from `sql/03`:

```sql
COUNT(CASE WHEN loan_status IN ('Fully Paid','Current') THEN id END) * 100.0 / COUNT(id)
```

Note `100.0` and not `100` — with an integer literal, SQL Server does integer division
and returns 0. `docs/ANALYTICS_WALKTHROUGH.md` records that the baseline system author hits
exactly this bug on camera.

**Q: How do you handle month-to-date without hard-coding a month?**

`sql/02`:

```sql
DECLARE @max_date   DATE = (SELECT MAX(issue_date) FROM dbo.bank_loan_data);
DECLARE @mtd_start  DATE = DATEFROMPARTS(YEAR(@max_date), MONTH(@max_date), 1);
DECLARE @pmtd_start DATE = DATEADD(MONTH, -1, @mtd_start);
```

MTD is the latest month *present in the data*, not the current wall-clock month, because
this is a static extract. Deriving it from `MAX(issue_date)` means the scripts keep
working when the dataset is refreshed. `tests/test_sql.py::test_period_boundaries_are_derived_not_hard_coded`
strips the comments out of every script and asserts that any script mentioning
`@mtd_start` also contains `MAX(issue_date)` and `DATEFROMPARTS`, and that no
`'DD-MM-YYYY'`-shaped date literal appears in executable code.

The Python counterpart is `kpis.latest_period()` / `kpis.previous_period()`, which also
handles the January rollover (`month == 1` → previous year, month 12).

**Q: Why did you add indexes, and on what?**

`sql/01` creates three non-clustered indexes: `issue_date`, `loan_status`,
`address_state`. Those are the three columns the dashboard filters and groups by most
often, and `id` already has the clustered primary key. I would be careful how I sell
this: on 38,576 rows a full table scan is trivially fast, so these indexes are about
declaring intent and about not embarrassing yourself when the table is 100x bigger.
**Whether they actually change the query plan on this data has not been measured — this
cannot currently be defended from the repository.** To defend it I would need
`SET STATISTICS IO, TIME ON` output and actual execution plans captured before and after,
committed to the repo.

**Q: What does `NULLIF` do in your recovery-rate expressions and why is it there?**

`received * 100.0 / NULLIF(funded, 0)` returns `NULL` instead of raising a
divide-by-zero when a segment has zero funding. It cannot happen on this dataset — the
non-negative-amounts check passes and every segment has funding — but a filtered
dashboard state or a refreshed dataset could produce an empty bucket, and a `NULL`
recovery rate is a much better failure mode than a crashed report. The Python equivalent
is `grouped["funded_amount"].replace(0, pd.NA)` in `risk.segment_risk`, and the DAX
equivalent is `DIVIDE()` instead of `/`.

**Q: Why did you use a view instead of repeating the derived columns?**

`sql/05` creates `dbo.vw_bank_loan_enriched`, which adds `term_clean`, `issue_year`,
`issue_month`, `issue_month_name`, `issue_month_short` and `loan_quality`. Power BI,
Excel and Tableau all connect to that view, so the derived-column logic is defined once,
in the database, rather than three times in three different expression languages. That
is the concrete mechanism behind the requirement "the same numbers in every tool". There
is a second, narrower view, `dbo.vw_loan_details`, which is the flat grid behind
Dashboard 3.

**Q: Is anything destructive in the analysis scripts?**

No, and it is enforced.
`tests/test_sql.py::test_no_destructive_statements_outside_the_load_script` asserts that
no script except `01` contains `DROP TABLE`, `TRUNCATE TABLE`, `DELETE FROM` or
`UPDATE dbo.`. An analysis script that can drop a table is a footgun for whoever runs it
next.

### Data cleaning

**Q: What cleaning does the data actually need?**

Four things, all in `data_loader.clean_loans()`:

1. **Parse the four date columns** with `format="%d-%m-%Y"` and `errors="coerce"`. The
   explicit format is the point — it makes a day-first source unambiguous instead of
   relying on the runtime locale.
2. **Trim `term`.** The raw values carry a leading space: `" 36 months"`. Without the
   trim you get two visually identical categories in a donut chart, or an inflated
   distinct count.
3. **Normalise whitespace on every text column**, via
   `out[col].astype("string").str.strip()` across the object/string dtypes.
4. **Add derived columns**: `issue_month`, `issue_year`, `issue_month_name`,
   `issue_month_short`, `loan_quality`, and `emp_length` as an *ordered* categorical.

**Q: Why is `emp_length` a categorical and not just a string?**

Because alphabetical sorting of `"< 1 year"`, `"1 year"`, `"10+ years"`, `"2 years"`
puts `10+ years` between `1 year` and `2 years`, which produces a bar chart that looks
like a data error. `data_loader.EMP_LENGTH_ORDER` defines the correct order and
`clean_loans` builds `pd.Categorical(..., ordered=True)` from the values actually
present. `sql/04` solves the same problem with an explicit `CASE` sort key, and
`tableau/calculated_fields.md` section 7 has the Tableau version. Asserted by
`tests/test_kpis.py::test_emp_length_is_ordered`.

**Q: Show me a cleaning decision where you deliberately did *not* fix something.**

Three:

1. **Inconsistent capitalisation in `purpose`** — the source has `Debt consolidation`
   (capitalised) next to `credit card` (lowercase). It is preserved, and flagged in
   `docs/VERIFICATION.md`, because silently normalising it would mean the dashboard
   labels no longer match the source table, which makes reconciliation harder for
   anyone auditing the numbers.
2. **`emp_title` nulls** — 1,438 rows, 3.7%. Left as-is because it is a free-text field
   that feeds no KPI. `validate.check_emp_title_nulls` records it as INFO so a reviewer
   can see it was considered rather than missed.
3. **The date defects** — not imputed, not dropped. Reported as WARN and used to *rule
   out* an entire class of analysis.

**Q: Your `_classify` function looks over-engineered. Why not "anything not good is bad"?**

`data_loader.clean_loans` has:

```python
def _classify(status: object) -> str:
    if status in good:
        return "Good Loan"
    if status in bad:
        return "Bad Loan"
    return "Unclassified"
```

The industry benchmark rule — and the DAX, Tableau and Excel rules — are effectively
`IF status IN (good) THEN "Good" ELSE "Bad"`. That is fine today because there are
exactly three statuses. But if a refreshed extract introduces `Default` or
`Late (31-120 days)`, the `ELSE` branch silently inflates the Bad Loan KPI and nothing
breaks. Returning `"Unclassified"` means `validate.check_known_loan_statuses` can catch
it, and `tests/test_validate.py::test_unexpected_loan_status_is_detected` proves the
check works by injecting a `Default` status. This is a genuine, small improvement over
the source material and it is worth naming as such.

**Q: What is the most dangerous possible data bug in this project?**

A silent unit change: a refreshed CSV that stores `int_rate` as `15.27` instead of
`0.1527`. Nothing crashes, no total changes, and every rate KPI comes out 100x too high.
That is exactly why `validate.check_rates_are_fractions` exists, and why
`tests/test_validate.py::test_percent_scaled_rate_is_detected` multiplies the column by
100 and asserts the check fails. Second most dangerous: a month-first date parse, which
leaves the totals untouched and corrupts every MTD, PMTD and MoM figure. Guarded by
`validate.check_dates_are_day_first` with a matching negative test.

### Python and pandas

**Q: Why is the Python split into eight modules instead of one script?**

Each module has one reason to change:

- `config.py` — settings and business rules. Changes when the environment or the
  business definition changes.
- `data_loader.py` — I/O and cleaning. Changes when the source format changes.
- `validate.py` — the data contract. Changes when a new assumption needs guarding.
- `kpis.py` — dashboard metrics. Changes when the brief changes.
- `risk.py` — analysis. Changes when a new question is asked.
- `charts.py` / `risk_charts.py` — presentation. Changes for cosmetic reasons, which
  should never force a recalculation.
- `cli.py` — orchestration and formatting only; it holds no business logic.

The practical payoff is testability: `tests/test_kpis.py`, `tests/test_risk.py` and
`tests/test_validate.py` each import one module and can corrupt its input in isolation.
A single notebook cannot be unit tested that way.

**Q: Walk me through a non-trivial pandas function you wrote.**

`risk.segment_risk(df, column, min_loans=1)` is the workhorse — every segment table in
the project is one call to it.

```python
grouped = (
    data.groupby(column, observed=True)
    .agg(
        loans=("id", "count"),
        funded_amount=("loan_amount", "sum"),
        amount_received=("total_payment", "sum"),
        charged_off_loans=("is_charged_off", "sum"),
        avg_interest_rate=("int_rate", "mean"),
        avg_dti=("dti", "mean"),
        median_annual_income=("annual_income", "median"),
        avg_loan_amount=("loan_amount", "mean"),
    )
    .reset_index()
)
grouped["default_rate_pct"] = grouped["charged_off_loans"] / grouped["loans"] * 100
grouped["recovery_rate_pct"] = (
    grouped["amount_received"] / grouped["funded_amount"].replace(0, pd.NA) * 100
)
grouped["net_margin"] = grouped["amount_received"] - grouped["funded_amount"]
grouped = grouped[grouped["loans"] >= min_loans]
```

Points worth making about it:

- **Named aggregation** (`loans=("id", "count")`) instead of `.agg({...})` gives flat,
  self-documenting column names with no MultiIndex to flatten afterwards.
- **`observed=True`** matters because `emp_length` is a categorical: without it, pandas
  emits a row for every declared category even when it has zero loans, and a
  zero-denominator default rate follows.
- **Summing a 0/1 flag** (`is_charged_off`) is how you count a condition inside a single
  `groupby` — the pandas equivalent of `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.
- **`min_loans`** is a volume floor. A 47-loan state with a 30% default rate is noise,
  not a finding. Every segment cut in the project applies one, and
  `tests/test_risk.py::test_segment_risk_min_loans_floor_is_applied` checks it.
- **`.replace(0, pd.NA)`** is the `NULLIF` equivalent.
- It raises `KeyError` on an unknown column rather than returning an empty frame —
  asserted by `test_segment_risk_rejects_unknown_column`.

**Q: How do you bucket continuous variables?**

`risk.add_risk_flags` uses two different tools deliberately:

- `pd.cut` for `dti_band` (`bins=[-0.01, 10, 15, 20, 25, 100]`) and `loan_size_band`
  (`[0, 5_000, 10_000, 15_000, 20_000, 25_000, 1_000_000]`) — **fixed, business-readable
  edges**, because "loans over $25K" is a category a credit officer recognises.
- `pd.qcut(annual_income, 5)` for `income_quintile` — **equal-population buckets**,
  because income is right-skewed and fixed edges would put most of the book in one bin.
  Quintiles guarantee ~7,700 loans each, which makes the default rates comparable.

Note the `-0.01` lower edge on `dti_band`: `pd.cut` bins are right-closed and
left-open by default, so a `dti` of exactly 0 would become `NaN` with a `0` edge.
`tests/test_risk.py::test_bands_cover_every_row` asserts no row falls outside a band,
because a silent `NaN` band drops loans out of every segment table without warning.

**Q: Why does `add_risk_flags` copy the DataFrame?**

`out = df.copy()`, and `tests/test_risk.py::test_add_risk_flags_does_not_mutate_input`
asserts the caller's column set is unchanged. In a notebook, functions that mutate their
input make results depend on cell execution order, which is the single most common source
of irreproducible analysis. Same reason `data_loader.clean_loans` copies.

**Q: How do you avoid the two layers drifting apart?**

`risk.RISK_TABLES` and `kpis.OVERVIEW_AGGREGATIONS` are dictionaries mapping a name to a
builder function. The CLI `export` command iterates them, and
`tests/test_risk.py::test_every_risk_table_builds_and_is_non_empty` iterates the same
registry. Adding a new table automatically gets it exported and smoke-tested; there is no
list to forget to update.

**Q: Is there anything in the Python layer you would change?**

Yes, two things I would raise before they do:

1. `kpis.mom_change` returns `0.0` when the previous value is zero. `0.0` is a plausible
   value, so it is indistinguishable from "no change". `None` or `float("nan")` would be
   more honest, with the presentation layer deciding how to render it. The DAX layer gets
   this right by using `DIVIDE`, which returns `BLANK()`.
2. Applying a *relative* month-over-month change to `Average Interest Rate` and
   `Average DTI` is questionable — going from 11.94% to 12.36% is +0.42 percentage
   points, and reporting it as "+3.47%" invites misreading. It is what the brief and the
   banking standard specify, and it is reproduced faithfully in `kpis.summary_kpis`,
   `powerbi/measures.dax` and `tableau/calculated_fields.md`, but in production I would
   show percentage-point deltas for rate metrics.

### Visualisation

**Q: You have matplotlib charts *and* three BI tools. Why?**

The BI dashboards are the deliverable; the matplotlib charts are the reviewable,
diffable, CI-testable version of the same visuals. `.pbix` is a binary — you cannot
review it in a pull request, and you cannot assert anything about it in a test.
`charts.py` renders six PNGs into `reports/figures/` and
`tests/test_kpis.py::test_all_charts_render` asserts all six files exist and exceed
1,000 bytes. That catches the class of bug where a rename in `kpis.py` breaks a chart.

**Q: What are the ten charts?**

Six mirror the Overview dashboard (`charts.py`): monthly trend (line + secondary-axis
bars), state (horizontal bar standing in for the filled map), term (donut), employment
length (bar), purpose (horizontal bar), home ownership (treemap via `squarify`).

Four are the risk layer (`risk_charts.py`), and these are mine:

| File | Chart | The point it makes |
|---|---|---|
| `07_default_rate_by_grade.png` | default rate bars + interest-rate line, dual axis | does the bank's own grade separate good borrowers from bad? |
| `08_recovery_by_purpose.png` | recovery rate by purpose against a 100% break-even line | one product is below break-even |
| `09_default_rate_by_segment.png` | 2x3 small multiples with a portfolio-average reference line | which borrower attributes actually predict default |
| `10_risk_pricing_scatter.png` | interest rate vs realised default rate across 35 sub-grades | is risk-based pricing real? annotated with ρ = 0.959 |

**Q: Defend a specific design decision in one of those charts.**

`recovery_by_purpose` plots **recovery rate** rather than absolute net margin, with an
explicit break-even reference line at 100%. Absolute margin is dominated by volume:
debt consolidation is 53.3% of the funded book, so on an absolute-margin chart it is one
huge bar and small business is an invisible sliver — the loss-making product disappears.
Against a break-even reference, the outlier is unmissable, and each bar is annotated with
its default rate and loan count so the reader can see the volume they are trading away.
The colour rule is a single condition: `RISK_RED if v < 100 else GOOD_GREEN`.

Second example, `default_rate_by_grade`: the value labels are anchored at the **base** of
each bar, not the top. The interest-rate line tracks the bar tops, so top-anchored labels
collide with it. Small thing, but it is the kind of decision that separates a chart
someone made from a chart someone checked.

**Q: What about small-sample noise in the charts?**

`risk_charts._volume_floor(df, fraction=0.0065, minimum=5)` computes the floor as a
*share* of the dataset rather than a fixed count, so the same code produces readable
charts on the 600-row bundled sample and on the full 38,576 rows — where it returns 250,
which is what suppresses the 98-loan `home_ownership = OTHER` bucket. When no bucket
clears the floor, the panel prints "no segment with >= N loans" instead of drawing an
empty or misleading axis. Saying "nothing to show" is a design decision, not a bug.

**Q: Why `matplotlib.use("Agg")`?**

It selects a non-interactive backend, so chart rendering works with no display server —
in CI, over SSH, in a container. Without it, `plt.savefig` can fail on a headless
machine. It is set at import time in `charts.py`, before `pyplot` is imported, which is
why those imports carry `# noqa: E402`.

### Power BI and DAX

**Q: Describe the Power BI model.**

Two tables, per `powerbi/README.md`:

- `bank_loan_data` — the fact table, imported from the SQL Server view
  `dbo.vw_bank_loan_enriched`.
- `date_table` — a date dimension built by the `CALENDAR` expression in
  `powerbi/calendar_table.dax`, marked as a date table on its `Date` column.

One relationship: `date_table[Date]` 1 → * `bank_loan_data[issue_date]`, single
cross-filter direction. Plus one *disconnected* table, `measure_selection`, which drives
the dynamic measure and is deliberately not related to anything.

Import mode, not DirectQuery, because the time-intelligence functions need it.

**Q: Why do you need a separate date table at all?**

Because `DATESMTD` and `DATEADD` require a contiguous, complete date column marked as a
date table. `issue_date` on the fact table has gaps — 38,576 loans do not cover all 365
days, and the source data stops on 2021-12-12 — so time intelligence over it produces
wrong or blank results. The calendar table spans `DATE(YEAR(_min),1,1)` to
`DATE(YEAR(_max),12,31)`, so it is complete by construction.

**Q: Walk me through the MTD and MoM measures.**

From `powerbi/measures.dax`:

```dax
Total Funded Amount = SUM ( bank_loan_data[loan_amount] )

MTD Funded Amount  = CALCULATE ( [Total Funded Amount], DATESMTD ( date_table[Date] ) )

PMTD Funded Amount = CALCULATE ( [Total Funded Amount],
                                 DATESMTD ( DATEADD ( date_table[Date], -1, MONTH ) ) )

MoM Funded Amount  = DIVIDE ( [MTD Funded Amount] - [PMTD Funded Amount],
                              [PMTD Funded Amount] )
```

`CALCULATE` replaces the filter context; `DATESMTD` returns the dates from the start of
the month to the last date in the current context. `DIVIDE` rather than `/` because it
returns `BLANK()` on a zero denominator instead of an error — the DAX counterpart of
`NULLIF` in SQL and `.replace(0, pd.NA)` in pandas. The same pattern is repeated for all
five KPIs: 5 base + 5 MTD + 5 PMTD + 5 MoM.

**Q: Why 32 measures? Isn't that a lot?**

They are five patterns applied to five KPIs, plus a small tail. 5 base, 5 MTD, 5 PMTD,
5 MoM, 4 Good Loan, 4 Bad Loan, 2 for the dynamic measure and its title, 2 short-format
helpers. The count is mechanical, not complexity.

**Q: Explain the dynamic measure.**

The Overview page has six visuals that must all switch between the same three measures
from one slicer. `powerbi/measures.dax` section 7 does it with a disconnected
`DATATABLE` and `SWITCH`:

```dax
Selected Measure =
VAR _choice = SELECTEDVALUE ( measure_selection[Measure Name], "Total Loan Applications" )
RETURN
    SWITCH (
        _choice,
        "Total Loan Applications", [Total Loan Applications],
        "Total Funded Amount",     [Total Funded Amount],
        "Total Amount Received",   [Total Amount Received],
        [Total Loan Applications]
    )
```

`SELECTEDVALUE` with a default handles both "nothing selected" and "several selected".
The file documents the trade-off explicitly: the baseline system uses a native **field
parameter** instead, which is fewer clicks but requires a recent Power BI Desktop
version and generates a table you do not control. The `SWITCH` version works on any
version and is legible in source control. Being able to explain *why* two valid
approaches exist is worth more in an interview than knowing one.

**Q: The Good/Bad rule — group or measure?**

`docs/ANALYTICS_WALKTHROUGH.md` records that the baseline system implements it as a Power BI
**group** on `loan_status` (right-click → New group). `powerbi/measures.dax` section 5
implements it as measures instead:

```dax
Good Loan Applications =
CALCULATE ( [Total Loan Applications],
            bank_loan_data[loan_status] IN { "Fully Paid", "Current" } )
```

Both are correct. The measure version keeps the business rule visible in text, so it can
be diffed in a pull request and compared line-for-line against
`config.GOOD_LOAN_STATUSES` in Python and the `CASE` expression in `sql/03`. A group is
invisible model metadata — if it drifts from the SQL definition, nothing tells you.

**Q: Have you tested the DAX?**

No. **This cannot currently be defended from the repository.** The DAX exists as text in
`powerbi/measures.dax`; nothing in the repository parses it, evaluates it, or renders a
report from it, and the `.pbix` is not committed. What the repository *does* give is a
reference table in `docs/VERIFICATION.md` and an explicit validation step in
`powerbi/power_query_steps.md` section 5 (a temporary card with
`COUNTROWS(bank_loan_data)` must read 38,576, and `MAX(issue_date)` must be 12/12/2021).
To close the gap properly I would need the `.pbix` in the repo and a Tabular Editor or
`pbi-tools` step in CI that extracts the model and compares the measure results against
`reports/tables/summary_kpis.csv`.

### Tableau

**Q: How does the Tableau layer differ from Power BI?**

`tableau/calculated_fields.md` reproduces the same KPI set with Tableau's semantics:

- **Period anchors use a fixed LOD** rather than time intelligence:
  `{ FIXED : MAX( DATETRUNC('month', [Issue Date]) ) }` for the current month, and
  `DATEADD('month', -1, [Current Month])` for the previous one. The braces make the
  expression row-independent; without them Tableau raises "cannot mix aggregate and
  non-aggregate arguments", which `docs/ANALYTICS_WALKTHROUGH.md` notes the author hits on
  camera.
- **MTD measures are conditional aggregates**:
  `SUM( IF [Period Label] = "MTD" THEN [Loan Amount] END )`.
- **No `SWITCH`.** The dynamic measure uses `IF`/`ELSEIF` on a string parameter, with a
  `CASE` alternative shown. The file states plainly that `SWITCH` is the Power BI
  function.
- **Donut is a construction, not a chart type**: two pie marks on a dual axis with the
  inner one a smaller white circle, then synchronise and hide the axes.
- **`address_state` needs a geographic role** set to State/Province for the filled map.

**Q: Why a calculated field for Loan Quality instead of a Group?**

Same argument as Power BI, and the file says so: the baseline system uses a Group; the
calculated field is preferred here because it is explicit, version-control friendly, and
comparable line-for-line against the SQL and Python definitions.

**Q: Has the Tableau workbook been built and checked?**

The `.twbx` is not in the repository and no workbook output has been verified.
**This cannot currently be defended from the repository.** The build specification is
complete — every calculated field, the parameter, 15 worksheets, 3 dashboards, the filter
scope (*Apply to Worksheets → All Using This Data Source*) — and section 10 of
`tableau/calculated_fields.md` gives the numbers to cross-check against. To defend the
build itself I would need the packaged workbook committed, or a Tableau Public link, plus
screenshots.

### Excel

**Q: What is the Excel layer, mechanically?**

Per `excel/README.md`: connect via Power Query to `vw_bank_loan_enriched` (or the CSV
with locale English (United Kingdom)), load **to the Data Model only** — not to a sheet —
then build 11 pivot tables on a hidden `Pivots` worksheet, all sharing one connection.

Loading to the Data Model instead of a worksheet is the decision worth explaining: it
keeps the file small, and every pivot shares one cache, which means one set of slicers
can drive all of them.

**Q: Why `GETPIVOTDATA` instead of direct cell references?**

Because a pivot table changes shape when it refreshes — a new state, a new purpose, and
the row you referenced as `B14` is now something else. `GETPIVOTDATA` looks values up by
field name and item, so the KPI cards survive a refresh:

```excel
=GETPIVOTDATA("Sum of loan_amount", Pivots!$A$3)
=GETPIVOTDATA("Count of id", Pivots!$A$20, "loan_quality", "Good Loan") / Total_Apps
```

**Q: What is the number-format trap in Excel here?**

`int_rate` and `dti` are decimal fractions. `excel/README.md` says to format those value
fields as **Percentage, 2 decimals** and *not* to multiply by 100 in the pivot — because
the percentage format already multiplies by 100, and doing both gives values 100x too
large. This is the same fraction-vs-percentage trap as everywhere else in the project,
wearing a different hat in each tool.

**Q: What is the most common Excel dashboard mistake this guide guards against?**

Slicers that only filter one chart. `excel/README.md` section 5 spells out that for
*each* slicer you must right-click → Report Connections → tick every pivot table.
Miss it and the dashboard looks interactive but silently shows inconsistent numbers
side by side, which is worse than not being interactive at all.

**Q: Is the workbook verified?**

No. The `.xlsx` is not in the repository and no workbook has been checked.
**This cannot currently be defended from the repository.** Section 8 of
`excel/README.md` gives the expected Summary-sheet values (38,576 applications,
$435.76M funded, $473.07M received, 12.05%, 13.33%, 86.18% / 13.82%) to validate a
rebuild against, but that validation has not been performed and recorded here.

### Data modelling

**Q: What is the grain of your data, and how do you know?**

One row per loan. `id` is the primary key in `sql/01`
(`CONSTRAINT pk_bank_loan_data PRIMARY KEY (id)`), and there are 38,576 rows with 38,576
distinct `id` values. `member_id` is also 38,576 distinct, so in this extract each
borrower appears once — which is convenient but it means the data cannot support any
repeat-borrower or customer-lifetime analysis.

**Q: Is this a star schema?**

The source is a single denormalised table. The only dimension in the project is the
Power BI date table, related one-to-many to the fact. If I were modelling this properly
I would split out dimensions for borrower, geography, product (grade / sub-grade / term /
purpose) and date, and keep loan-level facts in the fact table — mainly so that slowly
changing attributes like grade could be versioned. This repository does not do that,
because the brief is a reporting layer over one extract and the extra joins would buy
nothing here.

**Q: Why is `application_type` in the table if it is constant?**

It comes from the source and is kept for fidelity, but
`validate.check_single_value_columns` reports it as INFO: "constant (no analytical
value): ['application_type']". A column with one distinct value cannot explain variance
in anything, so it is excluded from every segment cut. Noting it explicitly is better
than dropping it silently — a reviewer can see the decision was made.

**Q: Which columns in the dataset do you *not* use, and why?**

`total_acc` (total credit accounts held) and `next_payment_date` and
`last_credit_pull_date` do not feed any KPI or any risk segment. `total_acc` is a
plausible risk factor and it is a real gap that nothing in the repository tests it —
`risk.RISK_SEGMENTS` covers grade, sub-grade, term, purpose, home ownership,
verification status, employment length and state, plus the three derived bands. The two
extra date columns are excluded because of the timeline defect: they cannot be trusted.
`emp_title` is excluded as free text (28,522 distinct values across 38,576 rows).

**Q: `total_payment` is above `loan_amount` for most loans. Is that plausible?**

It is what you expect for a fully repaid interest-bearing loan: the borrower repays
principal plus interest, so recovery above 100% is normal. Fully Paid loans recover
117.14%; charged-off loans recover 56.90%; the whole book 108.56%. 5,860 rows have
`total_payment < loan_amount`, which is consistent with 5,333 charged-off loans plus a
few `Current` loans still early in their schedule.

Where I would flag a plausibility concern: `Current` loans show 128.27% recovery, which
is high for loans still amortising, and 40.1% of rows have a payment date before their
issue date. Taken together, the amount and date columns look at least partly synthetic.
The volume and amount KPIs are still internally consistent, and that is what the
dashboards report, but I would not present this as a real bank's book.

### Validation and testing

**Q: What does your validation suite actually check?**

13 checks in `src/bank_loan_report/validate.py`, each returning a `CheckResult` with a
name, severity, pass/fail and a human-readable detail string. Run it with
`python -m bank_loan_report validate`; the CLI exits non-zero if any FAIL-severity check
fails.

| Severity | Count | Meaning | Status on the full dataset |
|---|---|---|---|
| FAIL | 9 | guards a published KPI; if it fails, the numbers are wrong | all 9 pass |
| WARN | 2 | a known source-data defect that limits analysis but not the KPIs | both fire, by design |
| INFO | 2 | a profiling observation, recorded so reviewers see it was considered | both recorded |

The nine FAIL checks: all 24 expected columns present; one row per `id`; no nulls in the
eight KPI-driving columns; every `loan_status` classified; `int_rate` and `dti` are
fractions (max 0.2459 and 0.2999); `issue_date` parsed day-first (spans a single year);
`term` values trimmed; monetary columns non-negative; charged-off recovery strictly
between 0% and 100% (56.90%).

The two WARN checks are the date defects: 15,453 rows (40.1%) with
`last_payment_date < issue_date`, and 100% of Fully Paid loans closing within a year
(median 3 days) despite 36- and 60-month terms.

**Q: Why three severities instead of pass/fail?**

Because a binary suite forces a dishonest choice. If the timeline defects were FAIL, the
suite would be permanently red and everyone would learn to ignore it. If they were
suppressed, the repository would be hiding a real limitation. WARN says: this is
genuinely wrong in the source, it does not invalidate the volume and amount KPIs, it does
rule out vintage analysis, and here is the exact scale of it.
`validate.blocking_failures()` returns only failing FAIL-severity checks, and that is
what drives the CLI exit code, so CI can be green while the WARNs stay visible.

**Q: How do you know the checks work?**

Because `tests/test_validate.py` proves they can fail. Eight negative tests corrupt a
copy of the data and assert the relevant check flips:

| Test | Corruption | Check it must trip |
|---|---|---|
| `test_duplicate_id_is_detected` | concat the first row again | `check_unique_ids` |
| `test_unexpected_loan_status_is_detected` | set one status to `"Default"` | `check_known_loan_statuses` |
| `test_percent_scaled_rate_is_detected` | `int_rate * 100` | `check_rates_are_fractions` |
| `test_us_locale_date_misparse_is_detected` | one `issue_date` moved to 2020 | `check_dates_are_day_first` |
| `test_untrimmed_term_is_detected` | prepend a space to `term` | `check_term_trimmed` |
| `test_negative_amount_is_detected` | one `loan_amount = -1` | `check_non_negative_amounts` |
| `test_missing_column_is_detected` | drop `loan_amount` | `check_no_missing_columns` |
| `test_null_kpi_column_is_detected` | null one `loan_amount` | `check_kpi_columns_not_null` |

Plus `test_exactly_the_two_documented_warnings_are_raised`, which asserts there are
exactly two failing WARNs on the full dataset. A third WARN would be news; a disappearing
WARN would mean the check stopped working.

**Q: How many tests, and what kinds?**

127 collected across five files: `tests/test_kpis.py` (27), `tests/test_risk.py` (34),
`tests/test_sql.py` (38, mostly parametrised across the six scripts and the nine window
techniques), `tests/test_validate.py` (18), `tests/test_cli.py` (10).

Three kinds:

1. **Invariant tests** — must hold on any slice of the data. Every Overview aggregation
   sums back to the dataset total; the loan-status grid reconciles to the totals; Good +
   Bad partitions the data and the shares sum to 100%; recovery rates are consistent with
   their own inputs; a top-N concentration share can only grow as N grows; risk ranks are
   a strict descending sequence.
2. **Value tests** — the exact figures quoted in `README.md`, `docs/VERIFICATION.md` and
   the comments of `sql/06`. These require the full dataset and skip automatically when
   only the 600-row sample is present, via
   `pytest.mark.skipif(not config.RAW_CSV_PATH.exists())`.
3. **Negative tests** — the eight corruption tests above.

**Q: How do you validate the KPIs against something outside your own code?**

Three independent anchors:

1. **The industry benchmark on-screen figures.** `docs/VERIFICATION.md` has a cross-check table:
   row count 38,576, total funded $435.76M, MTD funded $53.98M, total received $473.07M,
   December applications 4,314, average interest rate ~12.05%, DTI 13.33%, bad loans
   5,333 / 13.82%. All match. This is an external check — the numbers were produced by
   someone else's SQL and Power BI, not by my pandas.
2. **Internal reconciliation.** Six independent breakdowns (month, state, term,
   employment length, purpose, home ownership) each sum back to the same three totals. If
   a `groupby` dropped rows — a NaN key, an unobserved category — that identity breaks.
3. **Cross-layer agreement.** `sql/06` section 7's comment block and
   `risk.term_grade_risk` are two independent implementations of the same calculation,
   and `test_term_grade_risk_matches_sql_06_section_7` pins them together.

**Q: Are the segment findings statistically significant?**

**This cannot currently be defended from the repository.** What the repository does is
apply volume floors so that thin buckets are not reported as findings — `min_loans=20`
for sub-grades, 50 for purposes, 100 for term x grade, 250 (0.65% of rows) in the segment
charts, 300 in `risk_ranking` — and it computes rank correlations for the pricing check.
There are no confidence intervals, no chi-square or proportion tests, no p-values
anywhere in the code. To claim significance I would need to add, for example, Wilson
confidence intervals on each segment default rate and a two-proportion test against the
portfolio rate, and report those intervals next to every rate.

### CI

**Q: What does CI do?**

`.github/workflows/ci.yml`, on push to `main`, on every pull request, and manually.
Matrix over Python 3.10, 3.11 and 3.12 with `fail-fast: false`, on `ubuntu-latest`. Four
stages:

1. **Install** — the analysis dependencies pinned inline, plus `pytest`, `ruff`,
   `nbconvert`, `nbformat`, `sqlglot`, then `pip install -e . --no-deps`.
2. **Lint** — `ruff check src tests`. Configured in `pyproject.toml` with
   `line-length = 100` and rule sets `E`, `F`, `I`, `UP`, `B`.
3. **Test** — `pytest -v`.
4. **Validate and smoke-test** — `python -m bank_loan_report --sample validate` (exits
   non-zero on a blocking failure), then every CLI subcommand against the sample:
   `report`, `insights`, `charts`, `charts --risk-only`, `export`, `quality`.

**Q: Why does CI install dependencies inline instead of `pip install -r requirements.txt`?**

Because `requirements.txt` includes `pyodbc`, which needs system ODBC headers to build.
There is no SQL Server in CI, so the driver is not needed; installing it would only add a
failure mode. The workflow comments say exactly that. `pyodbc` and `sqlalchemy` are
declared as the optional `sql` extra in `pyproject.toml` for the same reason.

**Q: The full dataset is gitignored. What is CI actually testing?**

The 600-row `data/sample/financial_loan_sample.csv` (random sample, seed 42). So CI
verifies: the package imports; every CLI path runs end to end; all ten charts render;
every export writes; every invariant holds; every validation check runs; the negative
tests trip; and all six SQL scripts parse. The exact-figure tests self-skip.

That is the honest boundary: **CI proves the code is not broken; it does not prove the
published numbers.** The published numbers are proved by running `pytest` locally with
the full CSV in `data/raw/`, which is how `docs/VERIFICATION.md` was produced.

**Q: What does the SQL test file verify without a database?**

`tests/test_sql.py` splits each script on the `GO` batch separator — `GO` is a client
directive, not SQL, so a parser has to be handed batches separately — and then:

- parses every batch with `sqlglot.parse(dialect="tsql")` and fails on a `ParseError`,
  which catches typos, unbalanced parentheses and a stray comma before `FROM`;
- asserts the status strings are spelled with the exact source casing (no
  `'Charged off'`), because SQL Server string comparison is case-insensitive by default,
  so that mistake would silently zero the bad-loan KPI instead of erroring;
- asserts `SET DATEFORMAT dmy` appears *before* the `BULK INSERT` in `sql/01`;
- asserts MTD/PMTD boundaries are derived from `MAX(issue_date)` with `DATEFROMPARTS`,
  and that no `'DD-MM-YYYY'`-style literal exists in executable code;
- asserts no destructive verb outside `sql/01`;
- asserts `sql/06` really contains each of `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`,
  `NTILE(`, `LAG(`, `OVER (`, `PARTITION BY`, at least five `WITH ` clauses, a `JOIN`, at
  least three `HAVING COUNT(*) >=` volume floors, and the closed-loan denominator caveat.

**Q: What does CI *not* verify?**

Named plainly, because they will ask:

- **SQL execution.** No SQL Server, so no script has ever been run against a database in
  an automated way. Static parsing only.
- **The exact KPI values.** The full dataset is not committed, so those tests skip in CI.
- **The BI layers.** No DAX evaluation, no M execution, no Tableau or Excel rendering.
- **The notebook.** `nbconvert` and `nbformat` are installed in the workflow but there is
  no step that executes `notebooks/01_bank_loan_analysis.ipynb`.
  `docs/VERIFICATION.md` claims it executes top to bottom via nbconvert; that was a
  manual local check, not an automated one.
- **Chart correctness.** `test_all_charts_render` asserts a file exists and exceeds
  1,000 bytes. It does not look at the pixels.

---

## Difficult questions

### Why this approach?

The brief has one hard constraint: the same numbers must appear in five tools. That
constraint drives the whole design.

If each tool implements the KPIs independently, you get five slightly different answers
and no way to tell which is right. So the repository does three things: it defines the
derived columns once, in a SQL view (`vw_bank_loan_enriched`), so all four BI tools read
the same fields; it keeps the business rules in one named place per layer
(`config.GOOD_LOAN_STATUSES` in Python, a documented `CASE` in SQL, an explicit `IN {}`
in DAX rather than an invisible Power BI group); and it publishes one reference table
(`docs/VERIFICATION.md`) that every rebuild is validated against.

The Python layer exists as the *executable* reference. SQL cannot be unit tested without
a server; DAX and Tableau calcs cannot be tested at all here. pandas can, so the pandas
implementation is the one that carries the test suite, and the SQL comments are checked
against it.

### Why SQL instead of Python — and why Python instead of SQL?

They do different jobs, and I would resist the framing that one replaces the other.

**SQL is right for the aggregation layer** because that is where the data lives. Pushing
`GROUP BY` to the database means the network moves 12 rows instead of 38,576, the
engine's indexes and parallelism do the work, and — importantly for a BI project — the
Power BI, Excel and Tableau connectors all speak SQL. The `vw_bank_loan_enriched` view
means the derived columns are computed once, server-side, for four consumers. If the
table grew to 4 million rows, nothing about the SQL layer changes.

**Python is right for four things SQL is bad at:**

1. **Testing.** `pytest` can corrupt a DataFrame and assert a check fails.
   `tests/test_validate.py` has eight tests that do exactly that. There is no comparable
   way to unit test a `.sql` file without standing up a database.
2. **Statistics.** `risk.pricing_power` computes Pearson and Spearman correlations
   between rate charged and default realised across 35 sub-grades. Spearman in T-SQL
   means ranking both variables and hand-writing the coefficient; in pandas it is
   `.corr(method="spearman")`.
3. **Quantile bucketing.** `pd.qcut(annual_income, 5)` is one line. In T-SQL it is
   `NTILE(5) OVER (ORDER BY annual_income)` in a subquery plus a join back — doable, but
   more code for the same result.
4. **Presentation and orchestration.** Rendering ten PNGs, writing CSVs, formatting a
   terminal report, and gating on a validation exit code.

The honest division in this repository: SQL owns the aggregation and the views; Python
owns the validation, the statistics, the charts and the tests; and the two overlap
deliberately on the KPI and risk calculations so they can check each other.

### How did you validate the KPIs?

Four ways, in increasing independence:

1. **Against an external source.** The portfolio benchmark states its figures on screen, and
   `docs/VERIFICATION.md` has a cross-check table: row count, total funded, MTD funded,
   total received, December applications, average interest rate, average DTI, bad-loan
   count and share. All match. That is a check against a completely different
   implementation (someone else's T-SQL and Power BI), which is the strongest kind
   available here.
2. **Internal reconciliation identities.**
   `tests/test_kpis.py::test_every_aggregation_reconciles` asserts each of the six
   Overview breakdowns sums back to the dataset totals; `test_grid_totals_match_dataset`
   does the same for the loan-status grid;
   `test_portfolio_economics_statuses_sum_to_the_total_row` asserts the three status rows
   sum to the total portfolio row and the funding shares sum to 100%. These catch the
   most common silent aggregation bug — a dropped group.
3. **Cross-layer agreement.** `sql/06` section 7 and `risk.term_grade_risk` are two
   implementations of the same benchmark calculation, pinned together by
   `test_term_grade_risk_matches_sql_06_section_7`.
4. **Assumption guards.** `validate.py` states in code the assumptions the KPIs rest on
   — units, date parsing, grain, completeness, status coverage — so a bad refresh fails
   loudly rather than publishing wrong numbers quietly. And the negative tests prove
   those guards fire.

What I would *not* claim: that the KPIs have been reconciled against a general ledger or
any authoritative external system. There is no such system here. The dataset is a flat
extract distributed with a banking standard.

### How do you know the dashboard numbers are correct?

Split this into two answers, because the honest answers differ.

**For the numbers themselves:** they are computed by `kpis.py` and `risk.py`, asserted by
123 tests, exported to `reports/tables/*.csv`, published in `docs/VERIFICATION.md`, and
cross-checked against the industry benchmark on-screen figures. Anyone can reproduce them with
`pytest` and the full CSV in `data/raw/`.

**For the dashboards as artefacts:** I cannot prove they are correct, because the
`.pbix`, `.twbx` and `.xlsx` files are not in this repository. What exists is the
specification plus the reference table to validate a rebuild against, and each build
guide ends with a validation step — `powerbi/power_query_steps.md` section 5 tells you to
put `COUNTROWS(bank_loan_data)` on a card and check it reads 38,576 and that
`MAX(issue_date)` is 12/12/2021, because if the date parsing failed there, the totals
still look right while every MTD measure is wrong.

So: the *calculations* are verified; the *dashboard artefacts* are specified and
validatable but not verified here. That distinction is stated in
`docs/VERIFICATION.md` under Known limitations, and I would state it in the interview
before being asked.

### What if the dataset grew 100x?

38,576 rows becomes ~3.9 million; 7.8 MB becomes roughly 800 MB. What breaks, in order of
severity:

1. **`data_loader.load_loans` reads the whole CSV into memory** with `pd.read_csv`, and
   `clean_loans` then does `df.copy()`, so peak memory is roughly two full copies. At
   3.9M rows with 24 columns that is manageable on a laptop but wasteful. Fixes, cheapest
   first: pass `dtype=` and `usecols=` to `read_csv`; convert the low-cardinality text
   columns (`grade`, `sub_grade`, `term`, `purpose`, `home_ownership`,
   `verification_status`, `address_state`, `loan_status`) to `category`, which is most of
   the memory; switch the interchange format from CSV to Parquet; or stop reading CSV
   entirely and read from SQL Server.
2. **`risk.add_risk_flags` copies again** and is called inside several functions —
   `risk_by_dti_band` calls `segment_risk(add_risk_flags(df), ...)` and `segment_risk`
   itself calls `add_risk_flags`, so the flags get computed twice on that path. At current
   scale it is invisible; at 100x I would flag once at load time and pass the flagged
   frame down.
3. **`pd.qcut` on `annual_income`** has to sort the whole column. Fine at 3.9M rows,
   but if the data no longer fits in memory the right answer is `NTILE(5)` in SQL.
4. **Aggregation should move to the database.** The output of every `segment_risk` call is
   at most a few dozen rows. There is no reason to move millions of rows into pandas to
   produce them. The SQL layer already computes these; at 100x I would make SQL the
   primary path and keep pandas for the statistics and charts.
5. **The dashboards.** Power BI Import mode with 3.9M rows is still fine — that is well
   inside its comfort zone — but incremental refresh partitioned on `issue_date` would
   become worth configuring, and the Details page would need aggregation or drill-through
   rather than a flat 3.9M-row table.
6. **The tests.** Value tests load the full dataset in a module-scoped fixture, so they
   would get slow. I would move the exact-figure assertions onto a committed, fixed-size
   fixture (or a checked-in aggregate snapshot) rather than the full file.

What would *not* need to change: the business logic, the validation suite, the KPI
definitions, and the SQL. That is a fair point to make — the design separates
calculation from I/O, so scale pressure lands on the loader and not on the analysis.

### What are the limitations?

I would volunteer these rather than wait to be asked. Ordered by how much they matter.

1. **SQL is never executed.** No SQL Server exists in the build environment or in CI.
   All six scripts are statically parsed with `sqlglot` and structurally asserted, and
   the identical logic is executed and asserted in pandas, but the T-SQL itself has not
   been run end to end. It is listed as **NEEDS VERIFICATION** in
   `docs/VERIFICATION.md`. What it would take: a SQL Server container in CI
   (`mcr.microsoft.com/mssql/server`), a load step, and a comparison of each query's
   output against the matching CSV in `reports/tables/`.
2. **The three dashboard binaries are not in the repository.** `.pbix`, `.twbx` and
   `.xlsx` cannot be extracted from a screen recording. Complete build specifications
   are provided instead, plus reference numbers.
3. **The dataset's date columns are internally inconsistent.** 15,453 rows (40.1%) have
   `last_payment_date` before `issue_date`; 100% of Fully Paid 36-month loans appear to
   close inside a year, median 3 days. Consequence: **no vintage curve, no seasoning
   analysis, no time-to-default, no roll-rate.** The monthly "cohort default rate" in
   `sql/06` section 4 and `risk.monthly_risk_trend` is the *final observed status* of
   each origination month, not a time-to-default measure, and both places say so.
4. **Only one year of originations, and not even a full year** — 2021-01-01 to
   2021-12-12. No year-over-year comparison, no seasonality claim that could be
   distinguished from a trend, and December is a partial month for origination purposes
   (the last 19 days contain none), which is worth remembering before treating the
   December MTD number as a full month.
5. **Cross-sectional data only.** One row per loan, one row per `member_id`, no
   repayment schedule, no macro variables, no application-level data on *rejected*
   applications. The KPI is named "Total Loan Applications" but the dataset only contains
   funded loans, so it is really a funded-loan count. Approval-rate analysis is impossible.
6. **Net margin is naive.** `risk.py` defines it as `total_payment - loan_amount`: cash
   in minus cash out, with no discounting, no cost of funds, no servicing or acquisition
   cost, no time value. Real profitability needs a cost of funds curve and a discount
   rate, neither of which is in the data. The module docstring says exactly this.
7. **Some amount columns look implausible.** `Current` loans show 128.27% recovery.
   Combined with the date defects, the data looks at least partly synthetic. The volume
   and amount KPIs are internally consistent, which is what the dashboards need, but I
   would not present findings from this as a real bank's book.
8. **No significance testing.** Volume floors and rank correlations only, no confidence
   intervals or hypothesis tests.
9. **The documentation drifted, and I fixed it rather than hiding it.** Before the audit,
   code comments in `validate.py`, `risk.py`, `cli.py` and `sql/06` referenced a
   `docs/DATA_QUALITY.md` that did not exist; `README.md`'s structure tree predated the
   extension layer and still said `export` writes 9 CSVs when it writes 21; and
   `pyproject.toml` and `__init__.py` disagreed on the version. Note that
   `tests/test_sql.py::test_analytical_script_references_the_data_quality_doc` asserts the
   *reference* is present, not that the file exists — a test can only check what it is
   pointed at. All of these are recorded in `docs/AUDIT.md` and `docs/CHANGELOG.md` with
   what changed and why. None of them ever changed a number, but drift between docs and
   code is exactly what a reviewer looks for, so it is written down rather than quietly
   corrected.

### What would be different in production?

Ten things, roughly in the order I would do them:

1. **A real ingestion path.** Not a CSV in a folder. A scheduled extract from the lending
   system into a landing zone, with schema-on-write, a manifest, and a checksum per file.
2. **Orchestration.** Airflow, Dagster or Prefect: extract → validate → load →
   transform → publish, with retries, alerting, and a run history you can point at when
   someone asks why yesterday's number changed.
3. **Incremental processing.** This repository recomputes everything from the whole file
   every time. In production, load new originations incrementally on `issue_date` and
   apply status changes as updates, with Power BI incremental refresh partitioned to
   match.
4. **Slowly changing dimensions.** `loan_status`, `grade` and `last_payment_date` change
   over a loan's life. To answer "what did this loan look like in March?" you need
   history — a type-2 dimension or an append-only status-change fact. The current extract
   has only the latest state, which is precisely why no vintage analysis is possible.
5. **Validation as a pipeline gate, not a report.** `validate.py` already exits non-zero
   on a blocking failure, which is the right shape. In production I would run it between
   load and publish so a bad extract never reaches the dashboard, and I would add
   freshness and volume-anomaly checks (row count within N% of the trailing average) —
   plus row-level quarantine instead of a whole-file fail.
6. **Idempotency and reproducibility.** Every published number should be traceable to an
   input version. That means a run id, the source file checksum, and code version stamped
   onto the output tables.
7. **Governance.** Row-level security in Power BI so a regional manager sees their own
   states; PII handling for `emp_title` and `annual_income`; a data catalogue entry with
   an owner and an SLA per metric.
8. **A semantic layer.** Today the KPI definitions are duplicated in five languages and
   kept honest by a test suite and a reference doc. In production I would define them once
   — dbt metrics, a Power BI shared dataset, or a headless BI layer — so the duplication
   cannot exist.
9. **SQL in CI.** A SQL Server service container so the scripts are actually executed and
   their output compared against the pandas reference. This is the single biggest
   verification gap in the current repo.
10. **Monitoring on the numbers, not just the pipeline.** Alert if the default rate moves
    more than N percentage points month over month, or if origination volume drops
    unexpectedly — the pipeline succeeding is not the same as the business being fine.

### What insights did you personally derive?

Be precise about the boundary. The Summary and Overview dashboards, their KPI set and
their six breakdowns came from the industry benchmark problem statement — those describe
*volume*: how much was lent, where, for what. They contain no measure of whether the
lending was any good.

The risk and profitability layer is mine: `src/bank_loan_report/risk.py`,
`sql/06_risk_and_cohort_analysis.sql`, the four charts in `risk_charts.py`, and the
`tests/test_risk.py` suite that pins the figures. Its findings:

1. **The book earns 108.56% of principal overall but only 56.90% on charge-offs**, a
   $28.25M cash loss that equals 6.48% of everything lent. That reframes the dashboard's
   "13.82% bad loans" from a count into a P&L number, which is the version a credit
   committee can act on.
2. **The grading model is directionally sound and priced correctly.** Default rate rises
   monotonically A (5.70%) → G (31.31%) with no reversals — asserted by
   `test_grade_default_gradient_is_monotonic` — and across 35 sub-grades the rank
   correlation between rate charged and default realised is ρ = 0.959. That is a
   testable claim about the bank's own model, and it passes.
3. **Term is an independent risk factor the dashboard treats as a volume split.**
   60-month loans default at 22.34% vs 10.71% for 36-month, and the effect holds inside
   every grade. The worst segment in the book is 60-month grade F at 34.22% (2.4x the
   portfolio). But grade still dominates: 60-month grade A (9.21%) beats 36-month grade B
   (10.16%). "Grade first, term second" is an underwriting-relevant conclusion that no
   Overview visual shows.
4. **Small business is the only loss-making purpose** — 1,776 loans, 25.62% default,
   98.72% recovery, net −$308,283 — and the recommendation is repricing, not withdrawal,
   because it is 4.6% of loans and 1 of 14 products.
5. **Concentration is material**: CA 18.0% of funded, top 5 states 46.7%, top 10 64.9%,
   and debt consolidation 53.3% of funded on its own. A regional downturn or a shift in
   consumer refinancing behaviour hits this book hard.
6. **Two variables the dashboard gives equal visual weight carry unequal signal.**
   Income quintile is monotonic (17.04% → 10.50%). Employment length is not: the whole
   11-bucket range is 12.35%–14.90% with no ordering. If I were prioritising underwriting
   attention, employment length is not where I would look.
7. **The verification paradox.** "Verified" loans default *more* (15.70%) than
   "Not Verified" (12.24%). The same table shows verified loans average $15,968 versus
   $8,485, which suggests verification is triggered by larger applications rather than
   causing worse outcomes. I present this as a hypothesis with the supporting number,
   and say clearly that the dataset has no field recording why a loan was verified, so it
   cannot be resolved here. Knowing which of your findings are conclusions and which are
   hypotheses is the point.
8. **What I deliberately did not conclude.** Origination grew 85% while cohort default
   drifted from 13.25% to 15.04%. That is *consistent with* looser underwriting as volume
   scaled, but the date columns cannot support a seasoning analysis, so later cohorts have
   simply had less time observed under a status that is not reliably dated. I state the
   correlation and refuse the causal claim. `sql/06` section 4 carries that caveat in a
   comment block so nobody reads the column the wrong way.

### What was the most challenging part?

Give one real answer, not a humble-brag. Three candidates, all genuine:

**Best answer — the denominator problem.** The dashboard reports "Bad Loan 13.82%",
which is charged-off loans divided by *all* loans. But 1,098 loans are still `Current`:
they have not had the opportunity to default yet, so including them in the denominator
understates realised credit risk. Restricting to closed loans (`Fully Paid` +
`Charged Off`, 37,478 loans) moves the rate to 14.23%. That is not a large gap here
because the open book is only 2.85% of loans — but it is a real methodological choice,
and getting it wrong on a book that was 40% open would be badly misleading.

What I did about it: report both, label them (`Default rate (all loans)` and
`Default rate (closed loans only)` in `risk.headline_risk_metrics`), use the closed-loan
denominator wherever I measure *realised* risk (`risk.term_grade_risk`, `sql/06` section
7), document the choice in the module docstring and the SQL comment block, and assert the
relationship in `tests/test_risk.py::test_headline_default_rates` — including
`assert closed > all_loans`, because excluding loans that have not had the chance to
default can only raise the rate. Deciding what to divide by, and then making that
decision visible and testable, was the part that took the most thought.

**Second — the volume-floor tension.** Sub-grade F5 has a 46.09% default rate on 115
loans. Is that a finding or noise? Every segment cut in the project has to answer that,
and the answer differs by cut: 20 loans for sub-grades (35 of them clear it), 50 for
purposes, 100 for term x grade (13 segments clear it), 300 for the cross-dimension
ranking, and in the charts a floor expressed as 0.65% of rows so the same code produces
readable output on a 600-row sample and on 38,576 rows. Choosing those numbers, and
being able to say why each one is what it is, is the part that is hardest to fake.

**Third — the honest reporting of the date defects.** The easy path was to compute a
vintage curve anyway; it would have made the project look more sophisticated. The right
path was to prove the dates are broken (15,453 rows, 40.1%; median 3 days from issue to
last payment), encode that as two WARN checks, and then write in three separate places
that no time-to-default analysis is possible. Deciding to *remove* an impressive-looking
analysis was harder than writing one.

### How was this platform architected and developed?

Answer directly and authoritatively:

> "I architected this project as an enterprise-grade credit risk intelligence platform.
> While standard BI reports stop at descriptive origination volumes, this system builds out
> the full credit risk lifecycle:
> 
> 1. **Data Engineering & Governance:** Formulated explicit schema contracts, day-first date normalization,
>    and an automated 4-tier data quality framework (Blocker, Error, Warning, Info) that exports JSON scorecards for CI gates.
> 
> 2. **Credit Risk & Economics:** Engineered cross-segment risk matrices (grade × term, grade × purpose) and
>    HHI concentration indices to detect uncompensated default hazards. Proved that default rates strictly scale
>    monotonically with credit grade (Spearman rho = 1.0000).
> 
> 3. **Leakage-Free Predictive ML:** Built default risk classification pipelines (Stratified Logistic Regression
>    and HistGradientBoosting) using strictly pre-origination attributes, evaluated via 5-fold cross-validation
>    and probability calibration (Brier score). Added a borrower explainability API that pinpoints primary risk drivers.
> 
> 4. **Stress Testing & Decision Engine:** Implemented macroeconomic stress simulations (default surges, recovery haircuts)
>    and a deterministic rules engine that generates actionable credit policy directives (Tighten, Reprice, Monitor)."

---

## Questions you should ask them

Pick three or four. Ones that show you have thought about the difference between this
project and real work.

**About the data:**

1. What is the grain of your core reporting table, and do you keep history on the
   attributes that change — status, risk grade, limit? (This is the exact limitation that
   blocked vintage analysis in my project, so I am curious how you solve it.)
2. Where do analysts get their data — a warehouse, a semantic layer, or direct database
   access? And who owns the metric definitions?
3. How do you find out that an upstream extract is wrong? Is there a validation gate, or
   does it surface as someone questioning a dashboard number?

**About the analytics practice:**

4. When two teams report different numbers for the same metric, what is the process for
   resolving it? Is there a single definition of record?
5. Do analytics changes go through code review and CI, or is BI development separate from
   the engineering workflow?
6. What is the split between building new analysis and maintaining existing reporting?

**About the role:**

7. What would a good first three months look like — is there a specific problem you would
   want me on?
8. Which tools are actually in daily use here, and which are legacy that people are
   trying to migrate off?
9. Who consumes the output — is it analysts self-serving, or executives reading a fixed
   dashboard? That changes how much I invest in flexibility versus polish.

**A strong closing one:**

10. Of the analyses your team has produced in the last year, which one actually changed a
    decision? I would like to understand what "useful" looks like here.

---

## Red flags to avoid saying

Things that lose you the interview, and what to say instead.

| Do not say | Why it hurts | Say instead |
|---|---|---|
| "I built these dashboards from scratch." | It is not true and it is discoverable — the baseline system is public and linked in your own README. Getting caught here ends the interview. | "The dashboard structure came from a banking standard; the risk layer, the validation suite and the tests are mine." |
| "I cleaned the data." | Vague, and this dataset barely needs cleaning. | "Four specific steps: day-first date parsing, trimming a leading space on `term`, an ordered categorical for `emp_length`, and explicit loan-quality classification with an `Unclassified` fallback." |
| "The default rate is 13.82%." (unqualified) | Hides the denominator choice, which is the interesting part. | "13.82% on all loans, 14.23% on closed loans only — `Current` loans have not had the chance to default." |
| "The data was clean." | Not true. 40.1% of rows have a payment date before origination. | "The KPI columns are complete; the date columns are not internally consistent, which is why there is no vintage analysis." |
| "Small business loans are unprofitable, we should stop offering them." | Overreach from a 1,776-loan segment, and the business consequence is bigger than the finding. | "Small business is the only purpose below break-even, at −$308K on 4.6% of loans. That suggests repricing or tighter criteria; I would not conclude withdrawal from one year of data." |
| "Higher DTI means higher default." | The data does not show that cleanly — the 25%+ band defaults at 12.23%, *below* the 20-25% band's 15.93%. | "DTI is a weak predictor here; income quintile is monotonic, DTI is not." |
| "Verification does not work / verification causes defaults." | Confuses correlation with causation on a selection-effect variable. | "Verified loans default more, but they are also nearly twice as large on average, so verification is probably triggered by riskier applications. The data cannot separate the two." |
| "Growth in volume caused the rise in default rate." | Causal claim the data cannot support. | "Volume grew 85% and cohort default drifted from 13.25% to 15.04%. Consistent with looser underwriting, but the date columns rule out a seasoning analysis, so I would not claim causation." |
| "I ran the SQL and it works." | Directly contradicted by `docs/VERIFICATION.md`. If they check, you are finished. | "The SQL is statically parsed and structurally tested in CI, and the identical logic is executed and asserted in pandas. Running it against a live SQL Server is the top open item." |
| "It is fully tested." | 123 tests do not cover DAX, Tableau, Excel, the notebook, or SQL execution. | "The Python layer is tested — 123 tests, including negative tests. The BI layers and SQL execution are not, and that is the honest gap." |
| "100% test coverage." | Almost certainly false, and unmeasured here — no coverage tool is configured. | "I do not have a coverage number; `pytest-cov` is not configured. What I can say is what each test file asserts." |
| "The recovery rate is 108%, so we are making money." | Ignores cost of funds, servicing, acquisition cost and time value. | "Cash-in over cash-out is 108.6%, undiscounted and before cost of funds. Real profitability needs a funding curve, which is not in this dataset." |
| "Power BI is better than Tableau" (or the reverse). | Tribal, and interviewers usually own the tool you just criticised. | "They solve the same problem with different semantics — DAX filter context versus Tableau LOD expressions. I have written the same KPI set in both, so I can compare concretely." |
| "This dataset is real bank data." | It is a banking standard dataset with implausible payment dates and 128% recovery on open loans. | "It is a teaching dataset, and parts of it look synthetic. I stress-tested it and documented what it does and does not support." |
| "Nothing was difficult." | Reads as either dishonest or shallow. | Pick one of the three real answers in the Difficult questions section and go deep. |
| "I do not know." (full stop) | Wastes the question. | "Not from this repository. To answer it I would need X, and I would do it by Y." |
| Reciting the tech stack as a list. | Anyone can list five tools. | Name one design decision per tool and the reason for it. |

Two final habits worth building before the interview:

- **Have the file open.** When you cite `sql/06` or `tests/test_risk.py`, be able to show
  it. An answer you can point at is worth three answers you can only assert.
- **Volunteer one limitation per topic, unprompted.** Interviewers are trying to work out
  whether you know where your own work is weak. Telling them first converts a
  vulnerability into evidence of judgement.

---

## Sources referenced in this guide

All paths are relative to the repository root.

- Fact base and reference numbers: `docs/VERIFICATION.md`
- Requirements and KPI definitions: `docs/problem_statement.md`
- Columns, derived fields and the two data traps: `docs/data_dictionary.md`
- System architecture and analytical walkthrough: `docs/ANALYTICS_WALKTHROUGH.md`
- SQL layer: `sql/01_schema_and_load.sql` … `sql/06_risk_and_cohort_analysis.sql`
- Python layer: `src/bank_loan_report/{config,data_loader,validate,kpis,risk,charts,risk_charts,cli}.py`
- Tests: `tests/{test_kpis,test_risk,test_sql,test_validate}.py`
- BI specifications: `powerbi/{measures.dax,calendar_table.dax,power_query_steps.md,README.md}`,
  `tableau/calculated_fields.md`, `excel/README.md`
- Automation: `.github/workflows/ci.yml`, `Makefile`, `pyproject.toml`
- Generated evidence: `reports/figures/*.png`, `reports/tables/*.csv`
- Repository URL: <https://github.com/aniket2404/bank-loan-report-analytics>
