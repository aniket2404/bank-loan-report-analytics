"""Enterprise data-quality framework and profiling engine for lending data.

Implements a 4-tier validation severity model (BLOCKER, ERROR, WARNING, INFO),
data profiling, domain and boundary validation, anomaly detection, and
machine-readable JSON outputs for CI/CD gates.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from . import config, schema

Severity = Literal["BLOCKER", "ERROR", "WARNING", "INFO"]
Status = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class ValidationResult:
    """Individual data quality assertion outcome."""

    check_name: str
    severity: Severity
    status: Status
    observed_value: Any
    expected_value: Any
    message: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataProfile:
    """Statistical summary and profiling metrics for a dataset."""

    row_count: int
    column_count: int
    columns: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_dataframe(self) -> pd.DataFrame:
        records = []
        for col_name, stats in self.columns.items():
            row = {"column": col_name, **stats}
            records.append(row)
        return pd.DataFrame(records).sort_values("null_pct", ascending=False)


def profile_dataset(df: pd.DataFrame) -> DataProfile:
    """Generate comprehensive dataset profile metrics."""
    col_profiles: dict[str, dict[str, Any]] = {}
    total_rows = len(df)

    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = round((null_count / total_rows * 100) if total_rows else 0.0, 2)
        distinct_count = int(series.nunique(dropna=True))

        min_val: Any = None
        max_val: Any = None
        if pd.api.types.is_numeric_dtype(series) and not series.dropna().empty:
            min_val = float(series.min())
            max_val = float(series.max())
        elif pd.api.types.is_datetime64_any_dtype(series) and not series.dropna().empty:
            min_val = str(series.min().date())
            max_val = str(series.max().date())

        col_profiles[col] = {
            "dtype": str(series.dtype),
            "nulls": null_count,
            "null_pct": null_pct,
            "distinct_count": distinct_count,
            "min": min_val,
            "max": max_val,
        }

    return DataProfile(
        row_count=total_rows,
        column_count=len(df.columns),
        columns=col_profiles,
    )


# --------------------------------------------------------------------------- #
# Validation Check Definitions
# --------------------------------------------------------------------------- #

def check_schema_columns(df: pd.DataFrame) -> ValidationResult:
    missing = [c for c in schema.SOURCE_COLUMNS if c not in df.columns]
    passed = len(missing) == 0
    return ValidationResult(
        check_name="schema_columns_present",
        severity="BLOCKER",
        status="PASS" if passed else "FAIL",
        observed_value=f"{len(df.columns)} columns present" if passed else f"missing: {missing}",
        expected_value=f"all {len(schema.SOURCE_COLUMNS)} columns present",
        message="All expected source schema columns are present in the dataset."
        if passed
        else f"Critical missing columns: {missing}",
    )


def check_unique_loan_ids(df: pd.DataFrame) -> ValidationResult:
    dupes = int(df["id"].duplicated().sum()) if "id" in df.columns else 0
    passed = dupes == 0
    return ValidationResult(
        check_name="unique_loan_ids",
        severity="BLOCKER",
        status="PASS" if passed else "FAIL",
        observed_value=dupes,
        expected_value=0,
        message="Primary key uniqueness holds: one row per loan ID."
        if passed
        else f"Grain violation: detected {dupes:,} duplicate loan IDs.",
    )


def check_kpi_nulls(df: pd.DataFrame) -> ValidationResult:
    kpi_cols = ["id", "loan_amount", "total_payment", "int_rate", "dti", "issue_date", "loan_status", "term"]
    null_counts = {c: int(df[c].isna().sum()) for c in kpi_cols if c in df.columns}
    offenders = {c: count for c, count in null_counts.items() if count > 0}
    passed = len(offenders) == 0
    return ValidationResult(
        check_name="kpi_columns_completeness",
        severity="BLOCKER",
        status="PASS" if passed else "FAIL",
        observed_value=offenders if offenders else "0 nulls",
        expected_value="0 nulls across KPI columns",
        message="All critical KPI-driving columns are 100% complete."
        if passed
        else f"Incomplete critical KPI columns found: {offenders}",
    )


def check_loan_status_domain(df: pd.DataFrame) -> ValidationResult:
    if "loan_status" not in df.columns:
        return ValidationResult("loan_status_domain", "BLOCKER", "FAIL", "column missing", "present", "loan_status column missing.")
    found = set(df["loan_status"].dropna().unique())
    unknown = found - schema.VALID_LOAN_STATUSES
    passed = len(unknown) == 0
    return ValidationResult(
        check_name="loan_status_domain",
        severity="BLOCKER",
        status="PASS" if passed else "FAIL",
        observed_value=sorted(list(found)),
        expected_value=sorted(list(schema.VALID_LOAN_STATUSES)),
        message="All loan statuses conform to approved business domains."
        if passed
        else f"Unclassified loan status values detected: {sorted(list(unknown))}",
    )


def check_rate_fractional_units(df: pd.DataFrame) -> ValidationResult:
    problems = []
    for col in ("int_rate", "dti"):
        if col in df.columns:
            col_max = float(df[col].max())
            if col_max > 1.5:
                problems.append(f"{col} max={col_max:.4f}")
    passed = len(problems) == 0
    return ValidationResult(
        check_name="rate_fractional_units",
        severity="ERROR",
        status="PASS" if passed else "FAIL",
        observed_value="; ".join(problems) if problems else "decimal fractions <= 1.5",
        expected_value="decimal fractions (<= 1.5)",
        message="Interest rates and DTI ratios are stored as decimal fractions rather than whole percentages."
        if passed
        else f"Rate unit scaling error detected: {'; '.join(problems)}",
    )


def check_non_negative_amounts(df: pd.DataFrame) -> ValidationResult:
    monetary_cols = ["loan_amount", "total_payment", "installment", "annual_income"]
    negatives = {c: float(df[c].min()) for c in monetary_cols if c in df.columns and df[c].min() < 0}
    passed = len(negatives) == 0
    return ValidationResult(
        check_name="non_negative_amounts",
        severity="ERROR",
        status="PASS" if passed else "FAIL",
        observed_value=negatives if negatives else "all >= 0",
        expected_value="all amounts >= 0",
        message="All financial and income fields are non-negative."
        if passed
        else f"Negative financial values found: {negatives}",
    )


def check_categorical_domains(df: pd.DataFrame) -> ValidationResult:
    issues = []
    if "term" in df.columns:
        invalid_terms = set(df["term"].dropna().unique()) - schema.VALID_TERMS
        if invalid_terms:
            issues.append(f"term: {invalid_terms}")
    if "grade" in df.columns:
        invalid_grades = set(df["grade"].dropna().unique()) - schema.VALID_GRADES
        if invalid_grades:
            issues.append(f"grade: {invalid_grades}")
    if "home_ownership" in df.columns:
        invalid_home = set(df["home_ownership"].dropna().unique()) - schema.VALID_HOME_OWNERSHIPS
        if invalid_home:
            issues.append(f"home_ownership: {invalid_home}")

    passed = len(issues) == 0
    return ValidationResult(
        check_name="categorical_domains",
        severity="ERROR",
        status="PASS" if passed else "FAIL",
        observed_value="; ".join(issues) if issues else "all categories valid",
        expected_value="standard category domains",
        message="All categorical fields conform to validated domain values."
        if passed
        else f"Domain violations: {'; '.join(issues)}",
    )


def check_recovery_partial(df: pd.DataFrame) -> ValidationResult:
    bad = df[df["loan_status"].isin(list(config.BAD_LOAN_STATUSES))]
    if bad.empty:
        return ValidationResult("charged_off_partial_recovery", "ERROR", "PASS", "no charged off", "< 100%", "No charged-off loans present.")
    funded = float(bad["loan_amount"].sum())
    received = float(bad["total_payment"].sum())
    recovery_pct = (received / funded * 100) if funded > 0 else 0.0
    passed = 0.0 < recovery_pct < 100.0
    return ValidationResult(
        check_name="charged_off_partial_recovery",
        severity="ERROR",
        status="PASS" if passed else "FAIL",
        observed_value=f"{recovery_pct:.2f}%",
        expected_value="between 0% and 100%",
        message=f"Charged-off loans show expected partial cash recovery ({recovery_pct:.2f}%)."
        if passed
        else f"Anomalous charge-off recovery rate: {recovery_pct:.2f}%",
    )


def check_payment_date_chronology(df: pd.DataFrame) -> ValidationResult:
    """Known defect in standard source data where last_payment_date < issue_date."""
    if "last_payment_date" not in df.columns or "issue_date" not in df.columns:
        return ValidationResult("payment_date_chronology", "WARNING", "PASS", "columns absent", "chronological", "Date columns absent.")
    invalid = int((df["last_payment_date"] < df["issue_date"]).sum())
    pct = round(invalid / len(df) * 100, 2) if len(df) else 0.0
    passed = invalid == 0
    return ValidationResult(
        check_name="payment_date_chronology",
        severity="WARNING",
        status="PASS" if passed else "FAIL",
        observed_value=f"{invalid:,} loans ({pct}%)",
        expected_value="0 loans with payment date before issue date",
        message="All payment dates occur on or after issue dates."
        if passed
        else f"Known dataset defect: {invalid:,} loans ({pct}%) have payment date preceding issue date.",
    )


def check_repayment_duration_plausibility(df: pd.DataFrame) -> ValidationResult:
    """Known defect in standard source data where loans close faster than term."""
    fp = df[df["loan_status"] == "Fully Paid"]
    if fp.empty or "last_payment_date" not in df.columns:
        return ValidationResult("repayment_duration_plausibility", "WARNING", "PASS", "not testable", "plausible", "Cannot test repayment duration.")
    days = (fp["last_payment_date"] - fp["issue_date"]).dt.days
    implausible = int((days < 365).sum())
    pct = round(implausible / len(fp) * 100, 2)
    passed = pct < 5.0
    return ValidationResult(
        check_name="repayment_duration_plausibility",
        severity="WARNING",
        status="PASS" if passed else "FAIL",
        observed_value=f"{implausible:,} loans ({pct}%)",
        expected_value="< 5% closing inside 1 year",
        message="Repayment duration matches loan term structures."
        if passed
        else f"Known dataset defect: {pct}% of Fully Paid loans close within 1 year despite 36/60-month terms.",
    )


def check_constant_columns(df: pd.DataFrame) -> ValidationResult:
    constants = [
        c for c in schema.SOURCE_COLUMNS if c in df.columns and df[c].nunique(dropna=True) <= 1
    ]
    passed = len(constants) == 0
    return ValidationResult(
        check_name="constant_columns_profiling",
        severity="INFO",
        status="PASS" if passed else "FAIL",
        observed_value=constants if constants else "none",
        expected_value="no constant columns",
        message="No zero-variance constant features detected."
        if passed
        else f"Zero-variance constant columns detected (informative only): {constants}",
    )


def check_emp_title_missingness(df: pd.DataFrame) -> ValidationResult:
    if "emp_title" not in df.columns:
        return ValidationResult("emp_title_missingness", "INFO", "PASS", "absent", "informative", "emp_title column absent.")
    nulls = int(df["emp_title"].isna().sum())
    pct = round(nulls / len(df) * 100, 2)
    return ValidationResult(
        check_name="emp_title_missingness",
        severity="INFO",
        status="PASS" if nulls == 0 else "FAIL",
        observed_value=f"{nulls:,} nulls ({pct}%)",
        expected_value="0 nulls",
        message="Employment title column is completely populated."
        if nulls == 0
        else f"Employment title is free-text and contains {nulls:,} nulls ({pct}%); not used in core risk models.",
    )


def check_issue_date_freshness(df: pd.DataFrame) -> ValidationResult:
    if "issue_date" not in df.columns or df["issue_date"].dropna().empty:
        return ValidationResult("issue_date_freshness", "INFO", "FAIL", "no dates", "dates", "issue_date missing.")
    min_date = str(df["issue_date"].min().date())
    max_date = str(df["issue_date"].max().date())
    return ValidationResult(
        check_name="issue_date_freshness",
        severity="INFO",
        status="PASS",
        observed_value=f"{min_date} to {max_date}",
        expected_value="2021 calendar vintage",
        message=f"Dataset coverage spans {min_date} to {max_date}.",
    )


QUALITY_CHECKS: tuple[Callable[[pd.DataFrame], ValidationResult], ...] = (
    check_schema_columns,
    check_unique_loan_ids,
    check_kpi_nulls,
    check_loan_status_domain,
    check_rate_fractional_units,
    check_non_negative_amounts,
    check_categorical_domains,
    check_recovery_partial,
    check_payment_date_chronology,
    check_repayment_duration_plausibility,
    check_constant_columns,
    check_emp_title_missingness,
    check_issue_date_freshness,
)


def run_quality_audit(df: pd.DataFrame) -> list[ValidationResult]:
    """Execute all data-quality validations against the dataset."""
    return [check(df) for check in QUALITY_CHECKS]


def results_to_dataframe(results: list[ValidationResult]) -> pd.DataFrame:
    """Convert validation results into a displayable pandas DataFrame."""
    return pd.DataFrame([r.to_dict() for r in results])


def audit_summary(results: list[ValidationResult]) -> dict[str, Any]:
    """Provide a structured summary suitable for CI pass/fail gates."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    blockers = sum(1 for r in results if r.severity == "BLOCKER" and not r.passed)
    errors = sum(1 for r in results if r.severity == "ERROR" and not r.passed)
    warnings = sum(1 for r in results if r.severity == "WARNING" and not r.passed)
    infos = sum(1 for r in results if r.severity == "INFO" and not r.passed)

    is_ci_clean = blockers == 0 and errors == 0

    return {
        "total_checks": total,
        "passed": passed,
        "failed": total - passed,
        "blockers": blockers,
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "ci_status": "PASSED" if is_ci_clean else "FAILED",
    }


def results_to_json(results: list[ValidationResult], path: Path | str | None = None) -> str:
    """Export machine-readable validation results to JSON string or file."""
    summary = audit_summary(results)
    payload = {
        "summary": summary,
        "checks": [r.to_dict() for r in results],
    }
    json_str = json.dumps(payload, indent=2)
    if path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str, encoding="utf-8")
    return json_str
