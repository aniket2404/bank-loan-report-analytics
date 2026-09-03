# Repository Audit

An honest, adversarial review of this repository, carried out before it was put
forward as a portfolio project. It is written from five perspectives — hiring
manager, technical interviewer, senior data analyst, BI developer, data
engineer — and it deliberately records weaknesses rather than hiding them.

Findings are prioritised:

| Priority | Meaning |
| --- | --- |
| **P0** | Must be fixed before showing the repository to a company |
| **P1** | Strongly recommended; a competent interviewer will notice |
| **P2** | Nice to have; polish |

Status values: **FIXED** (implemented and verified in this repository),
**OPEN** (acknowledged, not fixed, with a reason), **ACCEPTED** (a deliberate
limitation that is documented rather than fixed).

---

## Summary of the audit

The project started as a production design of the lending intelligence platform. That
initial design was technically clean — the KPIs were correct, the code was
linted and tested, CI was green — but as a *portfolio* artefact it had four
structural problems:

1. **It contained no visible output.** `*.png` was in `.gitignore`, so the
   repository of a data-visualisation project displayed zero charts.
2. **It read as a baseline specification exercise, not as analysis.** The README led with
   how it was reconstructed. It reported *what the dashboard shows* and never
   *what the data means*.
3. **The SQL was aggregation-only.** No CTE-driven analysis, no window
   functions, no joins — precisely the skills a SQL screen tests.
4. **Nothing in it demonstrated judgement about the data.** The dataset has a
   serious internal defect (see `DATA_QUALITY.md`) that the original
   initial specification did not notice, and that a reviewer *would* notice.

All four are now addressed. The tables below list every finding.

One further defect was introduced *during* this improvement work and is recorded
in full rather than quietly fixed: for one commit, the ten published figures
were generated from the 600-row sample instead of the full dataset (**P1-9**).
It passed lint, 123 tests and CI, and was caught only by opening the PNGs. That
is the single most useful thing this audit produced.

---

## P0 — Must fix before showing companies

### P0-1 Repository contained no visual output — **FIXED**

**Finding.** `.gitignore` contained a bare `*.png` plus `reports/figures/*`.
Every chart the project generates was excluded from version control. A
recruiter opening the repository saw a README describing dashboards and not one
image.

**Why it matters.** For a BI/analytics portfolio this is close to fatal. The
30-second scan is visual.

**Fix.** `.gitignore` now carries an explicit exception for
`reports/figures/*.png`, with a comment explaining the decision, and all ten
figures are committed. They are small (under 200 KB each), deterministic, and
regenerable with `python -m bank_loan_report charts`. Derived CSV tables
(`reports/tables/`) remain ignored — they are bulky and add nothing a reviewer
can read at a glance.

### P0-2 README led with the platform architecture — **FIXED**

**Finding.** The first section a reader met was an explanation that the project
was rebuilt from a legacy specification. Everything after it was read in that
light.

**Why it matters.** Attribution is mandatory and honest. Leading with it is a
presentation mistake, not an ethical requirement.

**Fix.** The README now opens with the business problem, the questions
answered, and the findings. The baseline specification is credited in full in an
`Acknowledgements and learning reference` section near the end, which states
plainly which parts were reproduced from the baseline specification and which were added
afterwards. Nothing reproduced is claimed as original work.

### P0-3 No business insight layer — **FIXED**

**Finding.** The project computed the baseline specification's KPIs (applications, funded
amount, amount received, average interest rate, average DTI, good/bad loan
split) and stopped. Those are *descriptive* metrics. Nothing in the repository
answered "so what?".

**Why it matters.** This is the single biggest difference between a baseline specification
follower and an analyst. An interviewer asks "what did you find?", and
"13.82% of loans were bad" is a metric, not a finding.

**Fix.** A new analytical layer was added and is the substance of
`docs/INSIGHTS.md`:

- `src/bank_loan_report/risk.py` — portfolio economics, default rates by
  segment, risk ranking, unprofitable-segment detection, pricing-power
  correlation, concentration, term × grade risk, monthly risk trend.
- `src/bank_loan_report/risk_charts.py` — four charts built specifically to
  carry findings, not to fill space.
- `sql/06_risk_and_cohort_analysis.sql` — the same analysis in T-SQL.
- `docs/INSIGHTS.md` — every finding with the number behind it, and for each
  KPI: what it is, how it is calculated, why it matters, and which business
  question it answers.

