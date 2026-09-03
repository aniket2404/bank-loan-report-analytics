"""Regression tests for the Bank Loan Report KPI layer.

Tests that assert exact dollar figures require the full dataset and are skipped
automatically when only the bundled sample is present. The structural and
business-rule tests run either way.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bank_loan_report import charts, config, data_loader, kpis

FULL_ROW_COUNT = 38_576


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return data_loader.load_loans()


@pytest.fixture(scope="module")
def is_full(df: pd.DataFrame) -> bool:
    return len(df) == FULL_ROW_COUNT


requires_full = pytest.mark.skipif(
    not config.RAW_CSV_PATH.exists(),
    reason="full financial_loan.csv not present; see data/README.md",
)


# --------------------------------------------------------------------------- #
# loading and cleaning
# --------------------------------------------------------------------------- #
def test_expected_columns_present(df):
    for col in data_loader.EXPECTED_COLUMNS:
        assert col in df.columns


def test_dates_are_parsed(df):
    for col in config.DATE_COLUMNS:
        assert pd.api.types.is_datetime64_any_dtype(df[col]), col


def test_dates_are_day_first(df):
    """A US-locale mis-parse would push issue_date outside calendar year 2021."""
    assert df["issue_date"].min().year == 2021
    assert df["issue_date"].max().year == 2021


def test_term_is_trimmed(df):
    assert set(df["term"].dropna().unique()) == {"36 months", "60 months"}


def test_ids_are_unique(df):
    assert not df["id"].duplicated().any()


def test_derived_columns_added(df):
    for col in ("issue_month", "issue_month_name", "loan_quality"):
        assert col in df.columns


def test_emp_length_is_ordered(df):
    assert isinstance(df["emp_length"].dtype, pd.CategoricalDtype)
    assert df["emp_length"].cat.ordered
    assert list(df["emp_length"].cat.categories)[0] == "< 1 year"
    assert list(df["emp_length"].cat.categories)[-1] == "10+ years"


# --------------------------------------------------------------------------- #
# business rules
# --------------------------------------------------------------------------- #
def test_loan_quality_matches_statuses(df):
    good = df[df["loan_quality"] == "Good Loan"]["loan_status"].unique()
    bad = df[df["loan_quality"] == "Bad Loan"]["loan_status"].unique()
    assert set(good) <= set(config.GOOD_LOAN_STATUSES)
    assert set(bad) <= set(config.BAD_LOAN_STATUSES)


def test_good_and_bad_partition_the_data(df):
    quality = kpis.good_bad_loan_kpis(df)
    assert quality["applications"].sum() == len(df)
    assert quality["application_pct"].sum() == pytest.approx(100.0)


def test_periods_are_adjacent(df):
    year, month = kpis.latest_period(df)
    p_year, p_month = kpis.previous_period(year, month)
    assert (p_year, p_month) == (year, month - 1) or (p_year, p_month) == (year - 1, 12)
    assert len(kpis.mtd_frame(df)) > 0
    assert len(kpis.pmtd_frame(df)) > 0


def test_mom_change_handles_zero_denominator():
    assert kpis.mom_change(10, 0) == 0.0
    assert kpis.mom_change(110, 100) == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# internal consistency - these must hold on any slice of the data
# --------------------------------------------------------------------------- #
def test_summary_shape(df):
    summary = kpis.summary_kpis(df)
    assert list(summary.columns) == ["name", "total", "mtd", "pmtd", "mom_pct"]
    assert len(summary) == 5


def test_grid_totals_match_dataset(df):
    grid = kpis.loan_status_grid(df)
    assert grid["total_loan_applications"].sum() == kpis.total_loan_applications(df)
    assert grid["total_funded_amount"].sum() == pytest.approx(kpis.total_funded_amount(df))
    assert grid["total_amount_received"].sum() == pytest.approx(kpis.total_amount_received(df))


@pytest.mark.parametrize("name", list(kpis.OVERVIEW_AGGREGATIONS))
def test_every_aggregation_reconciles(df, name):
    """Each Overview breakdown must sum back to the dataset totals."""
    table = kpis.OVERVIEW_AGGREGATIONS[name](df)
    assert len(table) > 0
    assert table["total_loan_applications"].sum() == kpis.total_loan_applications(df)
    assert table["total_funded_amount"].sum() == pytest.approx(kpis.total_funded_amount(df))


def test_rates_are_percentages(df):
    assert 0 < kpis.average_interest_rate(df) < 100
    assert 0 < kpis.average_dti(df) < 100


def test_details_table_is_complete(df):
    assert len(kpis.details_table(df)) == len(df)
    assert len(kpis.details_table(df, limit=5)) == 5


# --------------------------------------------------------------------------- #
# exact figures - full dataset only
# --------------------------------------------------------------------------- #
@requires_full
def test_full_dataset_row_count(df, is_full):
    if not is_full:
        pytest.skip("sample data in use")
    assert len(df) == FULL_ROW_COUNT


@requires_full
def test_headline_kpis(df, is_full):
    if not is_full:
        pytest.skip("sample data in use")
    assert kpis.total_loan_applications(df) == 38_576
    assert kpis.total_funded_amount(df) == pytest.approx(435_757_075)
    assert kpis.total_amount_received(df) == pytest.approx(473_070_933)
    assert kpis.average_interest_rate(df) == pytest.approx(12.05, abs=0.01)
    assert kpis.average_dti(df) == pytest.approx(13.33, abs=0.01)


@requires_full
def test_mtd_pmtd_values(df, is_full):
    if not is_full:
        pytest.skip("sample data in use")
    assert kpis.latest_period(df) == (2021, 12)
    assert kpis.total_loan_applications(kpis.mtd_frame(df)) == 4_314
    assert kpis.total_loan_applications(kpis.pmtd_frame(df)) == 4_035
    assert kpis.total_funded_amount(kpis.mtd_frame(df)) == pytest.approx(53_981_425)


@requires_full
def test_good_bad_split(df, is_full):
    if not is_full:
        pytest.skip("sample data in use")
    quality = kpis.good_bad_loan_kpis(df).set_index("category")
    assert quality.loc["Good Loan", "applications"] == 33_243
    assert quality.loc["Bad Loan", "applications"] == 5_333
    assert quality.loc["Good Loan", "application_pct"] == pytest.approx(86.18, abs=0.01)
    assert quality.loc["Bad Loan", "application_pct"] == pytest.approx(13.82, abs=0.01)


@requires_full
def test_twelve_months_present(df, is_full):
    if not is_full:
        pytest.skip("sample data in use")
    assert len(kpis.by_month(df)) == 12
    assert len(kpis.by_state(df)) == 50


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def test_all_charts_render(df, tmp_path):
    written = charts.build_all(df, tmp_path)
    assert len(written) == 6
    for path in written:
        assert path.exists() and path.stat().st_size > 1_000
