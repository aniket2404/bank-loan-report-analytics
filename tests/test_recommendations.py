"""Tests for deterministic credit policy recommendations."""

from __future__ import annotations

import pytest

from bank_loan_report import data_loader, recommendations


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_generate_recommendations(df):
    recs = recommendations.generate_recommendations(df)
    assert isinstance(recs, list)
    for r in recs:
        assert r.action in ("TIGHTEN", "REPRICE", "MONITOR", "MAINTAIN", "INVESTIGATE", "REVIEW")
        assert r.confidence in ("HIGH", "MEDIUM", "LOW")
        assert len(r.rationale) > 0
        assert len(r.caveat) > 0
