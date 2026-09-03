"""Tests for the data-quality framework and profiling engine."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from bank_loan_report import data_loader, quality


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_profile_dataset(df):
    profile = quality.profile_dataset(df)
    assert profile.row_count == len(df)
    assert profile.column_count == len(df.columns)
    assert "loan_amount" in profile.columns
    assert profile.columns["loan_amount"]["min"] > 0
    df_profile = profile.to_dataframe()
    assert isinstance(df_profile, pd.DataFrame)
    assert len(df_profile) == len(df.columns)


def test_quality_audit_clean_data(df):
    results = quality.run_quality_audit(df)
    assert len(results) >= 12
    summary = quality.audit_summary(results)
    assert summary["blockers"] == 0
    assert summary["errors"] == 0
    assert summary["ci_status"] == "PASSED"


def test_quality_audit_catches_duplicate_ids(df):
    tampered = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    res = quality.check_unique_loan_ids(tampered)
    assert not res.passed
    assert res.severity == "BLOCKER"


def test_quality_audit_catches_negative_amount(df):
    tampered = df.copy()
    tampered.loc[0, "loan_amount"] = -500
    res = quality.check_non_negative_amounts(tampered)
    assert not res.passed
    assert res.severity == "ERROR"


def test_quality_audit_catches_unclassified_status(df):
    tampered = df.copy()
    tampered.loc[0, "loan_status"] = "Defaulted"
    res = quality.check_loan_status_domain(tampered)
    assert not res.passed
    assert res.severity == "BLOCKER"


def test_results_to_json(df, tmp_path):
    results = quality.run_quality_audit(df)
    out_file = tmp_path / "quality.json"
    json_str = quality.results_to_json(results, out_file)
    assert out_file.exists()
    payload = json.loads(json_str)
    assert payload["summary"]["ci_status"] == "PASSED"
    assert len(payload["checks"]) == len(results)
