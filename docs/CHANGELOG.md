# Changelog

What changed, and why. Grouped by release rather than by date.

---

## 2.0.0 — Portfolio hardening

The 1.0.0 release was solid: it implemented the baseline KPIs and
stopped there. This release adds the analytical, validation and documentation layers
that make the repository defensible in a technical interview, and fixes the defects
found while auditing it. The full audit is in [`AUDIT.md`](AUDIT.md).

### Added — analysis

- **`src/bank_loan_report/risk.py`** — the risk and profitability layer that the project
  previously lacked: `add_risk_flags` (charged-off / closed flags, DTI bands, income
  quintiles, loan-size bands), `portfolio_economics`, `headline_risk_metrics`,
  `segment_risk`, `risk_ranking`, `unprofitable_segments`, `pricing_power`,
  `concentration`, `term_grade_risk`, `monthly_risk_trend`.
  *Why:* the original project reported *what happened* and never *what it means*. Every
  finding in [`INSIGHTS.md`](INSIGHTS.md) comes from this module.
- **`src/bank_loan_report/risk_charts.py`** — four charts built to carry a specific
  finding each: default rate versus interest rate by grade, recovery rate by purpose
  against a 100% break-even line, default rate by borrower attribute, and the
  risk-versus-pricing scatter across sub-grades.
