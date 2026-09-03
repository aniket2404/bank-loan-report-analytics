# Learning Guide — Bank Loan Report Analytics

**Who this is for:** you, if you are about to put this project on a resume and need to
understand every line of it well enough to be questioned about it.

**How to use it:** read it with the repository open. Every section names the file it is
teaching. Nothing here is generic textbook material — every definition, formula and
number is tied to code that exists in this repo.

**Where the numbers come from:** every figure in this guide was produced by running
`src/bank_loan_report` against the full 38,576-row `financial_loan.csv` dataset. The
reference values live in `docs/VERIFICATION.md` and the machine-generated fact base used
to write this guide. If a figure here disagrees with what the code prints, the code wins
and this document is stale.

**Honesty note up front:** the Summary/Overview/Details dashboard structure, the KPI
definitions and SQL scripts `01`–`05` follow a published standard baseline implementation (see
`docs/ANALYTICS_WALKTHROUGH.md`). The risk and quality layer — `src/bank_loan_report/risk.py`,
`src/bank_loan_report/validate.py`, `src/bank_loan_report/risk_charts.py`,
`sql/06_risk_and_cohort_analysis.sql` and the five test files — is extension work built on
top of it. Keep that distinction straight in your head; it is the single most useful thing
you can be honest about.

---

## 1. What does this project actually do?

In one sentence: it takes a flat CSV of 38,576 consumer loans issued during 2021, loads it
into SQL Server, computes a fixed set of lending KPIs, reproduces those same KPIs
independently in Python, renders them into four different presentation tools, and then adds
a risk layer that asks whether the lending was any *good*.

There are two distinct halves, and confusing them is the most common way to sound
unprepared.

### Half one — the reporting layer ("how much did we lend?")

Requirements in `docs/problem_statement.md`. Three dashboards — **Summary**, **Overview**,
**Details**. SQL `sql/01`–`sql/05`; Python mirror `kpis.py` rendered by `charts.py`; BI specs
in `powerbi/`, `tableau/calculated_fields.md`, `excel/README.md`. It reports applications,
funded amount, amount received, average interest rate and average DTI as a total,
month-to-date, and versus the previous month.

This half is *descriptive*. It counts things. It contains no judgement about whether the
loans were sensible.

### Half two — the risk layer ("was the lending any good?")

`sql/06_risk_and_cohort_analysis.sql` (501 lines, 8 sections), mirrored by `risk.py` and
rendered by `risk_charts.py`. It asks which segments default, whether the bank's own risk
pricing predicts those defaults, where the cash losses land, and how concentrated the book is.

This half is *diagnostic*. It is also the half where the SQL stops being plain `GROUP BY`
and starts using CTEs, `RANK`, `LAG`, `ROW_NUMBER`, `NTILE`, running totals and a
`CROSS JOIN` benchmark.

### The glue

- `src/bank_loan_report/config.py` — one place for business rules and paths.
- `src/bank_loan_report/data_loader.py` — load and clean.
- `src/bank_loan_report/validate.py` — 13 executable data-quality checks.
- `src/bank_loan_report/cli.py` — `python -m bank_loan_report <command>`.
- `tests/` — 127 collected tests across five files.
- `.github/workflows/ci.yml` — lint, test, validate, CLI smoke tests on Python 3.10/3.11/3.12.

### How to run it

```bash
python -m bank_loan_report report      # Summary + Overview dashboards to stdout
python -m bank_loan_report insights    # risk and profitability analysis
python -m bank_loan_report validate    # 13 data-quality checks, non-zero exit on FAIL
python -m bank_loan_report quality     # per-column null / dtype / distinct profile
python -m bank_loan_report charts      # 10 PNGs into reports/figures/
python -m bank_loan_report export      # 21 CSVs into reports/tables/
```

Global flags: `--data <path>` to point at a specific CSV, `--sample` to use the bundled
600-row sample instead of the full dataset. Both are defined in `cli.py::main`.

---

## 2. Banking and lending terminology used here

Learn these in the context of the columns they map to. An interviewer will not accept
"DTI is debt to income" — they want to know what it does in *your* numbers.

### Loan

One row in the dataset, identified by `id`. 38,576 of them — money the bank disbursed to a
borrower with an agreed repayment schedule.

### Principal / funded amount

The money actually handed over. Column: `loan_amount`. In this project **Funded Amount =
`SUM(loan_amount)`** — that definition is fixed in `docs/data_dictionary.md` and implemented
in `kpis.total_funded_amount()`.

- Total funded across the book: **$435,757,075**
- Average loan: **$11,296.07**; median **$10,000** (mean above median — a right-skewed
  distribution, a few large loans pulling the average up)

### Amount received

Total cash repaid to date, including interest. Column: `total_payment`. **Amount Received =
`SUM(total_payment)`** — `kpis.total_amount_received()`.

- Total received: **$473,070,933**
- Net: **+$37,313,858**

Note carefully: `total_payment` is *cumulative cash in*, not profit. It contains no cost of
funds, no operating cost, no discounting. `risk.py` says this explicitly in its module
docstring, and you should repeat that caveat rather than let an interviewer catch it.

### Installment

The fixed monthly payment the borrower owes — a function of principal, rate and term.
Column: `installment`, average **$326.86**. Reported in the Details grid but used in no KPI.

### Interest rate

Annual rate charged. Column: `int_rate`. **Stored as a decimal fraction** — `0.1104` means
11.04%. Average across the book: **12.0488%**.

This is trap number one in the project. Multiply by 100 exactly once. If you multiply *and*
apply a percentage number format in Power BI or Excel, you get values 100× too large.
`validate.check_rates_are_fractions()` exists specifically to catch a refreshed file that
switches to whole percentages, because that error would inflate every rate KPI without
crashing anything.

### DTI — debt-to-income ratio

The borrower's existing monthly debt obligations divided by their monthly income, excluding
this loan. Column: `dti`, also a decimal fraction. Average **13.3274%**.

Interpretation: higher DTI means the borrower is already carrying more debt relative to what
they earn, so there is less headroom to absorb a shock. It is a standard underwriting input.

What is interesting in *this* dataset is that DTI turns out to be a **weak and
non-monotonic** predictor — see section 11. Being able to say "the textbook says DTI predicts
default; in my data it barely does, and here are the numbers" is a much better answer than
reciting the textbook.

### Grade and sub-grade

The lender's own internal credit rating, assigned at origination. Columns: `grade` (`A`–`G`,
A best) and `sub_grade` (finer, e.g. `C4`, `F5`). This is *the bank's opinion of the
borrower*, before any outcome is known.

Grade is the strongest single risk signal in the data, and it is perfectly monotonic on
default rate with interest rate climbing alongside — the grading system working:

| Grade | Loans | Default rate | Avg interest rate |
|---|---|---|---|
| A | 9,689 | 5.70% | 7.35% |
| B | 11,674 | 11.50% | 11.03% |
| C | 7,904 | 16.02% | 13.55% |
| D | 5,182 | 20.69% | 15.71% |
| E | 2,786 | 24.80% | 17.71% |
| F | 1,028 | 30.25% | 19.74% |
| G | 313 | 31.31% | 21.40% |

At sub-grade level the spread is far wider: **F5 defaults 46.09%** (115 loans) versus **A1 at
2.28%** — roughly a 20× spread.

### Term

The repayment period. Column: `term`, only two values: `36 months` and `60 months`.

**Trap number two:** the raw values have a leading space (`" 36 months"`).
`data_loader.clean_loans()` strips whitespace from every text column; the SQL view uses
`LTRIM(RTRIM(term)) AS term_clean`. If you skip this, `" 36 months"` and `"36 months"` become
two separate categories and your donut chart splits in half.

Term matters more than the dashboard suggests. The Overview dashboard shows term only as a
volume split (73.2% / 26.8%). But:

| Term | Loans | Default rate | Avg rate | Avg loan |
|---|---|---|---|---|
| 36 months | 28,237 | 10.71% | 11.03% | $9,670 |
| 60 months | 10,339 | 22.34% | 14.83% | $15,738 |

60-month loans default at more than double the rate. That finding comes from
`risk.segment_risk(df, "term")` and section 7 of `sql/06`, not from the baseline implementation dashboards.

### Charge-off

When a lender concludes a loan will not be repaid, it *charges off* the remaining balance —
it writes it off as a loss and stops treating it as a collectable asset. In this dataset it
is a value of `loan_status`: `Charged Off`.

- 5,333 charged-off loans
- $65,532,225 funded against them
- $37,284,763 recovered
- Recovery on charged-off loans: **56.90%** of principal
- Net cash lost: **−$28,247,462**, i.e. **6.48% of everything the bank lent**

Important nuance: a charge-off is not a total loss. The bank still collected 56.9% of the
principal on those loans before giving up. That is why the whole book is still profitable.

### Default rate

Share of loans that ended up charged off. There are **two** defensible denominators, and
knowing why is a genuine interview differentiator:

| Definition | Value | Formula in code |
|---|---|---|
| All loans | **13.82%** | `len(charged_off) / len(data)` — `risk.headline_risk_metrics()` |
| Closed loans only | **14.23%** | `charged_off / len(closed)` where closed = `Fully Paid` + `Charged Off`, 37,478 loans |

Why the closed-only version is more honest: a loan still `Current` has not yet had the
*opportunity* to default. Including it in the denominator dilutes the rate and understates
realised credit risk. The open book here is only **2.85%** of loans, so the gap is small
(13.82% → 14.23%) — but the reasoning is what matters, and `sql/06` section 7 and
`risk.term_grade_risk()` both restrict to closed loans and say so in comments.

The dashboard's "Bad Loan %" (13.82%) uses the all-loans denominator, so the two layers
deliberately differ and each documents which it uses.

### Recovery rate

`SUM(total_payment) / SUM(loan_amount) * 100`. Defined in `risk.py`'s module docstring and
computed in `risk.segment_risk()`.

- Above 100% → interest collected exceeded principal lent (good)
- Below 100% → the bank got back less cash than it put out (bad)

Portfolio recovery: **108.56%**. By status:

| Status | Loans | Recovery rate |
|---|---|---|
| Fully Paid | 32,145 | 117.14% |
| Current | 1,098 | 128.27% |
| Charged Off | 5,333 | 56.90% |

The `Current` figure at 128.27% looks odd for loans that are still open. Do not paper over
it — it is a consequence of the dataset's internally inconsistent date columns (section 9).
Say so.

### Net margin

`total_payment - loan_amount`. Cash in minus cash out. Per-loan column added by
`risk.add_risk_flags()`, summed per segment in `risk.segment_risk()`. Again: no discounting,
no cost of funds. It is a cash measure, not a profitability measure in the accounting sense.

### Good loan vs bad loan

