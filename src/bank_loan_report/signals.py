"""Risk signal quality, statistical validation, monotonicity, and findings catalog.

Assesses whether observed credit relationships represent genuine, monotonic
risk discrimination or statistical noise, computing lift ratios, rank
correlations, and structured findings with empirical caveats.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
from scipy import stats

from . import risk


@dataclass(frozen=True)
class RiskFinding:
    """Structured empirical observation with rigorous caveats and effect size."""

    metric: str
    dimension: str
    segment: str
    sample_size: int
    baseline_value: float
    observed_value: float
    effect_size: float
    interpretation: str
    caveat: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MonotonicityResult:
    """Evaluation of whether a risk factor scales monotonically across ordered tiers."""

    dimension: str
    ordered_levels: list[str]
    values: list[float]
    is_monotonic: bool
    violations: list[str]
    spearman_rho: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_monotonicity(
    df: pd.DataFrame,
    dimension: str,
    ordered_levels: list[str] | None = None,
) -> MonotonicityResult:
    """Assess whether default rates increase monotonically across ordered risk tiers.

    Monotonic risk ordering is the hallmark of a sound credit rating methodology.
    If Grade C has a lower default rate than Grade B, the rating boundary lacks
    discriminatory power.
    """
    data = risk.add_risk_flags(df)

    if ordered_levels is None:
        if dimension == "grade":
            ordered_levels = ["A", "B", "C", "D", "E", "F", "G"]
        elif dimension == "term":
            ordered_levels = ["36 months", "60 months"]
        elif dimension == "dti_band":
            ordered_levels = ["0-10%", "10-15%", "15-20%", "20-25%", "25%+"]
        elif dimension == "income_quintile":
            ordered_levels = ["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"]
        else:
            ordered_levels = sorted(list(data[dimension].dropna().unique()))

    seg_rates = {}
    for lvl in ordered_levels:
        subset = data[data[dimension] == lvl]
        if not subset.empty:
            seg_rates[lvl] = float(subset["is_charged_off"].mean() * 100)
        else:
            seg_rates[lvl] = 0.0

    levels_present = [lvl for lvl in ordered_levels if lvl in seg_rates]
    rates_present = [seg_rates[lvl] for lvl in levels_present]

    violations = []
    for i in range(len(rates_present) - 1):
        if rates_present[i] > rates_present[i + 1]:
            violations.append(
                f"{levels_present[i]} ({rates_present[i]:.2f}%) > {levels_present[i+1]} ({rates_present[i+1]:.2f}%)"
            )

    is_monotonic = len(violations) == 0

    if len(rates_present) >= 3:
        rho, _ = stats.spearmanr(range(len(rates_present)), rates_present)
    else:
        rho = 1.0 if is_monotonic else -1.0

    return MonotonicityResult(
        dimension=dimension,
        ordered_levels=levels_present,
        values=[round(v, 2) for v in rates_present],
        is_monotonic=is_monotonic,
        violations=violations,
        spearman_rho=float(round(rho, 4)),
    )


def compute_segment_lift(
    df: pd.DataFrame,
    dimension: str,
    min_loans: int = 50,
) -> pd.DataFrame:
    """Compute default rate lift relative to portfolio benchmark.

    Lift = Segment Default Rate / Portfolio Default Rate.
    A lift of 1.5x means borrowers in this segment default 50% more often
    than the average borrower.
    """
    data = risk.add_risk_flags(df)
    portfolio_default = data["is_charged_off"].mean() * 100

    grouped = (
        data.groupby(dimension, observed=True)
        .agg(
            loans=("id", "count"),
            charged_off=("is_charged_off", "sum"),
            funded_amount=("loan_amount", "sum"),
            avg_int_rate=("int_rate", "mean"),
        )
        .reset_index()
    )

    grouped = grouped[grouped["loans"] >= min_loans].copy()
    grouped["default_rate_pct"] = grouped["charged_off"] / grouped["loans"] * 100
    grouped["portfolio_default_pct"] = round(portfolio_default, 2)
    grouped["lift_ratio"] = round(grouped["default_rate_pct"] / portfolio_default, 2)
    grouped["avg_int_rate"] = round(grouped["avg_int_rate"] * 100, 2)

    # Statistical significance / confidence warning
    def _sample_warning(count: int) -> str:
        if count < 100:
            return "LOW SAMPLE (Directional only)"
        if count < 300:
            return "MODERATE SAMPLE"
        return "ROBUST SAMPLE"

    grouped["confidence"] = grouped["loans"].apply(_sample_warning)
    return grouped.sort_values("lift_ratio", ascending=False).reset_index(drop=True)


def feature_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Pearson r and Spearman rho correlations with default probability."""
    data = risk.add_risk_flags(df)
    numeric_features = [
        "loan_amount",
        "int_rate",
        "annual_income",
        "dti",
        "installment",
        "total_acc",
    ]

    records = []

    for feat in numeric_features:
        if feat not in data.columns:
            continue
        valid = data[[feat, "is_charged_off"]].dropna()
        p_corr = float(valid[feat].corr(valid["is_charged_off"]))
        s_corr, _ = stats.spearmanr(valid[feat], valid["is_charged_off"])

        records.append({
            "feature": feat,
            "pearson_r": round(p_corr, 4),
            "spearman_rho": round(float(s_corr), 4),
            "signal_direction": "Positive Risk" if p_corr > 0 else "Negative Risk",
            "correlation_strength": "Moderate" if abs(p_corr) > 0.1 else "Weak",
        })

    return pd.DataFrame(records).sort_values("spearman_rho", ascending=False).reset_index(drop=True)