- **`sql/06_risk_and_cohort_analysis.sql`** (491 lines, 8 sections) — the same analysis
  in T-SQL, using `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `LAG`, running totals over
  an ordered frame, a moving average frame, `PARTITION BY`, six CTE-based queries and a
  `CROSS JOIN` against a benchmark CTE.
  *Why:* `sql/02`–`sql/05` contained no window functions, no CTEs and no joins, which is
  precisely what a SQL interview tests.

### Added — validation and testing

- **`src/bank_loan_report/validate.py`** — 13 executable checks at three severities.
  `FAIL` means a published KPI would be wrong and the command exits non-zero; `WARN`
  marks a known dataset defect; `INFO` records an observation.
  *Why:* `data_quality_report()` profiled the data but asserted nothing. Profiling that
  cannot fail is not validation.
- **`tests/test_risk.py`** — 34 tests: invariants (net margin reconciles, per-status rows
  sum to the total, bands cover every row, no input mutation) plus exact-figure
  regression tests behind a `requires_full` skip.
- **`tests/test_validate.py`** — 18 tests, of which eight deliberately corrupt a copy of
  the data and assert the corresponding check flips to failing.
  *Why:* a check that can never fail is decoration.
- **`tests/test_sql.py`** — static T-SQL validation with `sqlglot`: every script parses,
  business-rule literals are cased consistently, `SET DATEFORMAT dmy` precedes the
  `BULK INSERT`, period boundaries are derived from `MAX(issue_date)` rather than
  hard-coded, no destructive verb appears outside the load script, and `sql/06` really
  contains the techniques it claims.
  *Why:* no SQL Server is available in this environment, so the SQL layer was previously
  unverified in any form. This is not execution, and the limitation is stated in
  [`VERIFICATION.md`](VERIFICATION.md).

### Added — documentation

- [`AUDIT.md`](AUDIT.md) — the P0/P1/P2 audit, including the findings that were *not*
  fixed and why.
- [`INSIGHTS.md`](INSIGHTS.md) — the business findings, plus every KPI with what it is,
  how it is calculated, why it matters and which business question it answers.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Mermaid data-flow, module-dependency and CI
  diagrams; a justification for why each technology is present rather than a list; layer
  contracts; and the architectural limitations.
- [`DATA_QUALITY.md`](DATA_QUALITY.md) — the check inventory, the two known dataset
  defects with evidence and consequences, and the four silent-failure traps in this data.
  *Why:* `validate.py` and `risk.py` already pointed readers at this file, which did not
  exist.
- `INTERVIEW_GUIDE.md` and `LEARNING_GUIDE.md` — see below.
- This changelog.

### Fixed

- **The published figures were generated from the 600-row sample.** `charts` and
  `export` wrote to `reports/figures/` and `reports/tables/` regardless of `--sample`,
  so the sample smoke-test run overwrote the ten full-dataset figures and one commit
  published 600-row versions of them. Lint, the full test suite and CI all passed; the
  only symptom was the axis magnitudes, and the only control that caught it was opening
  the PNGs. `--sample` runs now default to `reports/sample/` (gitignored) and cannot
  touch the published figures; all ten figures were regenerated from the full dataset and
  re-inspected individually; `tests/test_cli.py` (10 tests) pins the routing, including a
  test that asserts a `--sample` run never even creates the published figures directory.
  *Why it matters:* the test suite verified that charts were *written*, never *what was
  in them* — binary artefacts sat outside the validation boundary. Recorded in full as
  `AUDIT.md` P1-9 rather than fixed quietly.
- **`--outdir` meant two different things.** `charts --outdir X` wrote `X/*.png` but
  `export --outdir X` wrote `X/tables/*.csv`. `export --outdir X` now writes `X/*.csv`
  directly; the default path (`reports/tables/`) is unchanged, so no documented command
  changes behaviour. `AUDIT.md` P1-10.
- **Figures were excluded from version control.** `.gitignore` contained a bare `*.png`,
  so a data-visualisation project displayed zero charts on GitHub. It now carries an
  explicit exception for `reports/figures/*.png` with a comment explaining the decision,
  and all ten figures are committed. Derived CSV tables remain ignored.
- **Unknown loan statuses were silently classified as bad.** `clean_loans` used
  "anything that is not good is bad". Correct for the three statuses present; wrong and
  silent the day a fourth appears. Classification is now positive against both lists,
  unknown statuses become `Unclassified`, and `check_known_loan_statuses` fails on them.
- **A risk chart crashed on the bundled sample.** The segment chart used a fixed
  250-loan volume floor; on the 600-row sample no segment qualified and `max()` was
  called on an empty sequence. The floor is now proportional to dataset size
  (`_volume_floor`: 0.65% of rows, minimum 5, which still yields 250 on the full data)
  and empty panels render an explanatory message instead of raising. This would have
  broken CI on the first command the README tells a reader to run.
- **The documented `issue_date` range was wrong.** `docs/data_dictionary.md`,
  `sql/01_schema_and_load.sql` and `powerbi/power_query_steps.md` said the data ran to
  2021-12-31. The actual maximum is **2021-12-12**. The MTD KPI depends on that date, so
  the error mattered. Corrected everywhere and now asserted by
  `check_dates_are_day_first` and `test_dates_are_day_first`.
- **`resolve_data_path()` was called twice per CLI invocation.** Removed.
- **A misleading metric name.** The charge-off cash shortfall was labelled in a way that
  implied a loss on the whole book; it is now "Net cash lost to charge-offs" and reported
  alongside the positive portfolio net margin so neither can be read out of context.
- **The constant-column check flagged derived helpers.** `issue_year` is legitimately
  constant in a single-year extract; derived columns are now excluded from that check.
- **An undeclared scipy dependency, caught by CI.** `pricing_power` used pandas'
  `corr(method="spearman")`, which imports scipy lazily — so the module imported fine in a
  sandbox that happened to have scipy and then failed at call time on the clean CI runner.
  Spearman's rho is Pearson's r on the ranks, so it is now computed directly with
  `rank().corr(...)`. The value is unchanged to seven decimal places (0.9585434), the
  dependency list stays at pandas and matplotlib, and
  `test_spearman_is_computed_without_scipy` blocks the scipy import to prove it.
- **`risk_ranking` warned on empty inputs.** It concatenated per-dimension frames without
  dropping empty ones, which raised a pandas `FutureWarning` about dtype inference. Empty
  frames are now filtered, and a fully-filtered result returns a correctly-shaped empty
  DataFrame rather than raising.
- **Two documentation-vs-code disagreements found while re-verifying the README.**
  `pyproject.toml` declared version `1.0.0` while `src/bank_loan_report/__init__.py`
  declared `2.0.0` (both now `2.0.0`), and `powerbi/README.md` claimed "all 30 measures"
  while `powerbi/measures.dax` defines 32 (both READMEs now say 32). Neither changed a
  reported number, but both are the kind of drift a reviewer checks first.

### Changed

- **`cli.py`** — added `validate` (non-zero exit on a blocking failure) and `insights`
  subcommands; `charts` gained `--risk-only`; `export` now writes the 12 risk tables
  alongside the 9 KPI tables (21 CSVs in total).
- **`Makefile`** — added `validate`, `insights` and `all` targets. `make all` runs
  `validate` first, so a blocking data-quality failure stops the run before anything is
  published.
- **`.github/workflows/ci.yml`** — installs `sqlglot`; runs
  `python -m bank_loan_report --sample validate` as a dedicated gate; the CLI smoke
  tests now cover `report`, `insights`, `charts`, `charts --risk-only`, `export` and
  `quality`.
- **`__init__.py`** — version `2.0.0`, a docstring describing the layers, and the new
  modules exported.
- **`requirements-dev.txt`** — added `sqlglot>=25.0`.
- **`README.md`** — rewritten in portfolio order: business problem, questions, findings,
  data, architecture, KPI definitions, figures, validation, setup, reproduction,
  limitations. The documentation was expanded to a full
  Acknowledgements section near the end. It is still stated plainly which parts were
  implemented in the core release and what was extended in the risk tier.

### Known and deliberately unfixed

Documented in [`AUDIT.md`](AUDIT.md) rather than silently left:

- `kpis.by_month` does not reindex against a calendar spine; every month is present in
  this dataset, and the Power BI layer already carries a proper date table.
- `mom_change` returns `0.0` when the prior period is zero, which conflates "no change"
  with "no comparable period". Cannot occur in this dataset.
- The notebook covers the KPI walkthrough only; the risk layer is exposed through the
  CLI, the committed figures and `INSIGHTS.md` instead of being implemented a fourth
  time.
- The SQL scripts are still not executed against a real SQL Server instance.
- The MIT LICENSE names a different person than the GitHub account hosting the
  repository. This needs a decision from the repository owner.

---

## 1.0.0 — Initial Platform Release

Production release of the bank loan analytics platform:
- Data loader and date normalization pipeline
- Core KPIs, Good/Bad loan categorization, and overview aggregations
- SQL Server schema scripts and automated test suite