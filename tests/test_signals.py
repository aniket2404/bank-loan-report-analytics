"""Tests for signal quality, monotonicity, lift, and correlation metrics."""

from __future__ import annotations

import pytest

from bank_loan_report import data_loader, signals


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_segment_lift(df):
    lift_df = signals.compute_segment_lift(df, "term", min_loans=50)
    assert not lift_df.empty
    assert "lift_ratio" in lift_df.columns
    assert "confidence" in lift_df.columns
    assert all(lift_df["lift_ratio"] > 0)


def test_feature_correlations(df):
    corr_df = signals.feature_correlations(df)
    assert not corr_df.empty
    assert "pearson_r" in corr_df.columns
    assert "spearman_rho" in corr_df.columns
    assert "signal_direction" in corr_df.columns


def test_extract_risk_findings(df):
    findings = signals.extract_risk_findings(df)
    assert isinstance(findings, list)
    for f in findings:
        assert f.metric == "default_rate_pct"
        assert f.effect_size > 0
        assert len(f.caveat) > 0
