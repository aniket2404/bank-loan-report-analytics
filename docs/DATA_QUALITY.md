# Data Quality

## Purpose

This dataset has real defects. They are documented here rather than silently patched.

Two of them are serious enough to remove a whole class of analysis from the table. The
temptation in a portfolio project is to drop the offending rows, recompute the dates, or
simply not mention it and publish a "vintage analysis" that looks impressive and means
nothing. This project takes the other route: the defects are detected by executable
checks, reported every time the pipeline runs, described below with their evidence and
their consequences, and used to justify what was deliberately *not* built.

The distinction the validation suite draws is the one that matters:

- **`FAIL`** — the check guards a published KPI. If it fails, the numbers are wrong and
  the pipeline exits non-zero. All nine `FAIL` checks currently pass.
- **`WARN`** — a known defect in the source data that limits what can be analysed but
  does not invalidate the volume and amount KPIs, because those KPIs do not read the
  affected columns. Two `WARN` checks currently fire, and they are expected to.
- **`INFO`** — a profiling observation, recorded so a reviewer can see it was considered
  rather than missed.

Every figure on this page was machine-computed from the full 38,576-row dataset.

---

## The check suite

All thirteen checks in `src/bank_loan_report/validate.py`, in the order they run.

| Check | Severity | What it guards | Current result on the full dataset |
|---|---|---|---|
| `schema: all expected columns present` | FAIL | Every downstream calculation assumes the 24 source columns exist. A missing column would otherwise surface as a `KeyError` deep in an aggregation, or worse, as a silently dropped measure. | **PASS** — all 24 source columns present |
| `grain: one row per loan id` | FAIL | The grain. Duplicate ids would double-count funded and received amounts while leaving every average looking plausible. | **PASS** — 38,576 rows, 38,576 distinct ids |
| `completeness: no nulls in KPI-driving columns` | FAIL | `id`, `loan_amount`, `total_payment`, `int_rate`, `dti`, `issue_date`, `loan_status`, `term`. A null here quietly shrinks a `mean()` denominator or drops a loan from a month. | **PASS** — all KPI columns complete |
| `business rule: every loan_status is classified` | FAIL | The Good/Bad rule only covers the statuses it knows about. A new status must be classified deliberately, not fall into whichever bucket the code defaults to. | **PASS** — statuses present: `Charged Off`, `Current`, `Fully Paid` |
| `units: int_rate and dti stored as fractions` | FAIL | The single most damaging silent error available in this dataset: a source file that switches to whole percentages would make every rate KPI 100 times too high without anything crashing. | **PASS** — `int_rate` max 0.2459, `dti` max 0.2999 |
| `dates: issue_date parsed day-first` | FAIL | A US-locale month-first parse reassigns loans to the wrong month, corrupting every MTD, PMTD and MoM figure while leaving the totals untouched. Detected by `issue_date` leaking out of a single calendar year. | **PASS** — `issue_date` spans 2021-01-01 to 2021-12-12 |
| `cleaning: term values trimmed` | FAIL | The source `term` values carry a leading space. Untrimmed, `" 36 months"` and `"36 months"` become two categories and the donut chart splits into four slices. | **PASS** — terms: `36 months`, `60 months` |
| `ranges: monetary columns are non-negative` | FAIL | `loan_amount`, `total_payment`, `installment`, `annual_income`. A negative amount from a bad import would net off against real loans inside a `SUM`. | **PASS** — no negative amounts |
| `plausibility: charged-off recovery below 100%` | FAIL | A sanity check on the load: charged-off loans should recover something but not the full principal. Recovery at or above 100% would mean the status column and the payment column disagree. | **PASS** — charged-off recovery 56.90% of principal |
| `timeline: last_payment_date >= issue_date` | WARN | Documents that the source date columns are not internally consistent. Nothing downstream is invalidated because no KPI reads `last_payment_date`, but it rules out every duration-based measure. | **WARN** — 15,453 rows (40.1%) have a last payment before the loan was issued |
| `timeline: repayment duration matches term` | WARN | Documents that the observed repayment window is incompatible with the contractual term, which is the second half of the same date defect. | **WARN** — 100.0% of Fully Paid loans close within a year, median 3 days, despite 36- and 60-month terms |
| `profiling: constant columns` | INFO | Source columns with one distinct value carry no analytical information and should not be offered as a slicer. Derived helpers are excluded, since `issue_year` is legitimately constant for a single-year extract. | **INFO** — constant: `application_type` |
| `profiling: emp_title completeness` | INFO | Records that the nulls in this free-text field were seen and consciously left alone rather than imputed. | **INFO** — 1,438 nulls (3.7%); free-text field, feeds no KPI, left as-is |

