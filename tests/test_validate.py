"""Tests for the data validation suite.

The validation suite is the project's safety net, so it needs its own net. Two
things are tested here:

1. That the suite reports the true, documented state of this dataset - every
   FAIL-severity check passes, and exactly the two known timeline defects are
   reported as WARN.
2. That the checks actually detect breakage. Several tests deliberately corrupt
   a copy of the data (a US-locale date mis-parse, an un-scaled interest rate,
   a duplicated id) and assert the relevant check flips to failing. A check
   that can never fail is worthless, and this is how we prove these can.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bank_loan_report import config, data_loader, validate

FULL_ROW_COUNT = 38_576

requires_full = pytest.mark.skipif(
    not config.RAW_CSV_PATH.exists(),
    reason="full financial_loan.csv not present; see data/README.md",
)


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return data_loader.load_loans()


@pytest.fixture(scope="module")
def results(df: pd.DataFrame) -> list[validate.CheckResult]:
    return validate.run_all(df)


# --------------------------------------------------------------------------- #
# structure of the suite
# --------------------------------------------------------------------------- #
def test_every_check_returns_a_result(results):
    assert len(results) == len(validate.CHECKS)
    assert all(isinstance(r, validate.CheckResult) for r in results)


def test_check_names_are_unique(results):
    names = [r.name for r in results]
    assert len(names) == len(set(names))


def test_severities_are_valid(results):
    assert {r.severity for r in results} <= {"FAIL", "WARN", "INFO"}


def test_every_result_explains_itself(results):
    """A check with no detail string is useless in a report."""
    for r in results:
        assert r.detail.strip(), r.name


def test_status_property_reflects_outcome():
    passing = validate.CheckResult("x", "FAIL", True, "ok")
    failing = validate.CheckResult("x", "FAIL", False, "bad")
    warning = validate.CheckResult("x", "WARN", False, "known defect")
    assert passing.status == "PASS"
    assert failing.status == "FAIL"
    assert warning.status == "WARN"


def test_to_frame_shape(results):
    frame = validate.to_frame(results)
    assert list(frame.columns) == ["check", "severity", "status", "detail"]
    assert len(frame) == len(results)


# --------------------------------------------------------------------------- #
# the suite's verdict on the real dataset
# --------------------------------------------------------------------------- #
def test_no_blocking_failures(results):
    """Any FAIL-severity check that fails means a published KPI is wrong."""
    blocking = validate.blocking_failures(results)
    assert not blocking, [f"{r.name}: {r.detail}" for r in blocking]


def test_kpi_guarding_checks_all_pass(results):
    for r in results:
        if r.severity == "FAIL":
            assert r.passed, f"{r.name}: {r.detail}"


@requires_full
def test_exactly_the_two_documented_warnings_are_raised(df):
    """The two date defects are expected. A third WARN would be news, and a
    disappearing WARN would mean the check stopped working."""
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    warnings = [r.name for r in validate.run_all(df) if r.severity == "WARN" and not r.passed]
    assert len(warnings) == 2, warnings
    joined = " ".join(warnings).lower()
    assert "payment" in joined
    assert "duration" in joined or "term" in joined


# --------------------------------------------------------------------------- #
# negative tests - prove the checks can actually fail
# --------------------------------------------------------------------------- #
def test_duplicate_id_is_detected(df):
    broken = pd.concat([df, df.head(1)], ignore_index=True)
    assert not validate.check_unique_ids(broken).passed


def test_unexpected_loan_status_is_detected(df):
    broken = df.copy()
    broken.loc[broken.index[0], "loan_status"] = "Default"
    assert not validate.check_known_loan_statuses(broken).passed


def test_percent_scaled_rate_is_detected(df):
    """The classic mistake with this dataset: multiplying int_rate by 100 in
    the loader as well as in the presentation layer."""
    broken = df.copy()
    broken["int_rate"] = broken["int_rate"] * 100
    assert not validate.check_rates_are_fractions(broken).passed


def test_us_locale_date_misparse_is_detected(df):
    """If the CSV is read with month-first parsing, dates leak out of 2021."""
    broken = df.copy()
    broken.loc[broken.index[0], "issue_date"] = pd.Timestamp("2020-05-01")
    assert not validate.check_dates_are_day_first(broken).passed


def test_untrimmed_term_is_detected(df):
    broken = df.copy()
    broken["term"] = " " + broken["term"].astype(str)
    assert not validate.check_term_trimmed(broken).passed


def test_negative_amount_is_detected(df):
    broken = df.copy()
    broken.loc[broken.index[0], "loan_amount"] = -1
    assert not validate.check_non_negative_amounts(broken).passed


def test_missing_column_is_detected(df):
    broken = df.drop(columns=["loan_amount"])
    assert not validate.check_no_missing_columns(broken).passed


def test_null_kpi_column_is_detected(df):
    broken = df.copy()
    broken.loc[broken.index[0], "loan_amount"] = None
    assert not validate.check_kpi_columns_not_null(broken).passed


def test_blocking_failures_ignores_warn_and_info():
    results = [
        validate.CheckResult("a", "WARN", False, "known"),
        validate.CheckResult("b", "INFO", False, "noted"),
        validate.CheckResult("c", "FAIL", True, "fine"),
    ]
    assert validate.blocking_failures(results) == []
    results.append(validate.CheckResult("d", "FAIL", False, "broken"))
    assert [r.name for r in validate.blocking_failures(results)] == ["d"]