The project's portfolio-health split, defined in `config.py` and used everywhere:

```python
GOOD_LOAN_STATUSES = ("Fully Paid", "Current")
BAD_LOAN_STATUSES  = ("Charged Off",)
```

| Category | Statuses | Applications | Share | Funded | Received |
|---|---|---|---|---|---|
| Good Loan | Fully Paid, Current | 33,243 | **86.175%** | $370,224,850 | $435,786,170 |
| Bad Loan | Charged Off | 5,333 | **13.825%** | $65,532,225 | $37,284,763 |

One detail worth pointing at: `data_loader.clean_loans()` does **not** classify with
"anything not good is bad". It classifies explicitly into `Good Loan` / `Bad Loan` /
`Unclassified`, so an unrecognised status surfaces as `Unclassified` and
`validate.check_known_loan_statuses()` flags it, rather than silently inflating the Bad Loan
KPI. The SQL in `sql/03` uses a `CASE ... ELSE 'Bad Loan'` fallback, which is the baseline implementation's
approach — that asymmetry is real and you should know it exists.

### MTD, PMTD, MoM

- **MTD (month-to-date)** — the latest month present in the data. Here: **December 2021**.
- **PMTD (previous month-to-date)** — the month immediately before. Here: **November 2021**.
- **MoM (month-over-month)** — `(MTD − PMTD) / PMTD × 100`.

Both are *derived*, never hard-coded. `kpis.latest_period()` takes `df["issue_date"].max()`;
`sql/02` does `DECLARE @max_date DATE = (SELECT MAX(issue_date) FROM dbo.bank_loan_data)`.
`tests/test_sql.py::test_period_boundaries_are_derived_not_hard_coded` asserts the SQL does
not hard-code a month. That is what makes the report survive a data refresh.

| KPI | Total | MTD (Dec) | PMTD (Nov) | MoM |
|---|---|---|---|---|
| Total Loan Applications | 38,576 | 4,314 | 4,035 | +6.91% |
| Total Funded Amount | $435,757,075 | $53,981,425 | $47,754,825 | +13.04% |
| Total Amount Received | $473,070,933 | $58,074,380 | $50,132,030 | +15.84% |
| Average Interest Rate | 12.0488% | 12.356% | 11.942% | +3.47% |
| Average DTI | 13.3274% | 13.666% | 13.303% | +2.73% |

Two honest caveats about MTD in this dataset:

1. `issue_date` maxes out at **2021-12-12**. So "December MTD" is really the first twelve
   days of December, not a full month. The +6.91% MoM on applications is therefore
   comparing a partial month to a full one — it *understates* growth.
2. Applying a *relative* MoM change to a *rate* metric (interest rate, DTI) is
   questionable presentation. "+3.47%" on a rate that moved from 11.942% to 12.356% is a
   relative change; most credit reporting would quote the +0.41 percentage-point move
   instead. The code computes the relative version because that is what the dashboard
   specifies (`kpis.mom_change`), and you should be ready to say you know the difference.

One more implementation wart worth owning: `kpis.mom_change()` returns `0.0` when the
denominator is zero. That makes "no previous data" indistinguishable from "no change". A
`None`/`NaN` would be more honest. The DAX layer uses `DIVIDE()`, which returns blank
instead.

---

## 3. The dataset, column by column

The authoritative reference is **`docs/data_dictionary.md`** — read it, do not memorise a
paraphrase. What follows is the *meaning* layer: why each column exists and what the project
does with it.

**Shape:** 38,576 rows × 24 source columns. One row per loan. `id` and `member_id` are both
38,576 distinct values, so every loan belongs to a different borrower — there is no repeat
borrower to analyse. `issue_date` spans 2021-01-01 → 2021-12-12. After cleaning there are
29 columns (five derived).

### Identifiers

| Column | What it means | Used for |
|---|---|---|
| `id` | Loan identifier, the primary key | `COUNT(id)` = Total Loan Applications; grain check in `validate.check_unique_ids()` |
| `member_id` | Borrower identifier | Nothing. 1:1 with `id`, so it adds no information here |

### Borrower attributes

| Column | What it means | Used for |
|---|---|---|
| `address_state` | Two-letter US state, 50 values | Overview filled map; concentration analysis; state-level risk |
| `annual_income` | Yearly income in USD | Income quintiles (`pd.qcut`) in the risk layer. Avg $69,644.54, median $60,000 |
| `dti` | Debt-to-income, decimal fraction | Headline KPI; `dti_band` risk cut |
| `emp_length` | Employment length, 11 buckets `< 1 year` → `10+ years` | Overview bar chart; risk cut. Ordered categorical so charts sort correctly |
| `emp_title` | Free-text job title | **Nothing.** 1,438 nulls (3.7%), 28,522 distinct values. Flagged INFO by `validate.check_emp_title_nulls()` and left as-is |
| `home_ownership` | `RENT` / `MORTGAGE` / `OWN` / `OTHER` / `NONE` | Overview tree map; risk cut |
| `verification_status` | Whether income was verified: `Verified` / `Source Verified` / `Not Verified` | Risk cut — and it produces a counter-intuitive result (section 11) |
| `total_acc` | Total credit accounts held | **Nothing.** Unused in this project |

### Loan attributes

| Column | What it means | Used for |
|---|---|---|
| `grade` | Internal credit grade `A`–`G` | Primary risk dimension; slicer on all dashboards |
| `sub_grade` | Finer grade, e.g. `E1` | Sub-grade ranking; the pricing-power correlation |
| `term` | `36 months` / `60 months` (leading space in raw file) | Overview donut; independent risk factor |
| `purpose` | Stated reason, 14 categories | Overview bar chart; purpose profitability |
| `application_type` | Application type | **Nothing.** Constant `INDIVIDUAL` across all rows — zero analytical value, flagged INFO by `validate.check_single_value_columns()` |
| `loan_amount` | Principal disbursed | Funded Amount |
| `installment` | Fixed monthly payment | Reported in the Details grid only |
| `int_rate` | Annual rate, decimal fraction | Headline KPI; pricing-power analysis |
| `loan_status` | `Fully Paid` / `Current` / `Charged Off` | Good/Bad rule; every default-rate calculation |
| `total_payment` | Cumulative repaid | Amount Received; recovery rate; net margin |

### Dates — all four stored as `DD-MM-YYYY` text

| Column | What it means | Used for |
|---|---|---|
| `issue_date` | Origination date | **The only date the project trusts.** MTD/PMTD, monthly trend, cohorts |
| `last_payment_date` | Most recent payment received | Only in data-quality checks — it is broken |
| `next_payment_date` | Expected next payment | Nothing |
| `last_credit_pull_date` | Last credit report pull | Nothing |

**Trap: dates are day-first.** `11-02-2021` is 11 February, not 2 November. Python passes
`format="%d-%m-%Y"` explicitly (`config.SOURCE_DATE_FORMAT`); SQL Server needs
`SET DATEFORMAT dmy`; Power BI and Excel need "using locale → English (United Kingdom)".
A US-locale parse would silently reassign loans to the wrong month, corrupting every
MTD/PMTD/MoM figure while leaving the totals untouched — the worst kind of bug, because
nothing crashes. `validate.check_dates_are_day_first()` guards it by asserting `issue_date`
lands in a single calendar year.

### Derived columns (added by `data_loader.clean_loans()` and the SQL view)

`issue_month`, `issue_year`, `issue_month_name`, `issue_month_short`, `loan_quality`, plus
`term_clean` in the SQL view only. The risk layer adds more at runtime via
`risk.add_risk_flags()`: `is_charged_off`, `is_closed`, `net_margin`, `dti_band`,
`loan_size_band`, `income_quintile`.

---

## 4. The business problem

Read `docs/problem_statement.md` in full. The summary:

> A bank needs a reporting layer over its loan book to monitor lending activity, track
> portfolio health, and spot trends that should feed into lending strategy.

Three dashboards, all on the same dataset:

**Dashboard 1 — Summary.** Five headline KPIs (applications, funded, received, avg interest
rate, avg DTI), each reported three ways: total, MTD, MoM. Plus the Good/Bad loan split, plus
a grid with one row per `loan_status`.

**Dashboard 2 — Overview.** Six visuals, each showing the *same three measures* broken down
a different way: month (line), state (filled map), term (donut), employment length (bar),
purpose (bar), home ownership (tree map).

**Dashboard 3 — Details.** One flat table so a user can drill from any aggregate straight to
the underlying loan rows.

**Cross-cutting requirements.** Every dashboard filterable by grade, sub-grade, purpose,
term, home ownership, verification status, state and date range. Pages linked by navigation
buttons. **And the requirement that shapes the whole architecture:** the same numbers must
appear whichever tool is used — SQL, Python, Power BI, Excel or Tableau.

That last requirement is why `docs/VERIFICATION.md` exists as a single reference table and
why `kpis.py` mirrors `sql/02`–`sql/04` function-for-query. It is not redundancy for its own
sake; it is a reconciliation mechanism.

**What the problem statement does not ask for, and the risk layer adds anyway:** default
rates, recovery rates, segment profitability, concentration, whether risk-based pricing
works. The reporting layer counts. The risk layer judges. That gap is the honest answer to
"what did you add?"

---

## 5. The SQL layer

Six scripts, meant to be run in order. `tests/test_sql.py::test_scripts_are_numbered_in_run_order`
asserts the numbering is contiguous.

### `sql/01_schema_and_load.sql` (103 lines) — set up and load

Creates `bank_loan_db` if absent, drops and recreates `dbo.bank_loan_data` with explicit
column types, and loads the CSV. The baseline implementation uses the SQL Server *Import Flat File* wizard;
this script does it as code so the project is reproducible and the date columns land as real
`DATE` values instead of text.

It sets `DATEFORMAT dmy` around the load —
`tests/test_sql.py::test_bulk_insert_sets_dateformat` enforces that.

This is the **only** script permitted to contain destructive statements
(`DROP`, `TRUNCATE`, `DELETE`);
`tests/test_sql.py::test_no_destructive_statements_outside_the_load_script` asserts scripts
`02`–`06` are read-only. That is a real safety property: a reviewer can run any analytical
script against a production database without fear.

### `sql/02_summary_kpis.sql` (120 lines) — Dashboard 1 headline KPIs

Declares the reporting anchors once and reuses them:

```sql
DECLARE @max_date   DATE = (SELECT MAX(issue_date) FROM dbo.bank_loan_data);
DECLARE @mtd_start  DATE = DATEFROMPARTS(YEAR(@max_date), MONTH(@max_date), 1);
DECLARE @pmtd_start DATE = DATEADD(MONTH, -1, @mtd_start);
```

Then returns all five KPIs in one result set with Total / MTD / PMTD / MoM columns. The
`@max_date` derivation is the whole point: refresh the table with 2022 data and the script
still reports the right months.

