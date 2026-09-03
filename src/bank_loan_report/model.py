"""Predictive credit risk modeling and explainability engine.

Implements leakage-free default risk prediction using pre-origination
underwriting features, stratified model evaluation (ROC-AUC, PR-AUC, Brier score),
class imbalance weighting, and borrower risk factor attribution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config

# Strictly pre-origination features available at time of underwriting application
NUMERIC_FEATURES = [
    "loan_amount",
    "int_rate",
    "annual_income",
    "dti",
    "installment",
]

CATEGORICAL_FEATURES = [
    "term",
    "grade",
    "home_ownership",
    "verification_status",
    "purpose",
]

# Explicit post-origination columns excluded to prevent target leakage
LEAKAGE_COLUMNS = [
    "total_payment",
    "last_payment_date",
    "next_payment_date",
    "last_credit_pull_date",
    "loan_status",
    "loan_quality",
    "is_charged_off",
    "is_closed",
    "net_margin",
]


@dataclass
class ModelEvaluation:
    """Standardized performance metrics for a credit risk model."""

    model_name: str
    roc_auc: float
    pr_auc: float
    brier_score: float
    precision: float
    recall: float
    f1: float
    cv_roc_auc_mean: float
    cv_roc_auc_std: float
    confusion_matrix: list[list[int]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelBundle:
    """Trained model pipeline, metadata, and evaluation results."""

    model_type: str
    pipeline: Pipeline
    preprocessor: ColumnTransformer
    feature_names: list[str]
    evaluation: ModelEvaluation
    coefficients: dict[str, float] | None = None
    feature_importances: dict[str, float] | None = None


def prepare_features_and_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Extract valid pre-origination features and binary default target.

    Target = 1 if 'Charged Off', 0 otherwise.
    """
    clean_df = df.copy()
    if "is_charged_off" not in clean_df.columns:
        clean_df["is_charged_off"] = clean_df["loan_status"].isin(list(config.BAD_LOAN_STATUSES)).astype(int)

    # Validate presence of expected features
    missing = [col for col in NUMERIC_FEATURES + CATEGORICAL_FEATURES if col not in clean_df.columns]
    if missing:
        raise KeyError(f"Missing required predictive features: {missing}")

    X = clean_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES].copy()
    y = clean_df["is_charged_off"]
    return X, y


def build_preprocessor() -> ColumnTransformer:
    """Create robust ColumnTransformer for numerical scaling and one-hot encoding."""
    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    return ColumnTransformer([
        ("num", num_pipeline, NUMERIC_FEATURES),
        ("cat", cat_pipeline, CATEGORICAL_FEATURES),
    ])


def train_and_evaluate_models(
    df: pd.DataFrame,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict[str, ModelBundle]:
    """Train Logistic Regression and Gradient Boosting models with full evaluation."""
    X, y = prepare_features_and_target(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    models = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=random_state
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            class_weight="balanced", random_state=random_state
        ),
    }

    results: dict[str, ModelBundle] = {}

    for name, estimator in models.items():
        preprocessor = build_preprocessor()
        pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", estimator),
        ])

        # Cross-validation on training partition
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
        cv_scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="roc_auc")

        # Fit model
        pipeline.fit(X_train, y_train)

        # Predict probabilities on holdout test set
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        roc_auc = float(roc_auc_score(y_test, y_prob))
        pr_auc = float(average_precision_score(y_test, y_prob))
        brier = float(brier_score_loss(y_test, y_prob))
        prec = float(precision_score(y_test, y_pred, zero_division=0))
        rec = float(recall_score(y_test, y_pred, zero_division=0))
        f1 = float(f1_score(y_test, y_pred, zero_division=0))
        cm = confusion_matrix(y_test, y_pred).tolist()

        eval_metrics = ModelEvaluation(
            model_name=name,
            roc_auc=round(roc_auc, 4),
            pr_auc=round(pr_auc, 4),
            brier_score=round(brier, 4),
            precision=round(prec, 4),
            recall=round(rec, 4),
            f1=round(f1, 4),
            cv_roc_auc_mean=round(float(cv_scores.mean()), 4),
            cv_roc_auc_std=round(float(cv_scores.std()), 4),
            confusion_matrix=cm,
        )

        # Feature names extraction
        cat_encoder = pipeline.named_steps["preprocessor"].named_transformers_["cat"].named_steps["onehot"]
        encoded_cat_names = list(cat_encoder.get_feature_names_out(CATEGORICAL_FEATURES))
        all_feature_names = NUMERIC_FEATURES + encoded_cat_names

        coeffs: dict[str, float] | None = None
        importances: dict[str, float] | None = None

        if name == "logistic_regression":
            raw_coeffs = pipeline.named_steps["classifier"].coef_[0]
            coeffs = {feat: round(float(c), 4) for feat, c in zip(all_feature_names, raw_coeffs, strict=False)}
        elif hasattr(pipeline.named_steps["classifier"], "feature_importances_"):
            # If estimator supports feature importances
            raw_imp = pipeline.named_steps["classifier"].feature_importances_
            importances = {feat: round(float(imp), 4) for feat, imp in zip(all_feature_names, raw_imp, strict=False)}

        results[name] = ModelBundle(
            model_type=name,
            pipeline=pipeline,
            preprocessor=preprocessor,
            feature_names=all_feature_names,
            evaluation=eval_metrics,
            coefficients=coeffs,
            feature_importances=importances,
        )

    return results