Summary: 9 checks report **PASS**, 2 report **WARN** (the documented dataset defects),
2 report **INFO**. **0 blocking failures**, so `python -m bank_loan_report validate`
exits 0.

`tests/test_validate.py` asserts both halves of this table. It requires that no
`FAIL`-severity check fails, that exactly two `WARN` checks fire on the full dataset — a
third would be news, and a disappearing one would mean the check stopped working — and,
through eight negative tests that deliberately corrupt a copy of the data, that each
check is actually capable of failing.

---

## Known defects

### Defect 1 — `last_payment_date` precedes `issue_date` for 40.1% of rows

**Evidence.** 15,453 of 38,576 rows (40.1%) have `last_payment_date` earlier than
`issue_date`. The signed gap from issue to last payment runs from **-336 days** to
**+338 days**, with a median of **3 days**. The four date columns individually look
reasonable — `issue_date` spans 2021-01-01 to 2021-12-12, `last_payment_date`
2021-01-08 to 2021-12-15, `next_payment_date` 2021-02-08 to 2022-01-15, and
`last_credit_pull_date` 2021-01-08 to 2022-01-20 — so nothing is out of range. The
defect is only visible in the *relationship* between the columns, which is exactly why a
per-column null-and-range profile would have missed it.

**Likely cause.** This is a teaching extract. The dataset was assembled so that
`issue_date` alone is coherent — it is the column every dashboard requirement is built
on, it lands cleanly inside one calendar year, and it produces a well-behaved monthly
series. The other three date columns appear to have been generated or shuffled
independently of it, and were never constrained to be consistent with the origination
date. A gap distribution that is roughly symmetric around zero and confined to about a
year in each direction is what independently drawn dates within the same period look
like; it is not what a real loan book looks like, where the gap is non-negative by
construction.

**Analytical consequence.** No duration-based analysis is possible from this data:

- **No vintage analysis.** "Of the loans issued in March, how many had defaulted by
  month 6" cannot be answered, because for 40.1% of loans the observation date precedes
  the origination date.
- **No seasoning curves.** There is no reliable months-on-book measure to plot against.
- **No time-to-default.** The interval between origination and the final payment on a
  charged-off loan is not trustworthy at the row level.
- **No cohort-performance comparison.** Cohorts can be *formed* by issue month, but they
  cannot be compared *at equal age*, which is the only comparison that makes a cohort
  view meaningful.

What survives is everything that reads `issue_date` and the amount columns only. The
monthly trend is therefore valid strictly as an **origination-volume series**: how much
was lent, and how many loans were written, in each month of 2021. The default rate shown
per month in `risk.monthly_risk_trend` and in section 4 of
`sql/06_risk_and_cohort_analysis.sql` is the **final observed status of each month's
cohort**, not a time-to-default measure — the cohorts differ in age and that difference
cannot be corrected for.

**What was deliberately not done.**

- The offending rows were not dropped. Removing 40.1% of the book would corrupt every
  headline KPI, including all the ones that are demonstrably correct.
- The dates were not "repaired" by swapping, clipping or recomputing them. Any such fix
  would be fabricated data wearing the appearance of a fix.
- No vintage, seasoning, time-to-default or survival analysis was attempted anywhere in
  the repository, in SQL or in Python.
- The check was not downgraded to silence. It runs on every invocation and reports the
  exact row count and share, and the caveat is repeated at the point of use: in the
  docstring of `risk.monthly_risk_trend` and in the section-4 header comment of
  `sql/06_risk_and_cohort_analysis.sql`.

### Defect 2 — 100% of Fully Paid 36-month loans appear to close within 365 days

**Evidence.** There are **25,214** Fully Paid 36-month loans in the dataset. **All
25,214 (100%)** have fewer than 365 days between `issue_date` and `last_payment_date`.
Across all 32,145 Fully Paid loans the same check reports 100.0% closing within a year,
with a **median issue-to-last-payment gap of 3 days**. A 36-month amortising loan cannot
be retired in three days at any realistic scale, and it certainly cannot happen for
every single loan in a 25,214-row population.