### `sql/03_good_bad_loan.sql` (83 lines) — Good/Bad split and status grid

Two things worth studying:

```sql
COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ()   AS application_pct
```

`SUM(COUNT(*)) OVER ()` is an aggregate wrapped in a window function — it gives each group's
count next to the grand total *in one pass*, with no subquery and no second scan. This is
the single most useful window-function pattern in analytics and you should be able to explain
it cold.

```sql
CROSS APPLY (VALUES (
    CASE WHEN l.loan_status IN ('Fully Paid', 'Current') THEN 'Good Loan'
         ELSE 'Bad Loan' END)) AS quality(category)
```

`CROSS APPLY (VALUES ...)` defines the derived `category` column once and lets you both
`SELECT` and `GROUP BY` it without repeating the `CASE`. Note the `ELSE 'Bad Loan'` fallback
— unlike the Python version, this puts an unknown future status into Bad Loan silently.

### `sql/04_overview_charts.sql` (120 lines) — Dashboard 2

One query per visual, six in total, each returning the identical three measures:
`COUNT(id)`, `SUM(loan_amount)`, `SUM(total_payment)`. That uniformity is deliberate — it is
what lets one Power BI slicer drive all six visuals through a single `Selected Measure`.
Otherwise plain `GROUP BY`, with `MONTH()` / `DATENAME(MONTH, ...)` for the trend. Nothing
clever here, and there should not be.

### `sql/05_details_and_quality.sql` (99 lines) — Dashboard 3 and views

Creates `dbo.vw_loan_details` (the flat grid) and the enriched view
`dbo.vw_bank_loan_enriched` that the BI tools connect to. The view is where `term_clean`,
`dti_pct`, `int_rate_pct` and the month helper columns live, so the transformation happens
once in the database instead of five times in five tools.

### `sql/06_risk_and_cohort_analysis.sql` (501 lines) — the analytical script

This is the file to study hardest. Its own header explains why it exists:

> Scripts 02-05 reproduce the dashboard KPIs: they are aggregation queries that answer "how
> much" and "how many". [...] This script answers the questions the dashboard does NOT:
> which segments lose money, how each segment ranks against its peers, how the portfolio
> accumulates over the year, and whether risk-based pricing actually held.

Eight sections. Every one carries an `/* Expected: ... */` comment block with the values it
produces on the full dataset, so a reader can verify without a database.

`tests/test_sql.py` asserts this file uses window functions, CTEs and a join, applies volume
floors, documents its denominator, and references the data-quality doc.

#### Teaching CTEs from section 1

```sql
WITH status_economics AS (
    SELECT loan_status,
           COUNT(*)           AS loans,
           SUM(loan_amount)   AS funded,
           SUM(total_payment) AS received,
           SUM(total_payment) - SUM(loan_amount) AS net_cash
    FROM dbo.bank_loan_data
    GROUP BY loan_status
)
SELECT loan_status, loans, funded, received, net_cash,
       CAST(received * 100.0 / NULLIF(funded, 0)   AS DECIMAL(8,2)) AS recovery_pct,
       CAST(loans  * 100.0 / SUM(loans)  OVER ()   AS DECIMAL(8,2)) AS pct_of_loans,
       CAST(funded * 100.0 / SUM(funded) OVER ()   AS DECIMAL(8,2)) AS pct_of_funded
FROM status_economics
ORDER BY net_cash;
```

**What a CTE is, concretely:** `WITH name AS (query)` gives a query a name so the outer query
can treat it like a table. Three reasons it is used here:

1. **You cannot reference an aggregate alias in the same `SELECT`.** `recovery_pct` needs
   `received / funded`, but both are `SUM()`s computed in this query. Without the CTE you
   would have to write `SUM(total_payment) * 100.0 / NULLIF(SUM(loan_amount), 0)` again.
2. **You cannot window over an aggregate you are still computing.** `SUM(loans) OVER ()`
   needs `loans` to already exist as a column. The CTE materialises it first.
3. **Readability.** Aggregate first, derive second. Each layer does one job.

**A CTE is not a temp table.** It is not materialised or indexed; SQL Server inlines it into
the plan. So "I used a CTE for performance" is wrong — use `#temp` tables or indexed views
for that. Say "for readability and to reference derived columns."

**`NULLIF(funded, 0)`** turns a zero denominator into `NULL`, so division yields `NULL`
rather than raising a divide-by-zero error. It appears throughout `sql/06`. The Python
equivalent is `.replace(0, pd.NA)` in `risk.segment_risk()`; the DAX equivalent is `DIVIDE()`.

**`* 100.0` not `* 100`** — in T-SQL, `int / int` does integer division. `5333 * 100 / 38576`
would return `13`; `5333 * 100.0 / 38576` returns `13.82...`. This is a genuinely common
interview trap.

#### Teaching window functions from sections 2, 3, 4 and 6

A window function computes a value across a set of rows *related to the current row*, without
collapsing them the way `GROUP BY` does. Syntax: `FUNCTION() OVER (PARTITION BY ... ORDER BY
... ROWS ...)`.

The three clauses:

- **`PARTITION BY`** — reset the calculation for each group. Omit it and the window is the
  whole result set.
- **`ORDER BY`** — inside the window, decides ranking order and what "preceding" means.
- **frame (`ROWS BETWEEN ...`)** — which rows around the current one are in scope.

**Section 2 — `RANK()` and `LAG()` over grades:**

```sql
RANK() OVER (ORDER BY default_rate_pct DESC)                AS risk_rank,
CAST(default_rate_pct - LAG(default_rate_pct) OVER (ORDER BY grade)
     AS DECIMAL(8,2))                                       AS default_rate_step_vs_prev_grade,
CAST(SUM(funded) OVER (ORDER BY grade ROWS UNBOUNDED PRECEDING)
     * 100.0 / SUM(funded) OVER () AS DECIMAL(8,2))          AS cumulative_pct_of_funded
```

- `RANK()` numbers rows by an ordering; ties share a rank and the next rank skips.
- `LAG(col)` reaches back to the previous row *in the window's order*. Here, ordered by
  grade, it gives the step change from the next-better grade — turning a level (A 5.70%,
  B 11.50%) into a gradient (+5.80pp). First row is `NULL` because there is nothing before it.
- `SUM(...) OVER (ORDER BY grade ROWS UNBOUNDED PRECEDING)` is a **running total**: sum
  everything from the first row up to this one. Divided by the grand total, it becomes a
  cumulative share.

Know the difference between the three ranking functions, because it is asked constantly:

| Function | Ties | Gaps after ties |
|---|---|---|
| `ROW_NUMBER()` | Broken arbitrarily; always distinct | n/a |
| `RANK()` | Same rank | Yes (1,1,3) |
| `DENSE_RANK()` | Same rank | No (1,1,2) |

All three appear in `sql/06`: `ROW_NUMBER()` in section 3, `RANK()` in sections 2 and 7,
`DENSE_RANK()` in section 5 (`worst_recovery_rank`).

**Section 3 — `PARTITION BY` and `NTILE`:**

```sql
ROW_NUMBER() OVER (ORDER BY charged_off * 1.0 / loans DESC)                  AS overall_risk_rank,
ROW_NUMBER() OVER (PARTITION BY grade ORDER BY charged_off * 1.0 / loans DESC) AS risk_rank_in_grade,
NTILE(4)     OVER (ORDER BY charged_off * 1.0 / loans DESC)                  AS risk_quartile
```

Two `ROW_NUMBER()`s over the same data with different windows: one global ranking, one that
restarts inside each parent grade so you can see "the worst B sub-grade". `NTILE(4)` splits
the ordered set into four roughly equal buckets — quartiles.

Also note `HAVING COUNT(*) >= 20` in that section's CTE. `WHERE` filters rows *before*
aggregation; `HAVING` filters groups *after*. You need `HAVING` here because the condition is
on `COUNT(*)`, which does not exist until the aggregate runs.

**Section 4 — running totals, MoM, and a moving average:**

```sql
SUM(applications) OVER (ORDER BY issue_month ROWS UNBOUNDED PRECEDING)      AS ytd_applications,
CAST((funded - LAG(funded) OVER (ORDER BY issue_month)) * 100.0
     / NULLIF(LAG(funded) OVER (ORDER BY issue_month), 0) AS DECIMAL(8,2))  AS funded_mom_pct,
CAST(AVG(applications * 1.0) OVER (ORDER BY issue_month
                                   ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
     AS DECIMAL(10,1))                                                      AS applications_3mo_avg
```

Three frames, three meanings:

- `ROWS UNBOUNDED PRECEDING` → everything so far → year-to-date total.
- No frame, just `LAG` → one specific prior row → month-over-month growth. This is the same
  MoM definition as the dashboard cards, expressed in SQL.
- `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` → a sliding 3-row window → 3-month moving
  average, which smooths monthly noise.

If you learn one thing about frames: `ROWS` counts physical rows; `RANGE` counts logical
value ranges and treats ties as one unit. The default frame when you supply `ORDER BY`
without a frame clause is `RANGE UNBOUNDED PRECEDING AND CURRENT ROW`, which is *not* the
same as `ROWS` when there are duplicate ordering values. `sql/06` writes `ROWS` explicitly
to avoid that ambiguity.

**Section 6 — the Pareto pattern:**

```sql
CAST(SUM(funded) OVER (ORDER BY funded DESC ROWS UNBOUNDED PRECEDING)
     * 100.0 / SUM(funded) OVER () AS DECIMAL(8,2)) AS cumulative_pct_of_funded
```

Running total over a *descending* order = a cumulative concentration curve. That single
expression is the SQL equivalent of a Pareto chart, and it produces the concentration finding
in section 11.

#### Teaching joins from section 7

Section 7 answers "which term × grade combinations are materially worse than the portfolio as
a whole?" — which needs every row compared to one global number.

```sql
WITH closed_loans AS (
    SELECT * FROM dbo.bank_loan_data
    WHERE loan_status IN ('Fully Paid', 'Charged Off')
),
portfolio AS (
    SELECT COUNT(*) AS total_closed,
           SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) * 100.0
               / COUNT(*) AS portfolio_default_pct
    FROM closed_loans
),
segment AS (
    SELECT LTRIM(RTRIM(term)) AS term, grade, COUNT(*) AS loans, ...
    FROM closed_loans
    GROUP BY LTRIM(RTRIM(term)), grade
    HAVING COUNT(*) >= 100
)
SELECT s.term, s.grade, s.loans,
       s.default_pct - p.portfolio_default_pct AS excess_default_pp,
       s.default_pct / NULLIF(p.portfolio_default_pct, 0) AS risk_multiple,
       RANK() OVER (ORDER BY s.default_pct DESC) AS risk_rank
FROM segment AS s
CROSS JOIN portfolio AS p
ORDER BY s.default_pct DESC;
```

