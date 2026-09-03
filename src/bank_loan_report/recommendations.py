"""Deterministic portfolio policy recommendation engine.

Translates empirical credit analytics into actionable, rules-based business
directives (TIGHTEN, REPRICE, MONITOR, MAINTAIN, INVESTIGATE) with explicit
thresholds, rationale, and governance caveats.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

from . import risk

ActionType = Literal["TIGHTEN", "REPRICE", "MONITOR", "MAINTAIN", "INVESTIGATE", "REVIEW"]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class Recommendation:
    """Actionable credit policy directive derived deterministically from portfolio metrics."""

    action: ActionType
    trigger: str
    metric: str
    observed_value: Any
    threshold: Any
    affected_segment: str
    rationale: str
    confidence: ConfidenceLevel
    caveat: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_recommendations(df: pd.DataFrame) -> list[Recommendation]:
    """Execute deterministic credit policy rulebook against portfolio data."""
    data = risk.add_risk_flags(df)
    portfolio_default = float(data["is_charged_off"].mean() * 100)
    funded_total = float(data["loan_amount"].sum())
    recs: list[Recommendation] = []

    # Rule 1: Loss-Making Purpose Segments (Net Margin < 0)
    losers = risk.unprofitable_segments(df, "purpose", min_loans=50)
    for row in losers.itertuples():
        recs.append(
            Recommendation(
                action="REPRICE",
                trigger="Negative cumulative net cash margin (total payments < principal lent)",
                metric="net_margin_usd",
                observed_value=f"${row.net_margin:,.2f}",
                threshold="< $0.00",
                affected_segment=f"Purpose: {row.purpose}",
                rationale=(
                    f"Borrowers for '{row.purpose}' have consumed more capital than they returned, "
                    f"generating a net cash loss of ${abs(row.net_margin):,.2f} at a {row.default_rate_pct:.2f}% default rate. "
                    "Interest coupons fail to clear realized charge-offs."
                ),
                confidence="HIGH",
                caveat="Ensure pricing adjustments comply with regulatory usury caps.",
            )
        )

    # Rule 2: Sub-Prime Grade Risk Outliers (Default Rate > 25% with significant volume)
    grades = risk.segment_risk(df, "grade", min_loans=100)
    high_risk_grades = grades[grades["default_rate_pct"] >= 25.0]
    for row in high_risk_grades.itertuples():
        recs.append(
            Recommendation(
                action="TIGHTEN",
                trigger="Excessive default rate exceeding 25.0% threshold",
                metric="default_rate_pct",
                observed_value=f"{row.default_rate_pct:.2f}%",
                threshold=">= 25.0%",
                affected_segment=f"Credit Grade: {row.grade}",
                rationale=(
                    f"Grade {row.grade} default rate is {row.default_rate_pct:.2f}% "
                    f"({row.default_rate_pct / portfolio_default:.2f}x portfolio baseline). "
                    "Tighten debt-to-income and minimum credit score cutoffs to curtail non-performing inflows."
                ),
                confidence="HIGH",
                caveat="Drastic volume cuts reduce headline interest revenue.",
            )
        )

    # Rule 3: 60-Month Tenor Hazard Multiple
    terms = risk.segment_risk(df, "term", min_loans=100)
    sixty_mo = terms[terms["term"] == "60 months"]
    if not sixty_mo.empty:
        sixty_def = float(sixty_mo.iloc[0]["default_rate_pct"])
        thirty_six = terms[terms["term"] == "36 months"]
        thirty_def = float(thirty_six.iloc[0]["default_rate_pct"]) if not thirty_six.empty else 0.0

        if sixty_def >= 20.0:
            recs.append(
                Recommendation(
                    action="REVIEW",
                    trigger="60-month loan default rate exceeds 20.0%",
                    metric="default_rate_pct",
                    observed_value=f"{sixty_def:.2f}% vs {thirty_def:.2f}% (36m)",
                    threshold=">= 20.0%",
                    affected_segment="Loan Term: 60 months",
                    rationale=(
                        f"60-month loans suffer a {sixty_def:.2f}% default rate, over double "
                        f"the 36-month tenor ({thirty_def:.2f}%). Longer loan durations extend "
                        "borrower hazard exposure without proportional credit spread compensation."
                    ),
                    confidence="HIGH",
                    caveat="Review whether prepayment speed biases survival estimates.",
                )
            )

    # Rule 4: Prime Portfolio Retention & Expansion (Grade A)
    grade_a = grades[grades["grade"] == "A"]
    if not grade_a.empty:
        a_def = float(grade_a.iloc[0]["default_rate_pct"])
        if a_def <= 7.0:
            recs.append(
                Recommendation(
                    action="MAINTAIN",
                    trigger="Super-prime credit quality with default rate < 7.0%",
                    metric="default_rate_pct",
                    observed_value=f"{a_def:.2f}%",
                    threshold="<= 7.0%",
                    affected_segment="Credit Grade: A",
                    rationale=(
                        f"Grade A represents prime underwriting stability with a {a_def:.2f}% default rate "
                        "and reliable cash collection. Maintain current risk parameters and explore expansion."
                    ),
                    confidence="HIGH",
                    caveat="Monitor competitor pricing compression in prime tiers.",
                )
            )

    # Rule 5: Geographic Concentration Risk (State Share > 15%)
    states = df.groupby("address_state", observed=True)["loan_amount"].sum() / funded_total * 100
    top_state = states.idxmax()
    top_share = float(states.max())
    if top_share >= 15.0:
        recs.append(
            Recommendation(
                action="MONITOR",
                trigger="Single state concentration exceeds 15.0% of total funded book",
                metric="state_funded_share_pct",
                observed_value=f"{top_share:.2f}%",
                threshold=">= 15.0%",
                affected_segment=f"Geographic State: {top_state}",
                rationale=(
                    f"State '{top_state}' accounts for {top_share:.2f}% of total funded capital. "
                    "Macroeconomic shocks, real estate swings, or regional job losses will heavily impact overall book."
                ),
                confidence="MEDIUM",
                caveat="Regional economic diversification is limited by population demographics.",
            )
        )

    # Rule 6: High-DTI Band Vigilance (DTI 25%+)
    dti_seg = risk.segment_risk(data, "dti_band", min_loans=100)
    high_dti = dti_seg[dti_seg["dti_band"] == "25%+"]
    if not high_dti.empty:
        high_dti_def = float(high_dti.iloc[0]["default_rate_pct"])
        if high_dti_def > portfolio_default * 1.15:
            recs.append(
                Recommendation(
                    action="INVESTIGATE",
                    trigger="Elevated DTI tier exhibits > 15% default premium over portfolio baseline",
                    metric="default_rate_pct",
                    observed_value=f"{high_dti_def:.2f}% vs {portfolio_default:.2f}%",
                    threshold="> 1.15x baseline",
                    affected_segment="DTI Band: 25%+",
                    rationale=(
                        f"Borrowers carrying DTI ratios above 25% demonstrate elevated credit stress "
                        f"({high_dti_def:.2f}% default rate). Investigate whether secondary income verification "
                        "or installment-to-income caps are required."
                    ),
                    confidence="MEDIUM",
                    caveat="Self-reported DTI may understate external unsecured debt obligations.",
                )
            )

    return recs


def recommendations_to_dataframe(recs: list[Recommendation]) -> pd.DataFrame:
    """Convert recommendation objects into a displayable summary DataFrame."""
    return pd.DataFrame([r.to_dict() for r in recs])