**Likely cause.** The same one as defect 1, seen from the other direction. If
`last_payment_date` was generated independently of `issue_date` within the same
twelve-month window, then the gap between them is bounded by the length of that window —
about a year — regardless of the contractual term. That is precisely what is observed:
gaps ranging from -336 to +338 days and centred near zero. The `term` column is
internally consistent and analytically useful (36 months on 28,237 loans, 60 months on
10,339, with clearly different risk profiles), but it bears no relationship to the
observed date interval.

**Analytical consequence.** Beyond the consequences already listed for defect 1, this
specifically forecloses:

- Any comparison of actual versus contractual repayment duration.
- Any prepayment or early-settlement analysis, which would otherwise be a natural
  question given a `term` column and a `last_payment_date`.
- Any use of `next_payment_date` to infer whether a loan is still amortising; the open
  book is identified from `loan_status = 'Current'` (1,098 loans, 2.85% of the book)
  instead.
- Any interpretation of `installment` against elapsed time. `installment` is used only as
  a descriptive field, never to reconstruct a payment schedule.

**What was deliberately not done.**

- No implied duration, prepayment flag or early-settlement metric was derived.
- `term` was not cross-validated against the dates, and no rows were reclassified on the
  strength of the mismatch.
- Realised credit risk is measured on the **closed-loan** denominator — `Fully Paid` plus
  `Charged Off` — rather than on any time-based maturity criterion. That choice moves the
  portfolio default rate from 13.8247% on all loans to 14.2297% on closed loans only, and
  it is stated in `risk.term_grade_risk`, in section 7 of
  `sql/06_risk_and_cohort_analysis.sql`, and asserted by
  `tests/test_risk.py::test_headline_default_rates`.

---

## Lesser observations

None of these invalidates a number. Each shapes what the analysis offers.

**`application_type` is constant.** Every one of the 38,576 rows is `INDIVIDUAL`. The
column carries no information, so it is not offered as a slicer, not used as a segment,
and reported by the `profiling: constant columns` check so that its absence from the
analysis is visibly a decision rather than an omission.

**`member_id` is redundant with `id`.** Both have 38,576 distinct values across 38,576
rows, so `member_id` identifies loans one-for-one and cannot be used to identify
*borrowers*. Any per-borrower analysis — repeat borrowing, exposure per customer, whether
a borrower holds several loans — is therefore impossible, and none is attempted. `id` is
the primary key in `sql/01_schema_and_load.sql` and the grain assertion in the validation
suite is written against it.

**`emp_title` nulls and cardinality.** 1,438 nulls (3.7%) and 28,522 distinct values
across 38,576 rows. It is unnormalised free text at near-unique cardinality, which makes
it useless as a grouping dimension and pointless to impute. It feeds no KPI and is left
exactly as it arrives. The `profiling: emp_title completeness` check records this at
`INFO` severity, and the Power Query column-profiling step in
`powerbi/power_query_steps.md` documents the same finding with the same "leave as-is"
action, so the two layers agree.

**5,860 rows where `total_payment` is less than `loan_amount`.** These are loans where
the bank received back less cash than it lent. Given 5,333 `Charged Off` loans, the
majority of these rows are explained by charge-offs — charged-off loans recover 56.90% of
principal on average — but the two counts do not coincide, so some non-charged-off loans
are also cash-negative. This is plausible rather than defective: a `Current` loan early
in its life has legitimately repaid less than its principal. It does mean that
`net_margin` is negative at the row level for a meaningful minority of the book, which is
why `risk.py` reports recovery rate against a break-even reference of 100% instead of
reporting margin alone, and why `risk_charts.recovery_by_purpose` draws that reference
line explicitly. On aggregate the book is positive: $473,070,933 received against
$435,757,075 funded, a net margin of $37,313,858 and a recovery rate of 108.56%.