**Why `CROSS JOIN`:** `portfolio` returns exactly **one row**. A cross join (Cartesian
product) of N rows × 1 row = N rows, each now carrying the benchmark columns and available
for arithmetic. A cross join against a single-row CTE is the clearest way in SQL to broadcast
a global benchmark.

**Why not a window function:** you could write `AVG(...) OVER ()` instead, and section 1 of
the same file does exactly that. The trade-off, which the script's own comment flags: the
window version keeps it to one pass and no join, but the CROSS JOIN version names the
benchmark, lets you compute it on a *different* row set (here: all closed loans, before the
100-loan floor is applied), and reads more explicitly. Being able to argue both sides is
better than having a favourite.

**Join types, for completeness** — this project barely joins because it is a single flat
table. Know them anyway: `INNER`, `LEFT`, `RIGHT`, `FULL OUTER`, `CROSS`. The only structural
join in the whole repository is the Power BI relationship
`date_table[Date] 1 → * bank_loan_data[issue_date]`.

#### Section 8 — assertions in SQL

A `UNION ALL` of nine independent scalar checks, each returning a name, a PASS/WARN status and
the observed value. Seven PASS, two WARN — and the two WARNs are *expected*. It mirrors the
Python validation suite so the database and the pipeline agree on what "clean" means.

---

## 6. The KPI layer

Everything below lives in `src/bank_loan_report/kpis.py`. Each function has a SQL
counterpart. This is the section to be able to recite.

### The five headline KPIs

**Total Loan Applications** — `kpis.total_loan_applications()`

```python
int(df["id"].count())
```
SQL: `COUNT(id)`. DAX: `COUNT ( bank_loan_data[id] )`.
Value: **38,576**.
Why it matters: raw demand and throughput. It is the denominator for the Good/Bad
percentage, so it has to be a count of *loans*, not borrowers or applications-including-rejections.
Business question: how much business are we writing, and is it growing?

**Total Funded Amount** — `kpis.total_funded_amount()`

```python
float(df["loan_amount"].sum())
```
SQL: `SUM(loan_amount)`. DAX: `SUM ( bank_loan_data[loan_amount] )`.
Value: **$435,757,075**.
Why it matters: this is capital deployed — the exposure at risk and the number the balance
sheet cares about. Applications can grow while funding shrinks (smaller tickets), so you need
both.
Business question: how much capital have we put out, and is the average ticket changing?

**Total Amount Received** — `kpis.total_amount_received()`

```python
float(df["total_payment"].sum())
```
SQL: `SUM(total_payment)`. DAX: `SUM ( bank_loan_data[total_payment] )`.
Value: **$473,070,933**.
Why it matters: cash actually collected. Against funded it gives the recovery rate, which is
the closest thing this dataset has to a profitability measure.
Business question: are we getting our money back, with interest?

**Average Interest Rate** — `kpis.average_interest_rate()`

```python
float(df["int_rate"].mean() * 100) if len(df) else 0.0
```
SQL: `AVG(int_rate) * 100.0`. DAX: `AVERAGE ( bank_loan_data[int_rate] ) * 100`.
Value: **12.0488%**.
Why it matters: it is the price of risk. Rising average rate means either the market moved or
the book is drifting toward riskier grades — and you can tell which by cutting the same
metric by grade.
Business question: what are we charging, and why is it moving?
Caveat: this is an **unweighted mean of loans**, not weighted by principal. A $1,000 loan at
20% counts the same as a $35,000 loan at 7%. That is what the problem statement specifies; a
funded-weighted average would be a more meaningful portfolio yield. Know the difference.

**Average DTI** — `kpis.average_dti()`

```python
float(df["dti"].mean() * 100) if len(df) else 0.0
```
SQL: `AVG(dti) * 100.0`. DAX: `AVERAGE ( bank_loan_data[dti] ) * 100`.
Value: **13.3274%**.
Why it matters: an aggregate measure of borrower leverage — a proxy for how stretched the
book's customers are.
Business question: are we lending to progressively more indebted people?

Each of the five is computed three ways by `kpis.summary_kpis()`, which loops the same five
functions over three DataFrames (full, MTD slice, PMTD slice) and calls
`kpis.mom_change(m, p)`. The KPI is defined once and applied to different row sets — the
`_METRICS` dict is the definition, and that structure means a change to a formula
automatically flows into total, MTD and PMTD.

### The period helpers

```python
def latest_period(df):   # (year, month) of max issue_date -> (2021, 12)
def previous_period(y,m): return (y-1, 12) if m == 1 else (y, m-1)
def filter_period(df,y,m): return df[(df.issue_year==y) & (df.issue_month==m)]
def mtd_frame(df):  return filter_period(df, *latest_period(df))
def pmtd_frame(df): return filter_period(df, *previous_period(*latest_period(df)))
```

Note `previous_period` handles the January → previous-December rollover. This dataset never
exercises that path (it is a single calendar year), but the logic is there and it is the
right thing to test.

### Good/Bad loan block — `kpis.good_bad_loan_kpis()`

Iterates over `config.GOOD_LOAN_STATUSES` and `config.BAD_LOAN_STATUSES`, filters with
`.isin()`, and returns category, statuses included, share of applications, count, funded and
received. Values in section 2 above.
Why it matters: it is the one-glance portfolio-health number. 13.825% bad.
Business question: what fraction of what we wrote went wrong?

### Loan status grid — `kpis.loan_status_grid()`

A `groupby("loan_status")` producing total applications, funded, received, avg rate, avg DTI,
then a **left merge** with an MTD-only aggregation to add `mtd_funded_amount` and
`mtd_amount_received`, with `fillna(0)`.

The left merge is the interesting bit: it guarantees a row for every status even if that
status had no December originations. An inner join would silently drop it. `fillna(0)` then
makes "no MTD activity" read as zero rather than blank.

| Status | Applications | Funded | Received | Avg rate | Avg DTI |
|---|---|---|---|---|---|
| Charged Off | 5,333 | $65,532,225 | $37,284,763 | 13.879% | 14.005% |
| Current | 1,098 | $18,866,500 | $24,199,914 | 15.099% | 14.724% |
| Fully Paid | 32,145 | $351,358,350 | $411,586,256 | 11.641% | 13.167% |

Read that table as an insight, not a grid: `Current` loans carry the **highest** average
interest rate (15.10%) and the highest DTI (14.72%). The still-open book is the riskiest
slice of the portfolio. That is worth a sentence in an interview.

### The six Overview aggregations

All six go through one private helper, `kpis._aggregate(df, keys)`, which does a
`groupby(keys, observed=True).agg(...)` producing the same three measures. Then:

| Function | Grouped by | Sorted by | Feeds |
|---|---|---|---|
| `by_month` | month number, name, short name | month number | Line chart |
| `by_state` | `address_state` | state | Filled map |
| `by_term` | `term` | term | Donut |
| `by_emp_length` | `emp_length` | the ordered categorical | Bar |
| `by_purpose` | `purpose` | applications desc | Bar |
| `by_home_ownership` | `home_ownership` | applications desc | Tree map |

`observed=True` matters: with a categorical grouper, pandas would otherwise emit rows for
unobserved categories. And `by_emp_length` sorts correctly only because
`clean_loans()` made `emp_length` an *ordered* `pd.Categorical` — a plain string sort would
put `10+ years` between `1 year` and `2 years`.

### `kpis.details_table()`

Selects the 17 columns of Dashboard 3 in the specified order, sorted by `issue_date`, with an
optional `limit`. The column list matches `dbo.vw_loan_details` in `sql/05` exactly.

### The risk-layer metrics

From `src/bank_loan_report/risk.py`. These have no baseline implementation counterpart.

**Recovery rate** — `received / funded * 100`, per segment in `segment_risk()`. Portfolio:
108.56%.
Business question: for every dollar lent, how much came back?

**Default rate** — `charged_off_loans / loans * 100`. 13.82% all loans; 14.23% closed only.
Business question: what share of loans went bad?

**Net margin** — `received - funded`. +$37,313,858 portfolio-wide.
Business question: did this segment make or lose cash?

**Risk multiple** — `segment_default_pct / portfolio_default_pct`, in `term_grade_risk()`.
Business question: how many times the portfolio average does this segment default?
Worst: 60-month grade F at **2.40×**. Best: 36-month grade A at **0.39×**.

**Excess default (pp)** — `segment_default_pct - portfolio_default_pct`. The same idea in
percentage points instead of a ratio — additive rather than multiplicative. 60mo F is
+19.99pp.

**Pricing power** — `pricing_power()` correlates each sub-grade's average interest rate
against its realised default rate, over the 35 sub-grades with ≥20 loans:
**Pearson r = 0.9337, Spearman ρ = 0.9585**.
Business question: does the bank's grading system actually predict who defaults, or is the
grade decorative? Answer: it predicts, strongly.
Why both coefficients: Pearson measures linear association and is sensitive to outliers;
Spearman measures *monotonic rank* association and is not. Spearman being the higher of the
two says the ordering is nearly perfect even where the relationship bends. For "does the
ranking hold?", Spearman is the right statistic.

**Concentration** — `concentration()` computes running shares of funded amount for the top
1/3/5/10 states, top 1/3/5 purposes and top 1/3 grades. Numbers in section 11.

---

## 7. The Python layer

Nine modules under `src/bank_loan_report/`. The split is not arbitrary — each module has one
reason to change.

```
config.py        settings, paths, business rules            (no pandas logic)
data_loader.py   load, clean, profile                       (I/O boundary)
validate.py      13 executable data-quality checks          (contract)
kpis.py          the dashboard KPI layer, mirrors sql/02-04  (reporting)
risk.py          risk and profitability, mirrors sql/06      (analysis)
charts.py        the six Overview visuals                    (presentation)
risk_charts.py   the four risk visuals                       (presentation)
cli.py           command dispatch and formatting             (interface)
__main__.py      `python -m bank_loan_report`                (entry point)
```

### `config.py` — one place for rules and paths

Holds `PROJECT_ROOT`, `DATA_DIR`, `RAW_CSV_PATH`, `SAMPLE_CSV_PATH`, `FIGURES_DIR`,
`DATE_COLUMNS`, `SOURCE_DATE_FORMAT = "%d-%m-%Y"`, `GOOD_LOAN_STATUSES`,
`BAD_LOAN_STATUSES`, and a frozen `DatabaseSettings` dataclass that builds a SQLAlchemy URL
from environment variables.

Three design points worth defending:

1. **Every value is `os.getenv`-overridable.** No hard-coded absolute paths, so the project
   runs on any machine and in CI.
