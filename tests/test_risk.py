"""Regression tests for the risk / business-insight layer.

Two kinds of test live here:

1. **Invariant tests** - relationships that must hold on any subset of this
   dataset (rates bounded 0-100, funded + net = received, shares summing to
   100%, volume floors respected). These run on the bundled sample too.
2. **Value tests** - the exact figures quoted in ``README.md``,
   ``docs/INSIGHTS.md`` and the ``sql/06_risk_and_cohort_analysis.sql``
   comments. These need the full 38,576-row dataset and are skipped when only
   the sample is present, because a 600-row sample cannot reproduce them.

The value tests are the point of this file: they are what stops the
documentation from drifting away from the code.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bank_loan_report import config, data_loader, risk

FULL_ROW_COUNT = 38_576

requires_full = pytest.mark.skipif(
    not config.RAW_CSV_PATH.exists(),
    reason="full financial_loan.csv not present; see data/README.md",
)


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return data_loader.load_loans()


@pytest.fixture(scope="module")
def flagged(df: pd.DataFrame) -> pd.DataFrame:
    return risk.add_risk_flags(df)


# --------------------------------------------------------------------------- #
# add_risk_flags
# --------------------------------------------------------------------------- #
def test_risk_flags_are_added(flagged):
    for col in ("is_charged_off", "is_closed", "dti_band", "income_quintile", "loan_size_band"):
        assert col in flagged.columns


def test_charged_off_flag_matches_loan_status(flagged):
    expected = flagged["loan_status"] == "Charged Off"
    assert flagged["is_charged_off"].astype(bool).tolist() == expected.tolist()


def test_closed_flag_excludes_current(flagged):
    assert not flagged.loc[flagged["loan_status"] == "Current", "is_closed"].astype(bool).any()
    assert flagged.loc[flagged["loan_status"] == "Fully Paid", "is_closed"].astype(bool).all()


def test_add_risk_flags_does_not_mutate_input(df):
    before = set(df.columns)
    risk.add_risk_flags(df)
    assert set(df.columns) == before


def test_bands_cover_every_row(flagged):
    """No row may fall outside a band - a silent NaN band would drop loans
    from every segment table without warning."""
    for col in ("dti_band", "income_quintile", "loan_size_band"):
        assert flagged[col].isna().sum() == 0, col


# --------------------------------------------------------------------------- #
# portfolio economics
# --------------------------------------------------------------------------- #
def test_portfolio_economics_net_margin_reconciles(df):
    econ = risk.portfolio_economics(df)
    reconstructed = econ["amount_received"] - econ["funded_amount"]
    pd.testing.assert_series_equal(
        econ["net_margin"].astype(float),
        reconstructed.astype(float),
        check_names=False,
    )


def test_portfolio_economics_statuses_sum_to_the_total_row(df):
    """The 'Total portfolio' row must equal the sum of the per-status rows -
    otherwise a loan status has been dropped or double counted."""
    econ = risk.portfolio_economics(df)
    per_status = econ[econ["segment"] != "Total portfolio"]
    total = econ[econ["segment"] == "Total portfolio"].iloc[0]
    assert per_status["loans"].sum() == len(df) == total["loans"]
    assert per_status["funded_amount"].sum() == total["funded_amount"]
    assert per_status["amount_received"].sum() == total["amount_received"]
    assert abs(per_status["share_of_funded_pct"].sum() - 100) < 1e-6


def test_recovery_rate_is_consistent_with_its_inputs(df):
    econ = risk.portfolio_economics(df)
    for row in econ.itertuples():
        expected = row.amount_received / row.funded_amount * 100
        assert abs(row.recovery_rate_pct - expected) < 1e-6


@requires_full
def test_portfolio_economics_exact_values(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    econ = risk.portfolio_economics(df).set_index("segment")

    assert econ.loc["Charged Off", "loans"] == 5_333
    assert econ.loc["Charged Off", "funded_amount"] == 65_532_225
    assert econ.loc["Charged Off", "amount_received"] == 37_284_763
    assert round(econ.loc["Charged Off", "recovery_rate_pct"], 2) == 56.90
    assert econ.loc["Charged Off", "net_margin"] == -28_247_462

    assert econ.loc["Fully Paid", "loans"] == 32_145
    assert econ.loc["Current", "loans"] == 1_098

    total = econ.loc["Total portfolio"]
    assert total["funded_amount"] == 435_757_075
    assert total["amount_received"] == 473_070_933
    assert total["net_margin"] == 37_313_858
    assert round(total["recovery_rate_pct"], 2) == 108.56


# --------------------------------------------------------------------------- #
# segment_risk
# --------------------------------------------------------------------------- #
def test_segment_risk_rates_are_bounded(df):
    seg = risk.segment_risk(df, "grade")
    assert seg["default_rate_pct"].between(0, 100).all()
    assert (seg["recovery_rate_pct"] > 0).all()


def test_segment_risk_loan_counts_sum_to_total(df):
    seg = risk.segment_risk(df, "grade")
    assert seg["loans"].sum() == len(df)
    assert abs(seg["share_of_loans_pct"].sum() - 100) < 1e-6


def test_segment_risk_min_loans_floor_is_applied(df):
    seg = risk.segment_risk(df, "purpose", min_loans=500)
    assert (seg["loans"] >= 500).all()


def test_segment_risk_rejects_unknown_column(df):
    with pytest.raises(KeyError):
        risk.segment_risk(df, "not_a_column")


def test_segment_risk_interest_rate_is_a_percentage(df):
    """int_rate is stored as a fraction; the segment table must scale it once."""
    seg = risk.segment_risk(df, "grade")
    assert seg["avg_interest_rate"].between(1, 40).all()


@requires_full
def test_grade_default_gradient_is_monotonic(df):
    """The business claim in the README: risk rises with every grade step."""
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    seg = risk.segment_risk(df, "grade").sort_values("grade")
    rates = seg["default_rate_pct"].tolist()
    assert rates == sorted(rates), rates
    assert round(rates[0], 2) == 5.70   # grade A
    assert round(rates[-1], 2) == 31.31  # grade G


@requires_full
def test_grade_interest_rate_gradient_is_monotonic(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    seg = risk.segment_risk(df, "grade").sort_values("grade")
    rates = seg["avg_interest_rate"].tolist()
    assert rates == sorted(rates), rates


@requires_full
def test_sixty_month_term_is_riskier(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    seg = risk.segment_risk(df, "term").set_index("term")
    assert round(seg.loc["60 months", "default_rate_pct"], 2) == 22.34
    assert round(seg.loc["36 months", "default_rate_pct"], 2) == 10.71


@requires_full
def test_small_business_is_the_only_loss_making_purpose(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    losers = risk.unprofitable_segments(df, "purpose", min_loans=50)
    assert list(losers["purpose"]) == ["small business"]
    row = losers.iloc[0]
    assert row["loans"] == 1_776
    assert round(row["default_rate_pct"], 2) == 25.62
    assert row["net_margin"] == -308_283


@requires_full
def test_income_gradient_is_monotonic(df):
    """Lower income quintile -> higher default rate, with no reversals."""
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    seg = risk.segment_risk(risk.add_risk_flags(df), "income_quintile")
    seg = seg.sort_values("income_quintile")
    rates = seg["default_rate_pct"].tolist()
    assert rates == sorted(rates, reverse=True), rates


# --------------------------------------------------------------------------- #
# headline metrics
# --------------------------------------------------------------------------- #
def test_headline_metrics_have_units(df):
    head = risk.headline_risk_metrics(df)
    assert set(head.columns) == {"metric", "value", "unit"}
    assert head["unit"].isin({"pct", "usd", "count", "ratio"}).all()


@requires_full
def test_headline_default_rates(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    head = risk.headline_risk_metrics(df).set_index("metric")
    all_loans = head.loc["Default rate (all loans)", "value"]
    closed = head.loc["Default rate (closed loans only)", "value"]
    assert round(all_loans, 2) == 13.82
    assert round(closed, 2) == 14.23
    # the closed-loan rate must be the higher of the two: excluding loans that
    # have not yet had the chance to default can only raise the rate
    assert closed > all_loans


# --------------------------------------------------------------------------- #
# pricing power
# --------------------------------------------------------------------------- #
def test_pricing_power_returns_bounded_correlations(df):
    pricing = risk.pricing_power(df).iloc[0]
    for key in ("pearson_r", "spearman_rho"):
        assert -1 <= pricing[key] <= 1


@requires_full
def test_pricing_power_exact_values(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    pricing = risk.pricing_power(df).iloc[0]
    assert round(pricing["spearman_rho"], 3) == 0.959
    assert round(pricing["pearson_r"], 3) == 0.934
    assert pricing["segments_compared"] == 35


# --------------------------------------------------------------------------- #
# concentration
# --------------------------------------------------------------------------- #
def test_concentration_is_cumulative_and_bounded(df):
    conc = risk.concentration(df)
    assert conc["share_of_funded_pct"].between(0, 100).all()
    for dimension, group in conc.groupby("dimension"):
        # a top-N share can only grow as N grows
        values = group.sort_values("top_n")["share_of_funded_pct"].tolist()
        assert values == sorted(values), dimension


@requires_full
def test_concentration_exact_values(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    conc = risk.concentration(df)
    states = conc[conc["dimension"] == "States"].set_index("top_n")
    assert round(states.loc[1, "share_of_funded_pct"], 1) == 18.0
    assert round(states.loc[3, "share_of_funded_pct"], 1) == 34.8
    assert round(states.loc[10, "share_of_funded_pct"], 1) == 64.9
    assert states.loc[1, "members"] == "CA"


# --------------------------------------------------------------------------- #
# term x grade - cross-check against sql/06 section 7
# --------------------------------------------------------------------------- #
def test_term_grade_risk_benchmark_is_the_closed_loan_rate(df):
    tg = risk.term_grade_risk(df, min_loans=1)
    if tg.empty:
        pytest.skip("no closed loans in this dataset")
    closed = risk.add_risk_flags(df)
    closed = closed[closed["is_closed"].astype(bool)]
    expected = closed["is_charged_off"].mean() * 100
    assert abs(tg["portfolio_default_pct"].iloc[0] - expected) < 1e-9


def test_term_grade_risk_multiple_is_consistent(df):
    tg = risk.term_grade_risk(df, min_loans=1)
    if tg.empty:
        pytest.skip("no closed loans in this dataset")
    recomputed = tg["segment_default_pct"] / tg["portfolio_default_pct"]
    assert (tg["risk_multiple"] - recomputed).abs().max() < 1e-9


def test_term_grade_risk_is_ranked_descending(df):
    tg = risk.term_grade_risk(df, min_loans=1)
    if tg.empty:
        pytest.skip("no closed loans in this dataset")
    assert tg["risk_rank"].tolist() == list(range(1, len(tg) + 1))
    rates = tg["segment_default_pct"].tolist()
    assert rates == sorted(rates, reverse=True)


@requires_full
def test_term_grade_risk_matches_sql_06_section_7(df):
    """These are the exact figures quoted in sql/06_risk_and_cohort_analysis.sql.

    The SQL cannot be executed in CI (no SQL Server), so this test is the
    guarantee that the numbers written in its comments are real.
    """
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    tg = risk.term_grade_risk(df, min_loans=100)
    assert len(tg) == 13
    assert round(tg["portfolio_default_pct"].iloc[0], 2) == 14.23

    worst = tg.iloc[0]
    assert (worst["term"], worst["grade"]) == ("60 months", "F")
    assert worst["loans"] == 751
    assert round(worst["segment_default_pct"], 2) == 34.22

    best = tg.iloc[-1]
    assert (best["term"], best["grade"]) == ("36 months", "A")
    assert best["loans"] == 9_274
    assert round(best["segment_default_pct"], 2) == 5.57

    indexed = tg.set_index(["term", "grade"])
    # grade beats term: a 60-month A is still safer than a 36-month B
    assert (
        indexed.loc[("60 months", "A"), "segment_default_pct"]
        < indexed.loc[("36 months", "B"), "segment_default_pct"]
    )


# --------------------------------------------------------------------------- #
# monthly trend
# --------------------------------------------------------------------------- #
def test_monthly_trend_is_chronological(df):
    trend = risk.monthly_risk_trend(df)
    assert trend["issue_month"].is_monotonic_increasing


@requires_full
def test_monthly_trend_growth(df):
    if len(df) != FULL_ROW_COUNT:
        pytest.skip("not the full dataset")
    trend = risk.monthly_risk_trend(df)
    assert len(trend) == 12
    assert trend["loans"].iloc[0] == 2_332
    assert trend["loans"].iloc[-1] == 4_314
    assert round(trend["loans_mom_pct"].iloc[-1], 2) == 6.91
    assert round(trend["funded_mom_pct"].iloc[-1], 2) == 13.04


# --------------------------------------------------------------------------- #
# the exported table registry
# --------------------------------------------------------------------------- #
def test_every_risk_table_builds_and_is_non_empty(df):
    for name, builder in risk.RISK_TABLES.items():
        table = builder(df)
        assert isinstance(table, pd.DataFrame), name
        assert not table.empty, name


def test_spearman_is_computed_without_scipy(df, monkeypatch):
    """``pricing_power`` must not depend on scipy.

    pandas' ``corr(method="spearman")`` imports scipy lazily, so the module
    installs fine and then fails at call time on a scipy-free environment -
    which is exactly how this broke in CI. Blocking the import here proves the
    rank-based implementation stands on its own.
    """
    import builtins

    real_import = builtins.__import__

    def no_scipy(name, *args, **kwargs):
        if name.split(".")[0] == "scipy":
            raise ModuleNotFoundError("No module named 'scipy'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_scipy)
    result = risk.pricing_power(df)
    assert -1.0 <= result["spearman_rho"].iloc[0] <= 1.0


def test_risk_ranking_on_a_dataset_below_every_volume_floor(df):
    """A tiny slice yields an empty ranking with the full column set, not a crash."""
    ranking = risk.risk_ranking(df.head(5), min_loans=300)
    assert ranking.empty
    assert list(ranking.columns) == [
        "dimension",
        "segment_value",
        "loans",
        "default_rate_pct",
        "avg_interest_rate",
        "recovery_rate_pct",
        "net_margin",
    ]