**`dti` is capped near 0.30, so the top DTI band is thin.** The maximum `dti` in the
dataset is 0.2999 — 29.99% — which strongly suggests an underwriting cut-off at 30% (or a
filter applied when the extract was built). The consequence is that the `25%+` band in
`risk_by_dti_band` is not an open-ended tail but a narrow slice from 25% to 30%, holding
only **646 loans (1.67%)** with an average DTI of 27.22%. The other four bands run
monotonically from 12.00% default (`0-10%`) up to 15.93% (`20-25%`); the `25%+` band then
breaks the pattern at 12.23%. That reversal should not be read as "more indebted
borrowers default less". It is a thin, truncated, self-selected bucket: the 646 borrowers
who cleared underwriting *despite* a high DTI, priced at an average interest rate of
9.79% — the lowest of any band. The other four bands hold between 6,623 and 12,803 loans
each and are read normally. Band boundaries are set in `risk.add_risk_flags` and
every band is asserted to cover every row with no NaN.

---

## Data traps that silently produce wrong numbers

These are not defects in the data. They are properties of the data that produce wrong
answers without producing an error, which makes them more dangerous than the defects
above. Each is handled explicitly in every layer.

**1. Dates are `DD-MM-YYYY`.** `11-02-2021` means 11 February 2021, not 2 November 2021.
Any tool defaulting to a US locale mis-parses every date whose day-of-month is 12 or
lower, reassigns those loans to the wrong month, and breaks every MTD, PMTD and MoM
figure — while the grand totals stay correct, so the dashboard looks fine.

| Layer | How it is handled |
|---|---|
| Python | `config.SOURCE_DATE_FORMAT = "%d-%m-%Y"`, applied by `clean_loans` to all four date columns; never `dayfirst` inference |
| SQL Server | `SET DATEFORMAT dmy` before the `BULK INSERT` in `sql/01_schema_and_load.sql`, and again in `sql/06` |
| Power BI | Power Query *Data Type → Using Locale → Date → English (United Kingdom)*, or `"en-GB"` in the `Table.TransformColumnTypes` call in the M script |
| Excel | Get Data → Transform, set the four `*_date` columns to Date using locale English (United Kingdom) |
| Tableau | `DATEPARSE("dd-MM-yyyy", [Issue Date])` on the CSV connection |

Guarded by `validate.check_dates_are_day_first`, which fails if `issue_date` spans more
than one year; by `tests/test_kpis.py::test_dates_are_day_first`; by
`tests/test_validate.py::test_us_locale_date_misparse_is_detected`, which proves the
check can fail; and by `tests/test_sql.py::test_bulk_insert_sets_dateformat`, which
asserts the `SET DATEFORMAT dmy` directive actually precedes the load statement. The
Power BI build guide adds a manual check: after loading, `MAX(issue_date)` must read
12/12/2021, and if the max date lands in a different month the parsing step failed.

**2. `int_rate` and `dti` are stored as decimal fractions.** `0.1527` is 15.27%. They
must be multiplied by 100 **exactly once**, at presentation time. Multiply twice — or
multiply once and then apply a percentage number format — and the value is 100 times too
large. Multiply zero times and it is 100 times too small. `data_loader.clean_loans`
deliberately leaves both columns unscaled; `kpis.average_interest_rate`,
`kpis.average_dti`, `kpis.loan_status_grid` and `risk.segment_risk` each apply the single
`* 100`; the SQL scripts write `AVG(int_rate) * 100`; the DAX measures write
`AVERAGE(bank_loan_data[int_rate]) * 100`; Tableau writes `AVG([Int Rate]) * 100`. Excel
is the exception and the reason the rule is spelled out in `excel/README.md`: the pivot
value fields are formatted as Percentage with 2 decimals and are **not** multiplied,
because the percentage format performs the scaling. Guarded by
`validate.check_rates_are_fractions` (fails if either column exceeds 1.5),
`tests/test_kpis.py::test_rates_are_percentages`,
`tests/test_risk.py::test_segment_risk_interest_rate_is_a_percentage`, and
`tests/test_validate.py::test_percent_scaled_rate_is_detected`.

**3. The `term` column has a leading space.** Source values are `" 36 months"` and
`" 60 months"`. Untrimmed, a `GROUP BY term` yields duplicate categories the moment any
other layer trims — the donut chart grows extra slices, a join on term silently misses,
and a filter typed by hand matches nothing. `clean_loans` strips all text columns, so
`term` arrives as `36 months` / `60 months`; the SQL layer uses
`LTRIM(RTRIM(term))` and exposes `term_clean` in `dbo.vw_bank_loan_enriched`; Power Query
applies a Trim step; Tableau uses `TRIM([Term])`. Guarded by
`validate.check_term_trimmed`, `tests/test_kpis.py::test_term_is_trimmed`, and
`tests/test_validate.py::test_untrimmed_term_is_detected`.