2. **No secrets in the file.** `DatabaseSettings` reads `DB_USER` / `DB_PASSWORD` from the
   environment, `quote_plus`-escapes them, and raises if neither credentials nor
   `DB_TRUSTED_CONNECTION` are set. `.env` is gitignored; `.env.example` holds placeholders.
3. **The Good/Bad rule lives here, not in five places.** `kpis.good_bad_loan_kpis()`,
   `data_loader.clean_loans()`, `risk.BAD_STATUS` and
   `validate.check_known_loan_statuses()` all import it. Change the rule once and it
   propagates. Now compare that to the SQL, DAX, Tableau and Excel layers, where the same
   rule is restated — which is exactly why `tests/test_sql.py::test_business_rules_are_spelled_consistently`
   exists.

### `data_loader.py` — the I/O boundary

`resolve_data_path()` implements a precedence chain: explicit `--data` path > raw CSV if it
exists > bundled sample > `FileNotFoundError` with a pointer to `data/README.md`. That chain
is what makes the same code path work locally with the full dataset and in CI with the
sample.

`load_loans()` reads the CSV, asserts all 24 `EXPECTED_COLUMNS` are present (raising
immediately if not), then calls `clean_loans()`.

`clean_loans()` does five things, in order:

1. Parse the four date columns with the explicit `format="%d-%m-%Y"` and `errors="coerce"`.
2. Strip whitespace from every text column — which is what fixes `" 36 months"`.
3. Add `issue_month`, `issue_year`, `issue_month_name`, `issue_month_short`.
4. Classify `loan_quality` explicitly into `Good Loan` / `Bad Loan` / `Unclassified`.
5. Make `emp_length` an ordered categorical using `EMP_LENGTH_ORDER`, filtered to values
   actually present.

Two things to notice. First, `df.copy()` at the top: no function in this codebase mutates its
input. Second, `errors="coerce"` turns unparseable dates into `NaT` instead of raising — a
deliberate choice, because `validate.check_kpi_columns_not_null()` will then catch nulls in
`issue_date` as a FAIL. Fail at the validation gate with a clear message, not at read time
with a stack trace.

`data_quality_report()` returns per-column dtype, null count, null percentage and distinct
count — this is what `python -m bank_loan_report quality` prints.

### `validate.py` — the contract

Covered in section 9.

### `kpis.py` and `risk.py` — pure analysis

Neither module reads a file, prints anything, or writes anything. Every function takes a
DataFrame and returns a DataFrame or a scalar. That is why they are testable: `tests/test_kpis.py`
and `tests/test_risk.py` can construct tiny hand-made DataFrames with known answers and
assert on them without touching disk.

`kpis.py` exposes `OVERVIEW_AGGREGATIONS` (a dict of six functions) and `risk.py` exposes
`RISK_TABLES` (a dict of twelve). `cli.py`'s `export` command just iterates those dicts.
Adding a table means adding one dict entry — the CLI needs no change. That is the registry
pattern, and it is why `export` now writes 21 CSVs (9 KPI + 12 risk).

`risk.add_risk_flags()` deserves a close read, because it is where three derived risk
dimensions come from:

```python
out["dti_band"] = pd.cut(out["dti"] * 100,
                         bins=[-0.01, 10, 15, 20, 25, 100],
                         labels=["0-10%","10-15%","15-20%","20-25%","25%+"])
out["loan_size_band"] = pd.cut(out["loan_amount"],
                         bins=[0, 5_000, 10_000, 15_000, 20_000, 25_000, 1_000_000],
                         labels=["<$5K","$5-10K","$10-15K","$15-20K","$20-25K","$25K+"])
out["income_quintile"] = pd.qcut(out["annual_income"], 5,
                         labels=["Q1 (lowest)","Q2","Q3","Q4","Q5 (highest)"],
                         duplicates="drop")
```

**`pd.cut` vs `pd.qcut` — know this cold.** `cut` uses *fixed boundaries you choose*, so
bucket sizes are unequal (the `25%+` DTI band holds only 646 loans out of 38,576). `qcut`
uses *quantiles*, so each bucket holds roughly equal counts (the five income quintiles hold
7,746 / 7,686 / 7,714 / 7,746 / 7,684). Use `cut` when the boundaries are business-meaningful
and you want to talk about "loans over $25K". Use `qcut` when you want a fair comparison
across buckets of equal size — which is exactly right for income, where you want to compare
the poorest fifth to the richest fifth without one bucket dwarfing another.
Note `bins=[-0.01, ...]` on the DTI cut: `pd.cut` intervals are right-closed and
left-*open* by default, so a DTI of exactly 0 would be `NaN` with a lower bound of 0.
`duplicates="drop"` on `qcut` guards against repeated quantile edges when a value is very
frequent.

**Volume floors.** Every segment cut in the project suppresses thin buckets, at different
levels chosen for what the cut is used for:

| Floor | Where | Rationale |
|---|---|---|
| 20 loans | `pricing_power()`, `sql/06` §3 | 35 of 35 sub-grades survive; enough to correlate |
| 50 loans | `unprofitable_segments()`, `sql/06` §5 | purpose has 14 categories, smallest is 94 loans |
| 100 loans | `term_grade_risk()`, `sql/06` §7 | 13 of 14 term×grade cells survive |
| 250 loans | `risk_charts._volume_floor()` | 0.65% of rows; suppresses the 98-loan `OTHER` bucket |
| 300 loans | `risk_ranking()` | a cross-dimension league table needs comparable reliability |

The reason, in `segment_risk()`'s own docstring: "a 47-loan state with a 30% default rate is
noise, not a finding." `risk_charts._volume_floor()` is expressed as a *fraction* of the
dataset (0.65%, minimum 5) rather than a fixed count, specifically so the charts still render
on the 600-row sample in CI.

### `charts.py` and `risk_charts.py` — presentation

Both set `matplotlib.use("Agg")` at import time, before `pyplot` is imported. `Agg` is a
non-interactive backend: no display server needed, which is what makes chart rendering work
in CI. `risk_charts.py` imports the private `_save` and `_style_axis` helpers from
`charts.py` rather than duplicating them.

Ten PNGs are produced into `reports/figures/`:

```
01_monthly_trend.png        06_home_ownership.png
02_state_analysis.png       07_default_rate_by_grade.png
03_term_donut.png           08_recovery_by_purpose.png
04_emp_length.png           09_default_rate_by_segment.png
05_purpose.png              10_risk_pricing_scatter.png
```

`01`–`06` are the Overview visuals; `07`–`10` are the risk layer. `09` is a small-multiple
panel across six segments (term, income quintile, loan size, DTI band, home ownership,
employment length) — the "which borrower attributes actually predict default?" chart.

### `cli.py` — the interface

`argparse` with a required subcommand and two global flags. All the money and percentage
formatting lives here (`_money()`, `_fmt()`), which is the right place for it: the analysis
modules return raw numbers, and only the presentation layer decides that
`53981425.0` should read as `$53.98M`.

One design detail with real value: `validate` returns a **non-zero exit code** when there is a
blocking failure (`return 1 if blocking else 0`). That is what lets CI use it as a gate —
`python -m bank_loan_report --sample validate` fails the build if a KPI-guarding assumption
breaks.

### Why this structure rather than one notebook

Testable (pure functions with no I/O can be unit-tested; a notebook cannot), reusable (the
CLI, the tests and the notebook all import the same functions, so there is one implementation
of each KPI), diff-able (notebook JSON diffs are unreadable in review), and runnable in CI in
one line. The notebook still exists (33 cells) as narrative exploration *on top of* the
package — a consumer of the library, not the home of the logic.

---

## 8. The visualisation layer

Five presentation technologies. The obvious question is "why five?", and the honest answer is
"because the source baseline implementation is a multi-tool capstone." The *useful* answer is that each one
occupies a different niche, and you should be able to say what it is.

### Power BI — the primary dashboard

`powerbi/measures.dax` (32 measures), `powerbi/calendar_table.dax`,
`powerbi/power_query_steps.md`, `powerbi/README.md` (its text says 30 measures; the file
contains 32 — a stale count, worth knowing before someone else spots it).

Model: `bank_loan_data` fact imported from the SQL view `dbo.vw_bank_loan_enriched`, plus a
`date_table` dimension built with `CALENDAR`, related `date_table[Date] 1 → * bank_loan_data[issue_date]`,
single cross-filter direction, and marked as a date table.

**Why a separate date table at all?** Because DAX time-intelligence functions
(`DATESMTD`, `TOTALYTD`, `SAMEPERIODLASTYEAR`) require a contiguous, gap-free date dimension
marked as such. `issue_date` in the fact table has gaps — no loans were issued after
2021-12-12 — so time intelligence over the fact column alone is unreliable.

Measure groups in `measures.dax`: headline totals, MTD, PMTD, MoM, Good loan, Bad loan, and a
`Selected Measure` switch. The `* 100` for `int_rate` and `dti` happens in the measure, and
`DIVIDE()` guards the MoM denominators.

The `Selected Measure` pattern is worth understanding: a disconnected `measure_selection`
table feeds a slicer, and one `SWITCH`-based measure returns whichever of the three measures
the user picked. That is how one slicer drives all six Overview visuals. The file also
documents the alternative (a native Power BI *field parameter*, which is what the baseline implementation
uses) and explains the trade-off: field parameters need a recent Desktop version; the
`SWITCH` pattern works everywhere and is easier to keep in source control.

Import mode, not DirectQuery — the MTD/PMTD time-intelligence measures need it.

### Tableau — the same story, different grammar

`tableau/calculated_fields.md`. Documents `DATEPARSE("dd-MM-yyyy", [Issue Date])`,
`TRIM([Term])`, the `* 100` rate conversions, and — the interesting part — Level-of-Detail
expressions for the period anchors:

```
// Current Month
{ FIXED : MAX( DATETRUNC('month', [Issue Date]) ) }
```

`{ FIXED : ... }` computes at a fixed level of detail *independent of the visual's own
granularity*. That is Tableau's answer to the same problem DAX solves with `CALCULATE` +
`ALL`: you need a value that ignores the current filter/row context so every mark can be
compared against it. Being able to name the equivalent concept in two tools is genuinely
useful in an interview.

### Excel — the pivot-table build

`excel/README.md`. Two data paths (SQL Server connection or CSV with locale
English (United Kingdom)), loaded to the **Data Model** rather than a sheet so all pivots
share one cache and one set of slicers. Eleven named pivot tables on a hidden `Pivots` sheet
feed the dashboard.

Note the explicit warning: format rate fields as **Percentage, 2 decimals** and do *not*
multiply by 100 in the pivot, or the percent format double-scales them. That is the same
fraction-vs-percentage trap, third occurrence.

