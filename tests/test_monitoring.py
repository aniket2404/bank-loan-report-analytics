"""Tests for cohort drift monitoring and PSI calculations."""

from __future__ import annotations

import pandas as pd
import pytest

from bank_loan_report import data_loader, monitoring


def test_psi_identical_distributions():
    dist = pd.Series({"A": 0.4, "B": 0.4, "C": 0.2})
    psi = monitoring.calculate_psi(dist, dist)
    assert psi == pytest.approx(0.0, abs=1e-3)


def test_psi_shifted_distributions():
    exp = pd.Series({"A": 0.7, "B": 0.2, "C": 0.1})
    act = pd.Series({"A": 0.1, "B": 0.3, "C": 0.6})
    psi = monitoring.calculate_psi(exp, act)
    assert psi > 0.25


def test_portfolio_drift():
    df = data_loader.load_loans(use_sample=True)
    drift = monitoring.compute_portfolio_drift(df, split_month=7)
    assert isinstance(drift, list)
    if drift:
        metrics = {m.metric for m in drift}
        assert "origination_volume" in metrics
        assert "default_rate_pct" in metrics