**4. Only three `loan_status` values exist, so a new one must be classified explicitly.**
The dataset contains `Fully Paid` (32,145), `Charged Off` (5,333) and `Current` (1,098).
The Good/Bad rule is `Good = Fully Paid, Current` and `Bad = Charged Off`. The trap is the
implementation shortcut of writing "anything that is not good is bad": with three known
statuses it produces the right answer, and the day a fourth status such as `Default` or
`Late` appears it silently inflates the Bad Loan KPI with loans nobody classified.
`data_loader.clean_loans` therefore classifies positively against both lists and assigns
`Unclassified` to anything else, so an unknown status becomes visible instead of being
absorbed. `validate.check_known_loan_statuses` is a `FAIL`-severity check that fires on
any status outside `config.GOOD_LOAN_STATUSES | config.BAD_LOAN_STATUSES`, and
`tests/test_validate.py::test_unexpected_loan_status_is_detected` proves it. A related
trap sits in SQL: string comparison in SQL Server is case-insensitive by default, so a
mis-cased literal like `'Charged off'` would not error — it would just return a wrong
number. `tests/test_sql.py::test_business_rules_are_spelled_consistently` scans every
`.sql` file for exactly that.

---

## How to re-run the checks

```bash
python -m bank_loan_report validate
```

or, equivalently:

```bash
make validate
```

Against the bundled 600-row sample, which is what CI does:

```bash
python -m bank_loan_report --sample validate
```

Against any other file:

```bash
python -m bank_loan_report --data path/to/loans.csv validate
```

The command prints one line per check with its status and detail, then a summary line
counting checks passed, blocking failures and known data defects. It **exits non-zero if
any `FAIL`-severity check fails**, and zero when only `WARN` and `INFO` results are
present — which is the current state of this dataset. That exit code is what makes it
usable as a gate; the CI workflow runs it as a dedicated step for exactly that reason.

Two related commands:

```bash
python -m bank_loan_report quality   # per-column dtype, null count, null share, distinct count
pytest tests/test_validate.py -v     # the tests that verify the suite itself
```

The SQL layer carries a parallel set of assertions in section 8 of
`sql/06_risk_and_cohort_analysis.sql`, structured as a `UNION ALL` over independent
scalar checks so the output can be read in one glance. It is expected to return 7 PASS
and 2 WARN, the two WARNs being the same timeline defects documented above.

---

## What a production version would add

Everything in this repository validates a static extract. A pipeline that ran on a
schedule against a live source would need more:

- **Freshness SLAs.** An assertion that the newest `issue_date` is within an expected
  window of the run time, alerting when a feed stops arriving. Nothing here would notice
  a source that quietly froze — the checks would keep passing on yesterday's data.
- **Referential integrity.** With more than one table there would be foreign-key
  constraints and orphan-detection checks. This dataset has a single file and a
  `member_id` that is one-to-one with `id`, so there is no relationship to enforce and no
  join to protect.
- **Row-count and metric drift alerting.** Statistical process control on volumes and on
  the KPIs themselves: alert when the row count, funded amount, default rate or average
  interest rate moves beyond an expected band relative to recent history, rather than
  only on absolute-threshold breaches. The current suite would accept a 50% drop in
  volume without comment as long as every row in the smaller file was well-formed.
- **Schema contracts.** A versioned, machine-readable schema — column names, types,
  nullability, allowed categorical values, units — enforced at the ingestion boundary and
  versioned alongside the code, so a new `loan_status` value or a switch from fractions to
  percentages is rejected at the door rather than detected downstream.
  `data_loader.EXPECTED_COLUMNS` plus the `FAIL` checks are a hand-rolled subset of this.
- **Quarantine tables.** Rows failing a row-level rule routed to a quarantine table with
  the rule that rejected them, so the good rows load and the bad rows are inspectable and
  replayable. This project is all-or-nothing: `load_loans` raises on a missing column, and
  a defective row either passes or turns into a `WARN` counted in aggregate.
- **Lineage and check history.** Persisting each run's check results so trends are
  visible — a `WARN` that has been firing for months is a different situation from one
  that appeared this morning. Today the results are printed and then discarded.