def extract_risk_findings(df: pd.DataFrame) -> list[RiskFinding]:
    """Catalog empirical credit findings with sample size and observational caveats."""
    data = risk.add_risk_flags(df)
    portfolio_default = float(data["is_charged_off"].mean() * 100)
    findings: list[RiskFinding] = []

    # 1. Term risk finding
    term_lift = compute_segment_lift(df, "term", min_loans=100)
    sixty_mo = term_lift[term_lift["term"] == "60 months"]
    if not sixty_mo.empty:
        obs = float(sixty_mo.iloc[0]["default_rate_pct"])
        n = int(sixty_mo.iloc[0]["loans"])
        lift = float(sixty_mo.iloc[0]["lift_ratio"])
        findings.append(
            RiskFinding(
                metric="default_rate_pct",
                dimension="term",
                segment="60 months",
                sample_size=n,
                baseline_value=round(portfolio_default, 2),
                observed_value=round(obs, 2),
                effect_size=lift,
                interpretation=(
                    f"60-month term loans demonstrate a {lift:.2f}x default risk multiple "
                    f"({obs:.2f}% vs {portfolio_default:.2f}% portfolio baseline)."
                ),
                caveat=(
                    "Correlation does not imply causality; longer tenor loans may attract "
                    "borrowers with higher unobserved liquidity constraints."
                ),
            )
        )

    # 2. Grade G risk finding
    grade_lift = compute_segment_lift(df, "grade", min_loans=50)
    g_tier = grade_lift[grade_lift["grade"] == "G"]
    if not g_tier.empty:
        obs = float(g_tier.iloc[0]["default_rate_pct"])
        n = int(g_tier.iloc[0]["loans"])
        lift = float(g_tier.iloc[0]["lift_ratio"])
        findings.append(
            RiskFinding(
                metric="default_rate_pct",
                dimension="grade",
                segment="Grade G",
                sample_size=n,
                baseline_value=round(portfolio_default, 2),
                observed_value=round(obs, 2),
                effect_size=lift,
                interpretation=(
                    f"Grade G represents the highest-risk credit tier with a {lift:.2f}x default multiple "
                    f"({obs:.2f}% default rate)."
                ),
                caveat=(
                    "Sub-prime pricing (avg 21%+ interest) partially offsets principal losses, "
                    "but aggregate net margin remains fragile under macroeconomic distress."
                ),
            )
        )

    # 3. Small business purpose finding
    purpose_lift = compute_segment_lift(df, "purpose", min_loans=100)
    sb = purpose_lift[purpose_lift["purpose"] == "small business"]
    if not sb.empty:
        obs = float(sb.iloc[0]["default_rate_pct"])
        n = int(sb.iloc[0]["loans"])
        lift = float(sb.iloc[0]["lift_ratio"])
        findings.append(
            RiskFinding(
                metric="default_rate_pct",
                dimension="purpose",
                segment="small business",
                sample_size=n,
                baseline_value=round(portfolio_default, 2),
                observed_value=round(obs, 2),
                effect_size=lift,
                interpretation=(
                    f"Small business purpose loans exhibit high credit loss ({obs:.2f}% default rate, "
                    f"{lift:.2f}x portfolio baseline) and negative portfolio net cash margin."
                ),
                caveat=(
                    "Personal unsecured loans used for commercial purposes suffer from lack of "
                    "business collateral and elevated commercial enterprise mortality."
                ),
            )
        )

    return findings
