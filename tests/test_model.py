"""Tests for predictive credit risk models and explainability."""

from __future__ import annotations

import pytest

from bank_loan_report import data_loader, model


@pytest.fixture(scope="module")
def df():
    return data_loader.load_loans(use_sample=True)


def test_target_leakage_prevention(df):
    X, y = model.prepare_features_and_target(df)
    for leak in model.LEAKAGE_COLUMNS:
        assert leak not in X.columns
    assert set(y.unique()) <= {0, 1}


def test_model_training_and_evaluation(df):
    models = model.train_and_evaluate_models(df, test_size=0.25, random_state=42)
    assert "logistic_regression" in models
    assert "hist_gradient_boosting" in models

    lr = models["logistic_regression"]
    assert lr.evaluation.roc_auc > 0.60
    assert lr.evaluation.pr_auc > 0.10
    assert lr.evaluation.brier_score < 0.35
    assert len(lr.feature_names) > 0


def test_borrower_explainability(df):
    models = model.train_and_evaluate_models(df, test_size=0.25, random_state=42)
    sample_borrower = {
        "loan_amount": 10000,
        "int_rate": 0.12,
        "annual_income": 60000,
        "dti": 0.15,
        "installment": 300.0,
        "term": "36 months",
        "grade": "B",
        "home_ownership": "RENT",
        "verification_status": "Not Verified",
        "purpose": "debt_consolidation",
    }
    explanation = model.explain_borrower_risk(models["logistic_regression"], sample_borrower)
    assert "predicted_default_probability" in explanation
    assert "risk_tier" in explanation
    assert len(explanation["primary_risk_drivers"]) > 0
    assert len(explanation["mitigating_factors"]) > 0
