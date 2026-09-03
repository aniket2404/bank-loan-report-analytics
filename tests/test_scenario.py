"""Tests for stress testing and scenario analysis."""

from __future__ import annotations

import pytest

from bank_loan_report import data_loader, scenario


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_run_all_scenarios(df):
    outcomes = scenario.run_all_scenarios(df)
    assert len(outcomes) == 4
    names = [o.scenario_name for o in outcomes]
    assert "default_rate_shock_25pct" in names
    assert "recovery_haircut_30pct" in names
    assert "exclude_grades_f_g" in names
    assert "severe_macro_crisis" in names

    for o in outcomes:
        assert o.expected_loss_proxy_usd >= 0
        assert o.scenario_net_margin <= o.baseline_net_margin or o.scenario_name == "exclude_grades_f_g"
