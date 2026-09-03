"""Analytical cohort monitoring and feature drift detection engine.

Compares temporal portfolio cohorts (e.g. H1 vs H2) to quantify distribution
drift, Population Stability Index (PSI), missingness drift, and credit quality shifts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from . import risk

DriftSeverity = Literal["STABLE", "WARNING", "ALERT"]


@dataclass(frozen=True)
class DriftMetric:
    """Quantitative measurement of drift between baseline and current cohorts."""

    metric: str
    dimension: str
    baseline: float
    current: float
    abs_change: float
    rel_change_pct: float
    severity: DriftSeverity
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_psi(
    expected_dist: pd.Series,
    actual_dist: pd.Series,
    epsilon: float = 1e-4,
) -> float:
    """Calculate Population Stability Index (PSI) between two probability distributions.

    PSI = sum((Actual - Expected) * ln(Actual / Expected)).
    Thresholds:
    - PSI < 0.10: Stable / Insignificant Drift
    - 0.10 <= PSI < 0.25: Moderate Drift (Monitor)
    - PSI >= 0.25: Significant Drift (Action Required)
    """
    all_categories = sorted(list(set(expected_dist.index) | set(actual_dist.index)))
    exp = expected_dist.reindex(all_categories, fill_value=0.0) + epsilon
    act = actual_dist.reindex(all_categories, fill_value=0.0) + epsilon

    exp_norm = exp / exp.sum()
    act_norm = act / act.sum()

    psi_val = ((act_norm - exp_norm) * np.log(act_norm / exp_norm)).sum()
    return float(round(psi_val, 4))


def compute_portfolio_drift(
    df: pd.DataFrame,
    split_month: int = 7,
) -> list[DriftMetric]:
    """Compare baseline cohort (issue_month < split_month) vs current cohort (issue_month >= split_month)."""
    data = risk.add_risk_flags(df)

    baseline_df = data[data["issue_month"] < split_month]
    current_df = data[data["issue_month"] >= split_month]

    if baseline_df.empty or current_df.empty:
        return []

    metrics: list[DriftMetric] = []

    # 1. Volume Drift
    b_vol = len(baseline_df)
    c_vol = len(current_df)
    v_abs = c_vol - b_vol
    v_rel = (v_abs / b_vol * 100) if b_vol else 0.0
    metrics.append(
        DriftMetric(
            metric="origination_volume",
            dimension="portfolio",
            baseline=float(b_vol),
            current=float(c_vol),
            abs_change=float(v_abs),
            rel_change_pct=round(v_rel, 2),
            severity="WARNING" if abs(v_rel) > 25 else "STABLE",
            interpretation=f"Origination volume shifted by {v_rel:+.1f}% across cohorts.",
        )
    )

    # 2. Funded Exposure Drift
    b_fund = float(baseline_df["loan_amount"].sum())
    c_fund = float(current_df["loan_amount"].sum())
    f_rel = ((c_fund - b_fund) / b_fund * 100) if b_fund else 0.0
    metrics.append(
        DriftMetric(
            metric="funded_capital_usd",
            dimension="portfolio",
            baseline=round(b_fund, 2),
            current=round(c_fund, 2),
            abs_change=round(c_fund - b_fund, 2),
            rel_change_pct=round(f_rel, 2),
            severity="WARNING" if abs(f_rel) > 25 else "STABLE",
            interpretation=f"Capital deployed shifted by {f_rel:+.1f}%.",
        )
    )

    # 3. Default Rate Drift
    b_def = float(baseline_df["is_charged_off"].mean() * 100)
    c_def = float(current_df["is_charged_off"].mean() * 100)
    def_abs = c_def - b_def
    def_rel = (def_abs / b_def * 100) if b_def else 0.0
    def_sev: DriftSeverity = "STABLE"
    if abs(def_abs) >= 3.0:
        def_sev = "ALERT"
    elif abs(def_abs) >= 1.5:
        def_sev = "WARNING"

    metrics.append(
        DriftMetric(
            metric="default_rate_pct",
            dimension="credit_quality",
            baseline=round(b_def, 2),
            current=round(c_def, 2),
            abs_change=round(def_abs, 2),
            rel_change_pct=round(def_rel, 2),
            severity=def_sev,
            interpretation=f"Realized default rate changed by {def_abs:+.2f} percentage points.",
        )
    )

    # 4. Interest Rate Drift
    b_rate = float(baseline_df["int_rate"].mean() * 100)
    c_rate = float(current_df["int_rate"].mean() * 100)
    rate_diff = c_rate - b_rate
    metrics.append(
        DriftMetric(
            metric="avg_interest_rate_pct",
            dimension="pricing",
            baseline=round(b_rate, 2),
            current=round(c_rate, 2),
            abs_change=round(rate_diff, 2),
            rel_change_pct=round((rate_diff / b_rate * 100) if b_rate else 0.0, 2),
            severity="WARNING" if abs(rate_diff) > 1.0 else "STABLE",
            interpretation=f"Weighted average coupon changed by {rate_diff:+.2f} pp.",
        )
    )

    # 5. DTI Drift
    b_dti = float(baseline_df["dti"].mean() * 100)
    c_dti = float(current_df["dti"].mean() * 100)
    dti_diff = c_dti - b_dti
    metrics.append(
        DriftMetric(
            metric="avg_dti_pct",
            dimension="underwriting",
            baseline=round(b_dti, 2),
            current=round(c_dti, 2),
            abs_change=round(dti_diff, 2),
            rel_change_pct=round((dti_diff / b_dti * 100) if b_dti else 0.0, 2),
            severity="WARNING" if abs(dti_diff) > 1.5 else "STABLE",
            interpretation=f"Average borrower DTI shifted by {dti_diff:+.2f} pp.",
        )
    )

    # 6. Credit Grade Population Stability Index (PSI)
    b_grades = baseline_df["grade"].value_counts(normalize=True)
    c_grades = current_df["grade"].value_counts(normalize=True)
    grade_psi = calculate_psi(b_grades, c_grades)
    psi_sev: DriftSeverity = "STABLE"
    if grade_psi >= 0.25:
        psi_sev = "ALERT"
    elif grade_psi >= 0.10:
        psi_sev = "WARNING"

    metrics.append(
        DriftMetric(
            metric="grade_distribution_psi",
            dimension="population_stability",
            baseline=0.0,
            current=grade_psi,
            abs_change=grade_psi,
            rel_change_pct=0.0,
            severity=psi_sev,
            interpretation=(
                f"Credit grade distribution PSI is {grade_psi:.4f} ({psi_sev}). "
                "Values below 0.10 indicate population stability."
            ),
        )
    )

    # 7. Term Mix Drift (60-Month Share)
    b_sixty = float((baseline_df["term"] == "60 months").mean() * 100)
    c_sixty = float((current_df["term"] == "60 months").mean() * 100)
    sixty_diff = c_sixty - b_sixty
    metrics.append(
        DriftMetric(
            metric="sixty_month_term_share_pct",
            dimension="product_mix",
            baseline=round(b_sixty, 2),
            current=round(c_sixty, 2),
            abs_change=round(sixty_diff, 2),
            rel_change_pct=round((sixty_diff / b_sixty * 100) if b_sixty else 0.0, 2),
            severity="WARNING" if abs(sixty_diff) > 5.0 else "STABLE",
            interpretation=f"60-month loan share changed by {sixty_diff:+.2f} pp.",
        )
    )

    return metrics


def drift_to_dataframe(metrics: list[DriftMetric]) -> pd.DataFrame:
    """Convert drift metrics list into a displayable DataFrame."""
    return pd.DataFrame([m.to_dict() for m in metrics])
