"""Unit tests for schema contracts and domain definitions."""

from __future__ import annotations

from bank_loan_report import schema


def test_schema_column_counts():
    assert len(schema.SOURCE_COLUMNS) == 24
    assert len(schema.DERIVED_COLUMNS) == 5
    assert len(schema.DATE_COLUMNS) == 4
    assert len(schema.NUMERIC_COLUMNS) == 7
    assert len(schema.CATEGORICAL_COLUMNS) == 10


def test_allowed_domains():
    assert "36 months" in schema.VALID_TERMS
    assert "60 months" in schema.VALID_TERMS
    assert set("ABCDEFG") == schema.VALID_GRADES
    assert len(schema.VALID_SUBGRADES) == 35
    assert schema.VALID_LOAN_STATUSES == {"Fully Paid", "Current", "Charged Off"}


def test_numeric_bounds():
    assert schema.NUMERIC_BOUNDS["loan_amount"]["min"] > 0
    assert schema.NUMERIC_BOUNDS["int_rate"]["max"] <= 1.0
    assert schema.NUMERIC_BOUNDS["dti"]["max"] <= 1.5