Why Excel exists here at all: it is the tool a business stakeholder can open and poke at
without a licence, a server, or asking you.

### matplotlib — the reproducible, version-controlled visuals

`charts.py` and `risk_charts.py` — the only visual layer that actually runs in CI and produces
committed artefacts. No GUI, no licence, no manual clicks: `python -m bank_loan_report charts`
regenerates all ten PNGs deterministically.

### The honest summary of this layer

| Tool | What is in the repo | What is not |
|---|---|---|
| Power BI | 32 DAX measures, calendar DAX, Power Query steps, page-by-page spec | The `.pbix` file. The DAX has never been executed or rendered |
| Tableau | Every calculated field, parameter and LOD expression | The `.twbx` file |
| Excel | Full pivot-and-slicer build guide | The `.xlsx` file |
| matplotlib | The code *and* the 10 output PNGs | — |

The binaries are absent because they cannot be reconstructed from a video, and each build
guide says so in its first paragraph. This is a real limitation and you should state it
before being asked: the Power BI, Tableau and Excel layers are *specifications verified by
reading*, not artefacts verified by running. The reconciliation target for all three is
`docs/VERIFICATION.md` — "if your dashboard disagrees with this table, the dashboard is
wrong."

---

## 9. Validation and data quality

`src/bank_loan_report/validate.py` is the module that most distinguishes this project from a
baseline implementation reproduction. Its premise, from its own docstring:

> Every dashboard number in this project rests on assumptions about the source data. This
> module states those assumptions as executable checks so that a refreshed or replaced dataset
> either passes them or fails loudly.

### Three severities

| Severity | Meaning | Consequence |
|---|---|---|
| `FAIL` | The check guards a KPI. If it fails, published numbers are wrong. | `blocking_failures()` returns it; CLI exits 1; CI fails |
| `WARN` | A known defect in the source data that limits analysis but does not invalidate volume/amount KPIs | Reported, documented, not patched |
| `INFO` | A profiling observation, recorded so reviewers can see it was considered | Reported only |

That taxonomy is the design idea. "The data has problems" is not actionable. "These nine
problems would make the KPIs wrong, these two limit what I can analyse, and these two I
looked at and consciously ignored" is.

### The 13 checks

**Nine FAIL-severity checks — all currently PASS:**

| Check | Guards against | Observed |
|---|---|---|
| schema: all expected columns present | A renamed or dropped column | all 24 source columns present |
| grain: one row per loan id | Duplicate rows double-counting every sum | 38,576 rows, 38,576 distinct ids |
| completeness: no nulls in KPI-driving columns | A null silently dropping out of a `SUM`/`AVG` | all KPI columns complete |
| business rule: every loan_status is classified | A new status falling into the wrong bucket | statuses: Charged Off, Current, Fully Paid |
| units: int_rate and dti stored as fractions | The 100× error | int_rate max 0.2459, dti max 0.2999 |
| dates: issue_date parsed day-first | A US-locale month/day swap | issue_date spans 2021-01-01 to 2021-12-12 |
| cleaning: term values trimmed | `" 36 months"` splitting the term category | terms: 36 months, 60 months |
| ranges: monetary columns are non-negative | Sign errors in amounts | no negative amounts |
| plausibility: charged-off recovery below 100% | A misclassified status | charged-off recovery 56.90% of principal |

Two of these are worth explaining in detail because they encode real reasoning:

`check_rates_are_fractions()` triggers if `int_rate` or `dti` exceeds 1.5. Its docstring:
"The single most damaging silent error in this project would be a source file that switches to
whole percentages: every rate KPI would come out 100x too high without anything crashing."

`check_dates_are_day_first()` asserts `issue_date` covers exactly one calendar year. A
month-first parse of `DD-MM-YYYY` data would scatter loans across multiple years — and
critically, it "silently reassigns loans to the wrong month, which corrupts every MTD, PMTD
and MoM figure while leaving the totals untouched — the worst kind of bug."

**Two WARN checks — both currently firing:**

1. **`timeline: last_payment_date >= issue_date`** — **15,453 rows (40.1%)** have a last
   payment recorded *before* the loan was issued. `issue_date` → `last_payment_date` spans
   from **−336 days** to **+338 days**, median **3 days**.
2. **`timeline: repayment duration matches term`** — **100% of the 25,214 Fully Paid
   36-month loans close within 365 days**, median 3 days. A 36-month loan cannot be fully
   repaid in three days on schedule.

Together these say: **the date columns other than `issue_date` are not internally
consistent.** Consequences, and this is the important part:

- The volume and amount KPIs are **unaffected** — they use `loan_amount`, `total_payment`,
  `loan_status` and `issue_date` only.
- **No vintage, seasoning or time-to-default analysis is possible.** You cannot answer "of
  the loans issued in March, how many had defaulted by month 6", because the timeline data
  needed to answer it is wrong.
- The `monthly_risk_trend()` output and `sql/06` §4 are therefore **origination cohort**
  views showing each month's *final observed status*, not seasoning curves. Both say so in
  comments. This distinction is exactly the kind of thing a credit-risk interviewer will
  probe.
- It also explains the `Current` recovery rate of 128.27%, which would otherwise be
  inexplicable for loans still amortising.

The project's choice was to **document and constrain** rather than patch or drop. There is no
way to reconstruct the true payment dates, so inventing them would be worse than admitting
they are broken.

**Two INFO checks — both firing:**

1. `profiling: constant columns` — `application_type` is `INDIVIDUAL` for all 38,576 rows.
   No analytical value; excluded from every cut. Note the check deliberately scans only
   `EXPECTED_COLUMNS`, so the derived `issue_year` (legitimately constant, single-year data)
   is not falsely flagged.
2. `profiling: emp_title completeness` — 1,438 nulls (3.7%), 28,522 distinct values. A
   free-text field feeding no KPI, left as-is. The correct decision: imputing or dropping a
   column you do not use is busywork.

### Other data-quality facts recorded

- **5,860 rows have `total_payment < loan_amount`** — the borrower repaid less than
  principal. Expected for charged-off loans, and consistent with 5,333 charge-offs plus a
  small number of others.
- `member_id` is 1:1 with `id`, so there are no repeat borrowers.

### The runner

```python
CHECKS = (check_no_missing_columns, check_unique_ids, ..., check_emp_title_nulls)
def run_all(df):           return [check(df) for check in CHECKS]
def to_frame(results):     # tabular output
def blocking_failures(r):  return [x for x in r if x.severity == "FAIL" and not x.passed]
```

Each check is an independent function returning a `CheckResult` dataclass
(`name`, `severity`, `passed`, `detail`) whose `status` property resolves to `PASS` or the
severity. Adding a check means writing one function and adding it to the `CHECKS` tuple.

Run it: `python -m bank_loan_report validate` → 9 PASS, 2 WARN, 2 INFO, 0 blocking failures,
exit code 0.

`sql/06` §8 mirrors nine of these checks in T-SQL, so the database layer and the Python layer
agree on what "clean" means and either can be run standalone.

---

## 10. CI and testing

### The test suite

Four files, **127 collected tests** (more than the number of `def test_` functions because
several are parametrised across the six SQL files):

| File | Collected | Covers |
|---|---|---|
| `tests/test_kpis.py` | 27 | Every KPI function against hand-built DataFrames with known answers; MTD/PMTD derivation; the Good/Bad rule; the six Overview aggregations |
| `tests/test_risk.py` | 34 | `add_risk_flags`, banding, `segment_risk`, `term_grade_risk`, `pricing_power`, `concentration`, `monthly_risk_trend`, volume floors, the closed-loan denominator |
| `tests/test_sql.py` | 38 | Static analysis of all six SQL files |
| `tests/test_validate.py` | 18 | Each of the 13 checks against DataFrames deliberately constructed to pass or to fail |

`tests/test_validate.py` is the one to point at when asked "did you test your tests?" — it
builds a frame with untrimmed `term` values and asserts the check *fails*, builds one with
whole-percentage rates and asserts the units check *fails*, and so on. A validation suite that
has never been shown to fail is not a validation suite.

### What `tests/test_sql.py` actually does

This is the file people misunderstand, so be precise. It **statically analyses** the SQL. It
never connects to a database. `sqlglot` is imported via `pytest.importorskip`, so the tests
self-skip if the dev dependency is absent.

The 38 tests assert:

- Every script **parses as valid T-SQL** — the file is split on `GO` batch separators and
  each batch handed to `sqlglot.parse(..., dialect="tsql")`.
- Scripts are **numbered contiguously** in run order.
- The **business rules are spelled consistently** across files (the Good/Bad statuses).
- `sql/01` **sets `DATEFORMAT dmy`** around the bulk load.
- Period boundaries are **derived, not hard-coded** — no literal month 12.
- **No destructive statements** (`DROP`/`TRUNCATE`/`DELETE`) outside `sql/01`.
- `sql/06` **uses window functions** (parametrised across techniques), **uses CTEs and a
  join**, **applies volume floors**, **documents its denominator**, and **references the
  data-quality doc**.

### What CI runs

`.github/workflows/ci.yml`, on push to `main`, on every pull request, and on manual dispatch.
`ubuntu-latest`, Python **3.10, 3.11 and 3.12** in a matrix with `fail-fast: false`.

Steps:

1. **Install** — deps are listed inline rather than via `requirements.txt`, with a comment
   explaining why: `pyodbc` needs system ODBC headers that are not installed, so only the
   analysis deps are installed. Then `pip install -e . --no-deps`.
2. **Lint** — `ruff check src tests`.
3. **Test** — `pytest -v`. The workflow comments that exact-figure tests self-skip when the
   full dataset is absent, so CI validates structure and business rules on the bundled
   600-row sample.
4. **Validate** — `python -m bank_loan_report --sample validate`, which exits non-zero if a
   KPI-guarding assumption is violated.
5. **Smoke-test the CLI** — all six subcommands on `--sample`, including both chart modes and
   `export`, then `ls` the outputs to prove files were written.

### What CI verifies

- The package imports on three Python versions.
- Ruff finds no lint violations.
- All KPI and risk formulas are correct against hand-computed fixtures.
- All 13 validation checks behave correctly, in both directions.
- All six SQL scripts are syntactically valid T-SQL and satisfy the structural assertions.
- All six CLI commands run end to end and write their output files.
- The 600-row sample passes every FAIL-severity check.

### What CI does NOT verify — say this before you are asked

- **The SQL is never executed.** There is no SQL Server in CI. `sqlglot` proves the syntax
  parses; it does not prove a query returns the right rows. `docs/VERIFICATION.md` states
  this explicitly: SQL scripts — execution — "not executed".
