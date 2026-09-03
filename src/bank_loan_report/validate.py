"""Data validation suite for the Bank Loan Report project.

Every dashboard number in this project rests on assumptions about the source
data. This module states those assumptions as executable checks so that a
refreshed or replaced dataset either passes them or fails loudly.

Three severities are used:

``FAIL``
    The check guards a KPI. If it fails, published numbers are wrong.
``WARN``
    A known defect in the source dataset that limits what can be analysed but
    does not invalidate the volume/amount KPIs. These are documented in
    ``docs/DATA_QUALITY.md`` rather than silently patched.
``INFO``
    A profiling observation, recorded so reviewers can see it was considered.

Run it with::

    python -m bank_loan_report validate
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from . import config

Severity = str  # "FAIL" | "WARN" | "INFO"


@dataclass
class CheckResult:
    """Outcome of a single validation check."""

    name: str
    severity: Severity
    passed: bool
    detail: str

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return self.severity


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #
def check_no_missing_columns(df: pd.DataFrame) -> CheckResult:
    from .data_loader import EXPECTED_COLUMNS

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    return CheckResult(
        "schema: all expected columns present",
        "FAIL",
        not missing,
        "all 24 source columns present" if not missing else f"missing: {missing}",
    )


def check_unique_ids(df: pd.DataFrame) -> CheckResult:
    dupes = int(df["id"].duplicated().sum())
    return CheckResult(
        "grain: one row per loan id",
        "FAIL",
        dupes == 0,
        f"{dupes:,} duplicate ids"
        if dupes
        else f"{len(df):,} rows, {df['id'].nunique():,} distinct ids",
    )


def check_kpi_columns_not_null(df: pd.DataFrame) -> CheckResult:
    kpi_cols = [
        "id",
        "loan_amount",
        "total_payment",
        "int_rate",
        "dti",
        "issue_date",
        "loan_status",
        "term",
    ]
    nulls = {c: int(df[c].isna().sum()) for c in kpi_cols if c in df.columns}
    offenders = {c: n for c, n in nulls.items() if n}
    return CheckResult(
        "completeness: no nulls in KPI-driving columns",
        "FAIL",
        not offenders,
        "all KPI columns complete" if not offenders else f"nulls found: {offenders}",
    )


def check_known_loan_statuses(df: pd.DataFrame) -> CheckResult:
    """The Good/Bad rule only covers the statuses it knows about.

    If a new status appears, it must be classified deliberately rather than
    falling into whichever bucket the code defaults to.
    """
    known = set(config.GOOD_LOAN_STATUSES) | set(config.BAD_LOAN_STATUSES)
    found = set(df["loan_status"].dropna().unique())
    unknown = found - known
    return CheckResult(
        "business rule: every loan_status is classified",
        "FAIL",
        not unknown,
        f"statuses: {sorted(found)}"
        if not unknown
        else f"UNCLASSIFIED statuses present: {sorted(unknown)}",
    )


def check_rates_are_fractions(df: pd.DataFrame) -> CheckResult:
    """``int_rate`` and ``dti`` must be decimal fractions, not percentages.

    The single most damaging silent error in this project would be a source file
    that switches to whole percentages: every rate KPI would come out 100x too
    high without anything crashing.
    """
    problems = []
    for col in ("int_rate", "dti"):
        if col in df.columns and df[col].max() > 1.5:
            problems.append(f"{col} max={df[col].max():.4f} (expected <= ~1.0)")
    return CheckResult(
        "units: int_rate and dti stored as fractions",
        "FAIL",
        not problems,
        f"int_rate max {df['int_rate'].max():.4f}, dti max {df['dti'].max():.4f}"
        if not problems
        else "; ".join(problems),
    )


def check_dates_are_day_first(df: pd.DataFrame) -> CheckResult:
    """Guards against a US-locale (MM-DD-YYYY) mis-parse of the source dates.

    The source stores ``DD-MM-YYYY``. A month-first parse silently reassigns
    loans to the wrong month, which corrupts every MTD, PMTD and MoM figure
    while leaving the totals untouched - the worst kind of bug.
    """
    issue = df["issue_date"]
    single_year = issue.dt.year.nunique() == 1
    return CheckResult(
        "dates: issue_date parsed day-first",
        "FAIL",
        single_year,
        f"issue_date spans {issue.min().date()} to {issue.max().date()}"
        if single_year
        else f"issue_date spans {issue.dt.year.nunique()} years - likely a month/day swap",
    )


def check_term_trimmed(df: pd.DataFrame) -> CheckResult:
    raw = set(df["term"].dropna().unique())
    untrimmed = {t for t in raw if t != t.strip()}
    return CheckResult(
        "cleaning: term values trimmed",
        "FAIL",
        not untrimmed,
        f"terms: {sorted(raw)}" if not untrimmed else f"untrimmed values: {untrimmed}",
    )


def check_non_negative_amounts(df: pd.DataFrame) -> CheckResult:
    problems = [
        f"{col} min={df[col].min():,.2f}"
        for col in ("loan_amount", "total_payment", "installment", "annual_income")
        if col in df.columns and df[col].min() < 0
    ]
    return CheckResult(
        "ranges: monetary columns are non-negative",
        "FAIL",
        not problems,
        "no negative amounts" if not problems else "; ".join(problems),
    )


def check_charged_off_partial_recovery(df: pd.DataFrame) -> CheckResult:
    """Charged-off loans should recover something but not the full principal."""
    co = df[df["loan_status"].isin(list(config.BAD_LOAN_STATUSES))]
    if co.empty:
        return CheckResult(
            "plausibility: charged-off recovery below 100%", "FAIL", True, "no charged-off loans"
        )
    recovery = co["total_payment"].sum() / co["loan_amount"].sum() * 100
    ok = 0 < recovery < 100
    return CheckResult(
        "plausibility: charged-off recovery below 100%",
        "FAIL",
        ok,
        f"charged-off recovery {recovery:.2f}% of principal",
    )


def check_payment_after_issue(df: pd.DataFrame) -> CheckResult:
    """KNOWN DEFECT in the source dataset.

    ``last_payment_date`` precedes ``issue_date`` for a large share of rows, so
    the date columns other than ``issue_date`` are not internally consistent.
    Reported as WARN: the volume and amount KPIs do not use these columns, but
    no vintage, seasoning or time-to-default analysis is possible.
    """
    if "last_payment_date" not in df.columns:
        return CheckResult("timeline: last_payment_date >= issue_date", "WARN", True, "column absent")
    bad = int((df["last_payment_date"] < df["issue_date"]).sum())
    pct = bad / len(df) * 100 if len(df) else 0
    return CheckResult(
        "timeline: last_payment_date >= issue_date",
        "WARN",
        bad == 0,
        f"{bad:,} rows ({pct:.1f}%) have a last payment before the loan was issued - "
        "source date columns are not internally consistent",
    )


def check_repayment_duration_plausible(df: pd.DataFrame) -> CheckResult:
    """KNOWN DEFECT: 36-month loans cannot close inside twelve months."""
    fp = df[df["loan_status"] == "Fully Paid"]
    if fp.empty or "last_payment_date" not in df.columns:
        return CheckResult("timeline: repayment duration matches term", "WARN", True, "not testable")
    days = (fp["last_payment_date"] - fp["issue_date"]).dt.days
    implausible = int((days < 365).sum())
    pct = implausible / len(fp) * 100
    return CheckResult(
        "timeline: repayment duration matches term",
        "WARN",
        pct < 5,
        f"{pct:.1f}% of Fully Paid loans close within a year (median "
        f"{days.median():.0f} days) despite 36/60-month terms",
    )


def check_single_value_columns(df: pd.DataFrame) -> CheckResult:
    """Source columns with one distinct value carry no analytical information.

    Derived helper columns are excluded: ``issue_year`` is legitimately constant
    because the dataset covers a single calendar year.
    """
    from .data_loader import EXPECTED_COLUMNS

    constants = [
        c for c in EXPECTED_COLUMNS if c in df.columns and df[c].nunique(dropna=True) <= 1
    ]
    return CheckResult(
        "profiling: constant columns",
        "INFO",
        not constants,
        "no constant columns" if not constants else f"constant (no analytical value): {constants}",
    )


def check_emp_title_nulls(df: pd.DataFrame) -> CheckResult:
    if "emp_title" not in df.columns:
        return CheckResult("profiling: emp_title completeness", "INFO", True, "column absent")
    nulls = int(df["emp_title"].isna().sum())
    pct = nulls / len(df) * 100
    return CheckResult(
        "profiling: emp_title completeness",
        "INFO",
        nulls == 0,
        f"{nulls:,} nulls ({pct:.1f}%) - free-text field, feeds no KPI, left as-is",
    )


CHECKS: tuple[Callable[[pd.DataFrame], CheckResult], ...] = (
    check_no_missing_columns,
    check_unique_ids,
    check_kpi_columns_not_null,
    check_known_loan_statuses,
    check_rates_are_fractions,
    check_dates_are_day_first,
    check_term_trimmed,
    check_non_negative_amounts,
    check_charged_off_partial_recovery,
    check_payment_after_issue,
    check_repayment_duration_plausible,
    check_single_value_columns,
    check_emp_title_nulls,
)


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
def run_all(df: pd.DataFrame) -> list[CheckResult]:
    return [check(df) for check in CHECKS]


def to_frame(results: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"check": r.name, "severity": r.severity, "status": r.status, "detail": r.detail}
            for r in results
        ]
    )


def blocking_failures(results: list[CheckResult]) -> list[CheckResult]:
    """Checks whose failure means a published KPI would be wrong."""
    return [r for r in results if r.severity == "FAIL" and not r.passed]