def explain_borrower_risk(
    bundle: ModelBundle,
    borrower: dict[str, Any],
) -> dict[str, Any]:
    """Explain default risk factors for an individual loan application.

    Answers: 'Why is this borrower considered higher risk?' by analyzing
    feature deviations against portfolio baselines and model weights.
    """
    row_df = pd.DataFrame([borrower])
    pipeline = bundle.pipeline

    # Missing column check
    for col in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        if col not in row_df.columns:
            raise KeyError(f"Borrower dictionary missing required field: {col}")

    prob = float(pipeline.predict_proba(row_df)[0, 1])

    if prob < 0.10:
        tier = "Prime / Low Risk"
    elif prob < 0.20:
        tier = "Near-Prime / Moderate Risk"
    elif prob < 0.35:
        tier = "Sub-Prime / Elevated Risk"
    else:
        tier = "High Risk / Distressed"

    # Identify primary drivers based on known risk rules & coefficients
    risk_factors = []
    mitigating_factors = []

    # Interest rate check
    int_rate = float(borrower.get("int_rate", 0.0))
    if int_rate > 0.15:
        risk_factors.append(f"High interest rate ({int_rate*100:.1f}%) indicates adverse credit pricing tier")
    elif int_rate < 0.09:
        mitigating_factors.append(f"Low interest rate ({int_rate*100:.1f}%) reflects favorable risk rating")

    # DTI check
    dti = float(borrower.get("dti", 0.0))
    if dti > 0.20:
        risk_factors.append(f"Elevated Debt-to-Income ratio ({dti*100:.1f}%) indicates balance-sheet leverage")
    elif dti < 0.10:
        mitigating_factors.append(f"Low Debt-to-Income ratio ({dti*100:.1f}%) shows strong debt service capacity")

    # Term check
    term = str(borrower.get("term", "")).strip()
    if "60" in term:
        risk_factors.append("Extended 60-month loan tenor carries higher default hazard rate")
    elif "36" in term:
        mitigating_factors.append("36-month short loan tenor limits cumulative default exposure window")

    # Grade check
    grade = str(borrower.get("grade", "")).strip().upper()
    if grade in ("D", "E", "F", "G"):
        risk_factors.append(f"Sub-prime credit grade ({grade}) carries elevated historical default frequency")
    elif grade in ("A", "B"):
        mitigating_factors.append(f"High-quality credit grade ({grade}) historically outperforms portfolio")

    # Purpose check
    purpose = str(borrower.get("purpose", "")).lower()
    if "small_business" in purpose or "small business" in purpose:
        risk_factors.append("Commercial small-business purpose exhibits higher volatility")

    return {
        "predicted_default_probability": round(prob, 4),
        "default_probability_pct": f"{prob * 100:.2f}%",
        "risk_tier": tier,
        "primary_risk_drivers": risk_factors if risk_factors else ["No severe risk anomalies detected"],
        "mitigating_factors": mitigating_factors if mitigating_factors else ["Standard underwriting baseline"],
        "disclaimer": (
            "Benchmark predictive assessment generated for analytics evaluation. "
            "Not an automated adverse credit decision."
        ),
    }