- **The exact-figure tests skip in CI.** The full dataset is gitignored, so the assertions
  that pin real numbers do not run there. They pass locally when
  `data/raw/financial_loan.csv` is present. `docs/VERIFICATION.md` records 123 passed, 4
  skipped from a local full-dataset run.
- **No DAX is evaluated.** `measures.dax` is a text file. Nothing parses or executes it.
- **No Tableau or Excel artefact is verified.** Those are build guides.
- **The notebook is not executed in CI**, even though `nbconvert` and `nbformat` are
  installed. `docs/VERIFICATION.md` records a manual nbconvert run.
- **Chart *content* is not verified** — the smoke test proves PNG files appear, not that they
  are correct or legible.

### The reconciliation argument

Since the SQL cannot be executed in CI, what makes it trustworthy? The answer is
cross-implementation agreement. `risk.term_grade_risk()`'s docstring states it plainly:

> This is the Python counterpart of section 7 of `sql/06_risk_and_cohort_analysis.sql`; the
> two are expected to agree, and that agreement is what makes the SQL layer trustworthy
> without a live SQL Server in CI.

Every section of `sql/06` carries an `/* Expected: ... */` block with the values it should
produce, and those values were produced by the tested Python implementation. Two independent
implementations landing on the same number is meaningful evidence. It is *not* the same as
executing the SQL, and you should not claim it is.

---

## 11. Business insights — what the numbers actually say

Ten findings, each with its source. Learn three or four cold rather than all ten vaguely.

### 1. The book is profitable, and charge-offs cost 6.48% of everything lent

$435,757,075 funded, $473,070,933 received, net **+$37,313,858**, recovery **108.56%**.
Charge-offs consumed $65,532,225 of principal and returned $37,284,763 — a net cash loss of
**$28,247,462**, or **6.48% of total funded**.

The framing that matters: a 13.82% default rate sounds alarming until you notice charged-off
loans still recover 56.90% of principal, and interest on the performing 86% more than covers
the gap. Loss rate and default rate are different things.
Source: `risk.headline_risk_metrics()`, `risk.portfolio_economics()`, `sql/06` §1.

### 2. Risk-based pricing works — this is the strongest finding in the project

Across the 35 sub-grades with ≥20 loans, the average interest rate charged and the realised
default rate correlate at **Pearson r = 0.9337, Spearman ρ = 0.9585**.

The grade gradient is perfectly monotonic: A 5.70% → B 11.50% → C 16.02% → D 20.69% →
E 24.80% → F 30.25% → G 31.31%, with average rates climbing 7.35% → 21.40% alongside. Every
grade, including G, still recovers more than 100% of principal (G: 114.46%) — the bank is
being paid for the extra risk it takes.

Why it matters: this is the strongest possible evidence that the lender's underwriting model
is not decorative. If ρ had been near zero, the grade would be a label with no predictive
content and the entire pricing structure would need rebuilding.
Source: `risk.pricing_power()`, `risk.segment_risk(df, "grade")`, `sql/06` §2, chart
`10_risk_pricing_scatter.png`.

### 3. Term is an independent risk factor — and the dashboard hides it

The Overview dashboard shows term as a volume donut only: 36-month 28,237 loans (73.2%),
60-month 10,339 (26.8%). The risk cut shows 60-month loans default at **22.34%** versus
**10.71%** — more than double.

Restricting to closed loans and cutting term × grade (13 segments clear the 100-loan floor;
portfolio benchmark 14.23%):

| Segment | Loans | Default rate | Risk multiple |
|---|---|---|---|
| 60mo F | 751 | 34.22% | 2.40× |
| 60mo G | 240 | 32.08% | 2.25× |
| 60mo E | 1,758 | 29.75% | 2.09× |
| 60mo D | 1,806 | 28.68% | 2.02× |
| 36mo F | 206 | 26.21% | 1.84× |
| ... | | | |
| 36mo B | 9,075 | 10.16% | 0.71× |
| 60mo A | 380 | 9.21% | 0.65× |
| 36mo A | 9,274 | 5.57% | 0.39× |

Two readings, and the second is the one that makes the analysis good:

- Within **every** grade, the 60-month term is materially riskier. Term carries information
  the grade does not.
- But it does **not dominate** grade: 60-month grade A (9.21%) is still safer than 36-month
  grade B (10.16%). **Grade first, term second.**

That nuance is what separates "60-month loans are risky" from an actual credit finding.
Source: `risk.term_grade_risk()`, `sql/06` §7.

### 4. Small business is the only loss-making purpose

Of 14 purposes, exactly one returned less cash than it consumed: **small business** —
1,776 loans, **25.62%** default rate, **98.72%** recovery, net **−$308,283**.

The recommended action is *repricing or tighter criteria, not withdrawal*: it is 1 of 14
products and 5.5% of funded volume, its recovery is 98.7% (barely below break-even, not
catastrophic), and at a 25.6% default rate the pricing at 13.03% average is simply too thin
for the risk. Compare grade E, which defaults at 24.80% but charges 17.71% and returns
111.32%. Same risk, adequate price.

For contrast, debt consolidation is 18,214 loans and **53.3% of the entire funded book** at
109.18% recovery.
Source: `risk.unprofitable_segments()`, `sql/06` §5, chart `08_recovery_by_purpose.png`.

### 5. The portfolio is concentrated

| Dimension | Top 1 | Top 3 | Top 5 | Top 10 |
|---|---|---|---|---|
| States (of 50) | CA 18.01% | 34.84% | 46.70% | 64.94% |
| Purposes (of 14) | Debt consolidation 53.35% | 74.51% | 87.20% | — |
| Grades (of 7) | B 29.99% | 69.40% | — | — |

Nearly half the book sits in five states out of fifty, and over half in a single loan purpose.
Why it matters: a regional downturn in California or a shock to the debt-consolidation market
hits a disproportionate share of the book at once. Concentration is a risk the volume
dashboards cannot show, because they display each state as a share of a map rather than as a
cumulative curve.
Source: `risk.concentration()`, `sql/06` §6.

### 6. Income predicts default monotonically; DTI does not

Income quintiles (equal-sized buckets via `pd.qcut`):

| Quintile | Median income | Loans | Default rate |
|---|---|---|---|
| Q1 (lowest) | $30,000 | 7,746 | 17.04% |
| Q2 | $45,000 | 7,686 | 14.90% |
| Q3 | $60,000 | 7,714 | 14.47% |
| Q4 | $76,900 | 7,746 | 12.20% |
| Q5 (highest) | $117,764 | 7,684 | 10.50% |

Clean and monotonic — a 6.5pp spread from poorest to richest fifth.

DTI bands are neither:

| DTI band | Loans | Default rate |
|---|---|---|
| 20-25% | 6,623 | 15.93% |
| 15-20% | 8,851 | 14.96% |
| 10-15% | 9,653 | 13.87% |
| **25%+** | **646** | **12.23%** |
| 0-10% | 12,803 | 12.00% |

The highest-DTI band defaults *less* than the 10-15% band. Two readings worth offering:
the 25%+ bucket is only 646 loans (1.7% of the book) so it is thin; and its average interest
rate is the **lowest** of any band at 9.79%, which suggests those borrowers were
compensating on other credit dimensions strong enough that the bank priced them cheaply. The
honest conclusion: in this dataset DTI is a much weaker signal than either income or grade,
and it should not be used alone.
Source: `risk.segment_risk()` on `income_quintile` and `dti_band`, chart
`09_default_rate_by_segment.png`.

### 7. Bigger loans default more

| Loan size | Loans | Default rate |
|---|---|---|
| $25K+ | 1,583 | 19.84% |
| $20-25K | 2,953 | 17.85% |
| $15-20K | 4,507 | 16.24% |
| <$5K | 9,113 | 13.05% |
| $10-15K | 7,842 | 12.96% |
| $5-10K | 12,578 | 12.36% |

Broadly monotonic above $10K, with a mild bump at the smallest band. Note the confound: loan
size correlates with term and grade (60-month loans average $15,738 versus $9,670 for
36-month), so this is not a clean independent effect. Saying so is better than presenting it
as one.
Source: `risk.segment_risk(add_risk_flags(df), "loan_size_band")`.

### 8. Income verification is a risk *marker*, not a risk *reducer*

| Verification status | Loans | Default rate | Avg loan |
|---|---|---|---|
| Verified | 12,335 | **15.70%** | $15,968 |
| Source Verified | 9,777 | 14.14% | $10,136 |
| Not Verified | 16,464 | **12.24%** | $8,485 |

Counter-intuitive at first glance: verified borrowers default *more*. The explanation is in
the third column — verified loans average nearly twice the size. Verification is almost
certainly *triggered* by larger or more marginal applications, so the causal arrow points the
other way. This is a textbook selection-effect trap, and spotting it is a better signal to an
interviewer than any of the clean monotonic findings.
Source: `risk.segment_risk(df, "verification_status")`.

### 9. Employment length is essentially noise; home ownership is weak

Employment length default rates span **12.35% to 14.90%** across 11 buckets with **no
ordering** — `9 years` is the safest bucket at 12.35% and `10+ years` is among the riskiest at
14.90%. Yet employment length gets a dedicated bar chart on the Overview dashboard. That is a
useful observation about the dashboard: it shows *volume* by employment length, which is a
demand question, and the reader should not infer risk from it.

Home ownership: RENT 18,439 loans (14.57%), OWN 2,838 (13.99%), MORTGAGE 17,198 (12.97%). A
1.6pp spread — a weak signal, plausibly a proxy for income. The `OTHER` bucket at 18.37% and
net −$19,718 is only 98 loans, which is exactly why `risk_charts._volume_floor()` suppresses
it at 250 on the full dataset. `NONE` has 3 loans and should never be reported at all.
Source: `risk.segment_risk()` on `emp_length` and `home_ownership`.

### 10. Volume grew 85% through the year; cohort quality drifted mildly worse

January: 2,332 loans, $25,031,650 funded, 13.25% cohort default rate.
December: 4,314 loans, $53,981,425 funded, 15.04%.

That is **+85.0% applications** and **+115.7% funded** — funding grew faster than volume, so
the average ticket also grew. Applications rose every month except February.

The default-rate drift from 13.25% to 15.04% is "consistent with, but not proof of, looser
underwriting" (the wording in `sql/06` §4). Two reasons to hedge: the broken date columns
mean this is *final observed status by origination month*, not a seasoning curve; and
December's 4,314 loans cover only 12 days, so its cohort is not comparable in composition.
State the finding and the caveat together.

Also worth noting: state-level extremes among states with ≥300 loans — worst **NV 20.95%**
and **FL 17.27%**, best **TX 11.30%**, **AL 11.34%**, **PA 11.40%**. Nevada being 1.85× Texas
is a real geographic signal, though at 482 loans NV is thin.
Source: `risk.monthly_risk_trend()`, `sql/06` §4, `risk.segment_risk(df, "address_state")`.

