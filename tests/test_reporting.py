"""Tests for multi-tier reporting generation and JSON export."""

from __future__ import annotations

import pytest

from bank_loan_report import data_loader, reporting


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_executive_summary_text(df):
    text = reporting.generate_executive_summary_text(df)
    assert "EXECUTIVE CREDIT INTELLIGENCE BRIEFING" in text
    assert "Funded Capital" in text
    assert "Realized Default Rate" in text


def test_full_markdown_report(df):
    md = reporting.generate_full_markdown_report(df, include_model=True)
    assert "# Executive Credit Risk & Portfolio Intelligence Report" in md
    assert "Predictive Model Benchmarking" in md
    assert "Credit Policy Recommendations" in md


def test_export_machine_readable_json(df, tmp_path):
    paths = reporting.export_machine_readable_json(df, tmp_path, include_model=True)
    assert "data_quality" in paths
    assert "recommendations" in paths
    assert "scenarios" in paths
    assert "drift" in paths
    assert "model" in paths