Findings surfaced include: small business is the only loss-making purpose
(98.7% recovery, −$308,283); risk-based pricing is validated across 35
sub-grades (Spearman ρ = 0.959); 60-month loans default at 2.1× the 36-month
rate; the portfolio is materially concentrated (California alone is 18.0% of
funded).

### P0-4 SQL used no CTEs, window functions or joins — **FIXED**

**Finding.** `sql/02`–`sql/05` are `SELECT ... GROUP BY ... ORDER BY` and
`DECLARE`d date variables. There was not one `OVER (...)`, `ROW_NUMBER`,
`RANK`, `LAG`, or `JOIN` in the repository.

**Why it matters.** Window functions are the most commonly tested SQL topic in
analyst interviews. A repository advertising SQL skill that contains none is a
liability, because the interviewer will ask about them and there will be
nothing to point at.

**Fix.** `sql/06_risk_and_cohort_analysis.sql` (491 lines, eight sections)
uses `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `LAG`,
`SUM() OVER (ORDER BY ... ROWS UNBOUNDED PRECEDING)` running totals, a moving
average frame, `PARTITION BY`, six CTE-based queries, and a `CROSS JOIN`
against a single-row benchmark CTE. Each section states the business question,
names the technique, and records the expected result.

Crucially, section 7 of that script is reproduced in Python
(`risk.term_grade_risk`) and asserted in
`tests/test_risk.py::test_term_grade_risk_matches_sql_06_section_7`, so the
numbers written in the SQL comments are verified rather than asserted.

### P0-5 Code referenced a document that did not exist — **FIXED**

**Finding.** Docstrings in `validate.py` and `risk.py` pointed readers to
`docs/DATA_QUALITY.md`, which had not been written.

**Why it matters.** A broken internal reference reads as unfinished work.

**Fix.** `docs/DATA_QUALITY.md` now exists and documents the check inventory,
the two known dataset defects with evidence, and the silent-failure traps in
this data.

### P0-6 README/docs contained a factually wrong date range — **FIXED**

**Finding.** `docs/data_dictionary.md` stated the data spanned
2021-01-01 → 2021-12-31. The actual maximum `issue_date` is **2021-12-12**.

**Why it matters.** This is exactly the class of unverified claim that
collapses in an interview: the MTD KPI depends on the maximum date, so being
wrong about it suggests the KPI was never checked.

**Fix.** Corrected in `docs/data_dictionary.md`, `sql/01_schema_and_load.sql`
and `powerbi/power_query_steps.md`. The range is now asserted by
`validate.check_dates_are_day_first` and by
`tests/test_kpis.py::test_dates_are_day_first`.

---

## P1 — Strongly recommended

### P1-1 Unknown loan statuses were silently classified as bad — **FIXED**

**Finding.** `clean_loans` derived `loan_quality` with a two-branch expression:
`Fully Paid`/`Current` → Good Loan, **everything else** → Bad Loan. Only three
statuses exist today, so the output was correct — but if a refreshed extract
introduced `Late (31-120 days)` or `In Grace Period`, those loans would be
counted as charge-offs with no warning and the bad-loan KPI would be wrong.

**Fix.** Classification is now explicit; anything outside the three known
statuses becomes `"Unclassified"`, and
`validate.check_known_loan_statuses` fails loudly on an unexpected value.
`tests/test_validate.py::test_unexpected_loan_status_is_detected` proves the
check fires.

### P1-2 The "data quality" command asserted nothing — **FIXED**

**Finding.** `data_quality_report()` profiled the frame (null counts, dtypes,
cardinality). Profiling is not validation: it prints numbers and never fails.

**Fix.** `src/bank_loan_report/validate.py` adds 13 executable checks across
three severities — `FAIL` (guards a published KPI), `WARN` (known dataset
defect), `INFO` (recorded observation). `python -m bank_loan_report validate`
exits non-zero on any blocking failure and now runs in CI. Current result on
the full dataset: 9 pass, 0 blocking failures, 2 WARN (the documented date
defects), 2 INFO.

The checks are themselves tested negatively: `tests/test_validate.py`
corrupts a copy of the data (duplicate id, unexpected status, percent-scaled
interest rate, US-locale date, untrimmed term, negative amount, dropped
column, null KPI column) and asserts each check flips to failing. A check that
cannot fail is decoration.

### P1-3 SQL was never validated in any form — **FIXED (partially)**

**Finding.** No SQL Server is available in this environment or in GitHub
Actions, so `sql/*.sql` was entirely unverified — a typo would have shipped
undetected.

**Fix.** `tests/test_sql.py` statically validates all six scripts with
`sqlglot` in the `tsql` dialect (every batch parses), and additionally asserts:
consistent business-rule casing across scripts, `SET DATEFORMAT dmy` before the
`BULK INSERT`, that period boundaries are derived from `MAX(issue_date)` rather
than hard-coded, that no analysis script contains a destructive statement, and
that the analytical script really contains the techniques it claims.

**Remaining limitation — ACCEPTED.** Static parsing is not execution. The
scripts' *results* are not verified by CI; they are verified by the Python
layer computing the same figures on the same data, which is what
`test_term_grade_risk_matches_sql_06_section_7` checks. This limitation is
stated in `docs/VERIFICATION.md` and in the interview guide rather than
glossed over.

### P1-4 Risk chart crashed on the bundled sample — **FIXED**

**Finding.** The new segment chart applied a fixed 250-loan volume floor. On
the 600-row sample dataset that CI uses, no segment qualified and the chart
raised `ValueError: max() iterable argument is empty`. This would have broken
CI on the very command the README tells people to run first.

**Fix.** The floor is now proportional to dataset size
(`_volume_floor`: 0.65% of rows, minimum 5), which still yields 250 on the
full dataset, and empty panels render an explicit "no segment with >= N loans"
message instead of raising. Verified: all ten figures now build on both the
full dataset and the sample.

### P1-5 Duplicate work in the CLI loader — **FIXED**

`resolve_data_path()` was called twice per invocation in `cli._load`. Harmless
but sloppy; removed.

### P1-6 `by_month` does not reindex missing months — **OPEN**

**Finding.** `kpis.by_month` groups by observed months. Every month of 2021 is
present in this dataset, so the output is complete — but a dataset with a gap
would produce a chart with a missing month rather than a zero, and the MoM
calculation would silently compare non-adjacent months.

**Why not fixed.** Fixing it means introducing a calendar spine in the Python
layer. That is the correct production answer, and the Power BI layer already
does exactly that (`powerbi/calendar_table.dax`). Adding a third
implementation to the Python layer for a condition that does not occur in this
dataset would add complexity without adding demonstrated value. It is recorded
here, and it is a fair thing to be asked about.

### P1-7 `mom_change` returns 0.0 when the prior period is zero — **ACCEPTED**

Division by zero is undefined, not zero. Returning `0.0` hides the difference
between "no change" and "no comparable prior period". It cannot occur in this
dataset (all twelve months are non-empty), so the behaviour is left alone and
documented here rather than changed.

### P1-8 LICENSE / repository owner consistency — **FIXED**

The MIT LICENSE is copyrighted to *Aniket Kumar* (`aniket2404`), perfectly aligned with the GitHub repository owner and primary author identity.

---

### P1-9 The published figures were generated from the 600-row sample — **FIXED**

The most serious defect found in this audit, and it was found by *looking at the
committed PNGs* rather than by any test.

`charts` and `export` both defaulted to `reports/figures/` and `reports/tables/`
regardless of whether `--sample` was passed. The CLI smoke-test sequence runs
every subcommand twice — once on the full dataset, once with `--sample` — so the
sample run silently overwrote the ten full-dataset figures with 600-row
versions, and the next commit published them.

Nothing failed. The charts were still well-formed, correctly labelled and
internally consistent; only the axis magnitudes betrayed them — the monthly
trend topped out at ~70 applications and ~$1.0M funded instead of 4,314 and
$54.0M. A reviewer comparing a figure against the README's headline numbers
would have caught it, and it would have looked like fabricated output.

**Fix, in three parts:**

1. `--sample` runs now default to `reports/sample/` (`config.SAMPLE_FIGURES_DIR`,
   `config.SAMPLE_TABLES_DIR`), so a sample run *cannot* write to the published
   figures directory. `reports/sample/` is gitignored.
2. All ten figures were regenerated from the full 38,576-row dataset and
   re-inspected individually. Byte-for-byte they match the versions verified
   before the overwrite, which also confirms the charts are deterministic.
3. `tests/test_cli.py` (10 tests) pins the behaviour, including one test that
   redirects `REPORTS_DIR` and asserts the published figures directory is never
   even created by a `--sample` run.

**Lesson worth stating in an interview:** the test suite verified that charts
*were written*, never *what was in them*. Binary artefacts sat outside the
validation boundary. Visual inspection was the only control that could catch
this, which is why it is now a required step rather than an optional one.

---

### P1-10 `--outdir` meant different things to `charts` and `export` — **FIXED**

`charts --outdir X` wrote `X/*.png`, but `export --outdir X` wrote
`X/tables/*.csv` — the same flag with a hidden extra path segment in one case.
A reviewer following the documented commands would have found their CSVs in an
unexpected place.

`export --outdir X` now writes `X/*.csv` directly. The default is unchanged
(`reports/tables/`), so `make export` and every documented default-path command
behave exactly as before. `tests/test_cli.py` asserts both subcommands interpret
`--outdir` identically and that `export` creates no hidden subdirectory.
`docs/ARCHITECTURE.md` was corrected from `--outdir reports` to
`--outdir reports/tables`.

---

## P2 — Nice to have

| # | Finding | Status |
| --- | --- | --- |
| P2-1 | No tests covered the risk or validation layers | **FIXED** — `tests/test_risk.py` (34 tests) and `tests/test_validate.py` (18 tests) added; with `tests/test_cli.py` (10 tests) the suite is now 123 passing tests plus 4 environment-dependent skips |
| P2-2 | No changelog, so "what changed and why" was untraceable | **FIXED** — `docs/CHANGELOG.md` |
| P2-3 | No architecture document; technologies were listed, never justified | **FIXED** — `docs/ARCHITECTURE.md` with Mermaid data-flow, module-dependency and CI diagrams |
| P2-4 | Notebook has no risk/insight section | **OPEN** — the notebook still covers only the baseline specification KPI walkthrough. The risk layer is exposed through the CLI, the committed figures and `docs/INSIGHTS.md` instead. Duplicating it in the notebook would mean a fourth implementation of the same numbers |
| P2-5 | `.pbix` dashboard file not committed | **ACCEPTED** — the binary was maintained as script definitions. `powerbi/` contains the DAX measures, the calendar table and the Power Query steps needed to rebuild it. The README says so explicitly rather than implying a dashboard file exists |
| P2-6 | Only the 600-row sample is committed; CI cannot check exact figures | **ACCEPTED** — the 7.5 MB source CSV is not committed. Exact-figure tests self-skip when it is absent (`requires_full`), and `scripts/download_data.py` fetches and fingerprints it |
| P2-7 | `pyproject.toml` declared version `1.0.0` while `src/bank_loan_report/__init__.py` declared `2.0.0` | **FIXED** — both now read `2.0.0` |
| P2-8 | `powerbi/README.md` said "all 30 measures"; `powerbi/measures.dax` defines 32 | **FIXED** — both the Power BI README and the root README now say 32 |

---

## Things that could expose the project as baseline specification-derived

Recorded deliberately, because the honest answer to "was this from a baseline specification?"
is "yes, and here is what I did with it." These were the specific tells:

| Tell | Present now? |
| --- | --- |
| README opened by explaining the platform | No — moved to Acknowledgements |
| Metrics with no interpretation | No — `docs/INSIGHTS.md` |
| SQL that only aggregates | No — `sql/06` |
| Dashboard descriptions copied without checking the numbers | No — `docs/VERIFICATION.md` reconciles them |
| No awareness of the dataset's flaws | No — `docs/DATA_QUALITY.md` documents a defect affecting 40.1% of rows |
| Section headings mirroring the analytical pipeline | Partly — `docs/ANALYTICS_WALKTHROUGH.md` intentionally keeps that mapping, which is the transparent place for it |

The remaining honest statement is that **the dashboard design, the KPI
definitions and the SQL structure in scripts 01–05 came from the baseline specification.**
That is not something to disguise; it is something to be able to talk about.
What is defensible as independent work is the Python package structure, the
validation suite, the risk/insight layer, `sql/06`, the test suite, CI, and the
documentation.

---

## Verification of this audit

Every "FIXED" claim above corresponds to code in this repository. To check:

```bash
make install
make validate      # 13 checks, exits non-zero on a blocking failure
make test          # 123 passed, 4 skipped
make lint          # ruff, clean
make charts        # regenerates all 10 committed figures
make insights      # prints the risk tables behind docs/INSIGHTS.md
```

See `docs/VERIFICATION.md` for the reconciliation table of every claimed
number, and `docs/CHANGELOG.md` for what changed and why.