---

## 12. Study checklist

Before this goes on a resume, be able to do all of the following **from memory, without
notes.**

### Numbers you must know cold

- [ ] 38,576 loans, 24 source columns, 29 after cleaning, all issued 2021-01-01 → 2021-12-12
- [ ] $435.76M funded, $473.07M received, +$37.31M net, 108.56% recovery
- [ ] 86.18% good / 13.82% bad; 5,333 charge-offs
- [ ] Default rate 13.82% all loans, 14.23% closed only, and **why the two differ**
- [ ] Charged-off recovery 56.90%; net loss $28.25M = 6.48% of funded
- [ ] Avg interest rate 12.05%, avg DTI 13.33%, avg loan $11,296, median $10,000
- [ ] MTD Dec 4,314 apps / $53.98M; PMTD Nov 4,035 / $47.75M; MoM +6.91% / +13.04%
- [ ] Grade default gradient A 5.70% → G 31.31%
- [ ] 36-month 10.71% vs 60-month 22.34% default
- [ ] Pricing power ρ = 0.959 across 35 sub-grades
- [ ] Small business: only loss-maker, net −$308,283, 25.62% default
- [ ] CA 18.01% of funded; top 5 states 46.70%; debt consolidation 53.35% of funded

### Definitions you must be able to state precisely

- [ ] Good Loan = `Fully Paid` or `Current`; Bad Loan = `Charged Off`
- [ ] Funded = `SUM(loan_amount)`; Received = `SUM(total_payment)`
- [ ] MTD = latest month in data; PMTD = the month before; MoM = `(MTD − PMTD)/PMTD`
- [ ] Recovery rate = received/funded; net margin = received − funded
- [ ] Default rate, both denominators, and which layer uses which
- [ ] Risk multiple vs excess default in percentage points
- [ ] DTI, grade/sub-grade, term, charge-off, installment

### Technical concepts you must be able to explain with a repo example

- [ ] What a CTE is, three reasons `sql/06` uses them, and why "for performance" is wrong
- [ ] `SUM(x) OVER ()` — value next to grand total in one pass
- [ ] `ROW_NUMBER` vs `RANK` vs `DENSE_RANK` — and where each appears in `sql/06`
- [ ] `LAG()` and how §4 turns levels into MoM growth
- [ ] `ROWS UNBOUNDED PRECEDING` (running total) vs `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`
      (moving average); `ROWS` vs `RANGE`
- [ ] `NTILE(4)` and `PARTITION BY` in §3
- [ ] `WHERE` vs `HAVING`, and why the volume floors must use `HAVING`
- [ ] `CROSS JOIN` against a single-row CTE vs the window-function alternative, and the
      trade-off
- [ ] `NULLIF` / `* 100.0` — divide-by-zero and integer-division guards
- [ ] `pd.cut` vs `pd.qcut`, and why income uses `qcut` but DTI uses `cut`
- [ ] Why `matplotlib.use("Agg")` before importing pyplot
- [ ] Why the left merge + `fillna(0)` in `loan_status_grid()`
- [ ] Why `emp_length` is an ordered categorical
- [ ] Power BI: why a separate `date_table`, marked as a date table, Import not DirectQuery
- [ ] The `SWITCH` + disconnected table pattern vs a field parameter
- [ ] Tableau `{ FIXED : ... }` as the LOD analogue of DAX context manipulation
- [ ] The two data traps: day-first dates, and fractions-not-percentages

### Architecture you must be able to draw on a whiteboard

- [ ] CSV → SQL Server (`01`) → KPI queries (`02`–`04`) → views (`05`) → risk (`06`)
- [ ] The parallel Python path: `data_loader` → `validate` → `kpis` / `risk` → `charts` / CLI
- [ ] Which BI tool reads which view
- [ ] Why the Python layer duplicates the SQL layer (reconciliation, not redundancy)
- [ ] Where the Good/Bad rule lives in each layer, and why `test_sql.py` checks consistency

### Limitations you must volunteer before being asked

- [ ] SQL is never executed in CI — `sqlglot` static parsing only, no SQL Server available
- [ ] `.pbix`, `.twbx` and `.xlsx` are not in the repo; only DAX / calculated fields /
      build guides
- [ ] The DAX has never been parsed, evaluated or rendered
- [ ] 40.1% of rows have `last_payment_date < issue_date` → no vintage or time-to-default
      analysis is possible
- [ ] December MTD covers 12 days, so MoM understates growth
- [ ] Exact-figure tests skip in CI because the full dataset is gitignored
- [ ] The dashboard structure and SQL `01`–`05` came from a baseline implementation; the risk/validation
      layer is the extension
- [ ] Interest rate averages are unweighted by principal
- [ ] Relative MoM on rate metrics is questionable presentation
- [ ] No statistical significance testing on any segment finding — no confidence intervals,
      no hypothesis tests. Volume floors are a crude substitute
- [ ] The version numbers in `pyproject.toml` and `src/bank_loan_report/__init__.py` once
      disagreed (`1.0.0` vs `2.0.0`) and are now both `2.0.0`; the drift and its fix are
      recorded in `docs/AUDIT.md`. Re-read `README.md`'s structure tree before demoing and
      confirm it still lists every module and SQL script that exists

### Practice out loud

- [ ] The 60-second pitch, timed, three times without notes
- [ ] The 5-minute walkthrough with the repo open, pointing at files
- [ ] "Was this from a baseline implementation?" — answered honestly, in under 45 seconds, without
      defensiveness
- [ ] "How do you know the dashboard numbers are correct?" — the reconciliation argument
      plus its limits
- [ ] Explain one insight you find genuinely interesting (the verification-status selection
      effect is the best candidate) and why it changed how you read the data

---

## 13. Concepts this project does NOT cover

An honest inventory. Volunteering these is stronger than being caught by them, and each is a
concrete next step you can name if asked "what would you learn next?"

### No machine learning

There is no model, no train/test split, no cross-validation, no feature engineering pipeline,
no ROC/AUC, no calibration, no SHAP. Every default rate in this repo is a **historical
frequency**, not a **prediction**. The obvious extension — a logistic regression or gradient
boosted model predicting `is_charged_off` from grade, term, income, DTI and purpose — is a
different project, and doing it properly would need the vintage data this dataset does not
support. Do not let anyone (including yourself) describe this as a credit-risk *model*.

### No statistical inference

No confidence intervals, no hypothesis tests, no significance levels anywhere. When the
project says "60-month grade F defaults at 34.22%", it does not say whether that differs
significantly from grade E at 29.75% on 751 and 1,758 loans respectively. The volume floors
(20/50/100/250/300) are a crude proxy for "big enough to believe" — a real substitute would be
Wilson confidence intervals on each proportion, or a chi-squared test of independence.

### No incremental or streaming pipeline

Every run reads the entire CSV and recomputes everything from scratch. No watermarks, no
change data capture, no upserts, no `MERGE`, no partitioning, no late-arriving-data handling,
no slowly changing dimensions. `sql/01` drops and recreates the table on every run. That is
fine for a static 38,576-row extract and completely inappropriate for a daily-refreshed loan
book.

### No orchestration

No Airflow, no Dagster, no Prefect, no dbt, no cron. Nothing schedules anything; nothing
retries; nothing alerts. The "pipeline" is a human typing `python -m bank_loan_report report`.
The natural first step here would be dbt for the SQL transformation layer — the CTE-heavy
`sql/06` maps almost directly onto dbt models with tests.

### No live database in CI

No SQL Server service container, so no SQL is ever executed in automation. The upgrade is
concrete and well-trodden: a `services:` block in `ci.yml` running
`mcr.microsoft.com/mssql/server`, then executing `01`–`06` against the sample data and
asserting on the returned rows. That single change would convert every
`/* Expected: ... */` comment in `sql/06` into an enforced assertion.

### No cloud or modern warehouse

Everything is local: SQL Server on `localhost`, files on disk. No Snowflake, BigQuery,
Databricks, Redshift, S3, blob storage, IAM, or cost management. No columnar storage, no
clustering keys, no query-cost awareness. If asked what changes at 100× scale, the honest
answer is that the architecture changes shape rather than scaling — see the
`INTERVIEW_GUIDE.md` answer on that.

### No version-controlled BI artefacts

The `.pbix`, `.twbx` and `.xlsx` binaries are absent. There is no automated way to check
that a rebuilt dashboard matches `docs/VERIFICATION.md`; that reconciliation is manual.
Tools like Tabular Editor / `pbi-tools` can extract Power BI models to source-controllable
text — that is the real fix, and this project does not use it.

### No time-series or vintage analysis

Ruled out by the data, not by choice. With 40.1% of rows carrying a `last_payment_date`
before `issue_date`, no seasoning curve, no time-to-default distribution, no survival
analysis and no forecast is defensible. Twelve monthly points of a single year would not
support seasonality claims even if the dates were clean.

### No dimensional modelling

One flat fact table with 24 columns and no dimensions. No star schema, no surrogate keys, no
conformed dimensions, no bridge tables, no SCD Type 2. The only relationship in the entire
project is the Power BI `date_table` → fact link — which is, at least, a genuine
one-to-many dimension relationship you can talk about.

### No data governance or security depth

No row-level security, no column masking, no PII handling policy, no audit logging, no data
lineage tooling, no data catalogue, no retention policy. `config.py` keeps credentials out of
source control and `.env` is gitignored, which is table stakes rather than a governance
story.

### No unit economics

Net margin here is `total_payment - loan_amount`: undiscounted cash in minus cash out. There
is no cost of funds, no operating cost allocation, no expected credit loss provisioning, no
risk-adjusted return on capital, no IFRS 9 / CECL staging, no net present value. So "the book
is profitable" means "more cash came back than went out", which is a much weaker claim than
"this book earns its cost of capital". Say the weaker claim.

---

## Further reading inside this repo

| To understand | Read |
|---|---|
| The business requirements | `docs/problem_statement.md` |
| Every column in detail | `docs/data_dictionary.md` |
| Reference values for every number | `docs/VERIFICATION.md` |
| The data defects in full | `docs/DATA_QUALITY.md` |
| The risk findings written up | `docs/INSIGHTS.md` |
| The layer-by-layer design | `docs/ARCHITECTURE.md` |
| What came from the baseline implementation and what did not | `docs/ANALYTICS_WALKTHROUGH.md` |
| How to answer interview questions on this | `docs/INTERVIEW_GUIDE.md` |
| The SQL techniques, with expected outputs inline | `sql/06_risk_and_cohort_analysis.sql` |
| How to rebuild each dashboard | `powerbi/README.md`, `tableau/calculated_fields.md`, `excel/README.md` |
| Where the data comes from | `data/README.md` |
