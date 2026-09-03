"""Stress testing and scenario simulation engine for portfolio credit risk.

Simulates macroeconomic shocks, recovery haircuts, underwriting tightening,
and product mix shifts to quantify capital sensitivity and incremental expected loss.
All results are explicitly designated as hypothetical analytical projections.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from . import risk


@dataclass(frozen=True)
class ScenarioOutcome:
    """Quantitative impact of a hypothetical stress test scenario."""

    scenario_name: str
    description: str
    baseline_funded: float
    scenario_funded: float
    baseline_received: float
    scenario_received: float
    baseline_net_margin: float
    scenario_net_margin: float
    margin_impact_usd: float
    baseline_default_pct: float
    scenario_default_pct: float
    expected_loss_proxy_usd: float
    sensitivity_tier: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scenario_default_rate_shock(
    df: pd.DataFrame,
    shock_rel_pct: float = 25.0,
) -> ScenarioOutcome:
    """Simulate a relative increase in default rate (e.g. +25% default surge)."""
    data = risk.add_risk_flags(df)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    base_margin = received - funded

    base_def_rate = float(data["is_charged_off"].mean() * 100)
    new_def_rate = base_def_rate * (1 + shock_rel_pct / 100)

    # In charged-off loans, the average loss is loan_amount - total_payment
    co_loans = data[data["is_charged_off"] == 1]
    avg_co_loss = float((co_loans["loan_amount"] - co_loans["total_payment"]).mean()) if not co_loans.empty else 0.0

    current_co_count = len(co_loans)
    incremental_co_count = int(current_co_count * (shock_rel_pct / 100))
    incremental_loss = incremental_co_count * avg_co_loss

    scen_received = received - incremental_loss
    scen_margin = scen_received - funded

    return ScenarioOutcome(
        scenario_name="default_rate_shock_25pct",
        description=f"Macroeconomic downturn: {shock_rel_pct:.0f}% relative surge in charged-off loans.",
        baseline_funded=round(funded, 2),
        scenario_funded=round(funded, 2),
        baseline_received=round(received, 2),
        scenario_received=round(scen_received, 2),
        baseline_net_margin=round(base_margin, 2),
        scenario_net_margin=round(scen_margin, 2),
        margin_impact_usd=round(-incremental_loss, 2),
        baseline_default_pct=round(base_def_rate, 2),
        scenario_default_pct=round(new_def_rate, 2),
        expected_loss_proxy_usd=round(incremental_loss, 2),
        sensitivity_tier="Elevated" if incremental_loss > 5_000_000 else "Moderate",
    )


def scenario_recovery_haircut(
    df: pd.DataFrame,
    haircut_pct: float = 30.0,
) -> ScenarioOutcome:
    """Simulate a haircut in salvage recovery cash on defaulted loans."""
    data = risk.add_risk_flags(df)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    base_margin = received - funded

    base_def_rate = float(data["is_charged_off"].mean() * 100)
    co_received = float(data[data["is_charged_off"] == 1]["total_payment"].sum())
    lost_recovery = co_received * (haircut_pct / 100)

    scen_received = received - lost_recovery
    scen_margin = scen_received - funded

    return ScenarioOutcome(
        scenario_name="recovery_haircut_30pct",
        description=f"Secondary debt collection distress: {haircut_pct:.0f}% haircut on salvage recovery.",
        baseline_funded=round(funded, 2),
        scenario_funded=round(funded, 2),
        baseline_received=round(received, 2),
        scenario_received=round(scen_received, 2),
        baseline_net_margin=round(base_margin, 2),
        scenario_net_margin=round(scen_margin, 2),
        margin_impact_usd=round(-lost_recovery, 2),
        baseline_default_pct=round(base_def_rate, 2),
        scenario_default_pct=round(base_def_rate, 2),
        expected_loss_proxy_usd=round(lost_recovery, 2),
        sensitivity_tier="Moderate",
    )


def scenario_underwriting_tightening(
    df: pd.DataFrame,
    excluded_grades: tuple[str, ...] = ("F", "G"),
) -> ScenarioOutcome:
    """Simulate policy exclusion of high-loss credit grades F and G."""
    data = risk.add_risk_flags(df)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    base_margin = received - funded
    base_def_rate = float(data["is_charged_off"].mean() * 100)

    retained = data[~data["grade"].isin(excluded_grades)]
    scen_funded = float(retained["loan_amount"].sum())
    scen_received = float(retained["total_payment"].sum())
    scen_margin = scen_received - scen_funded
    scen_def_rate = float(retained["is_charged_off"].mean() * 100)
    margin_diff = scen_margin - base_margin

    return ScenarioOutcome(
        scenario_name="exclude_grades_f_g",
        description=f"Tighten risk policy: Eliminate underwriting of Grades {', '.join(excluded_grades)}.",
        baseline_funded=round(funded, 2),
        scenario_funded=round(scen_funded, 2),
        baseline_received=round(received, 2),
        scenario_received=round(scen_received, 2),
        baseline_net_margin=round(base_margin, 2),
        scenario_net_margin=round(scen_margin, 2),
        margin_impact_usd=round(margin_diff, 2),
        baseline_default_pct=round(base_def_rate, 2),
        scenario_default_pct=round(scen_def_rate, 2),
        expected_loss_proxy_usd=round(abs(margin_diff), 2),
        sensitivity_tier="High Strategic Impact",
    )


def scenario_macro_crisis(
    df: pd.DataFrame,
) -> ScenarioOutcome:
    """Simulate severe combined crisis: +40% default surge with 25% recovery reduction."""
    data = risk.add_risk_flags(df)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    base_margin = received - funded
    base_def_rate = float(data["is_charged_off"].mean() * 100)

    co_loans = data[data["is_charged_off"] == 1]
    avg_co_loss = float((co_loans["loan_amount"] - co_loans["total_payment"]).mean()) if not co_loans.empty else 0.0
    incremental_co_loss = int(len(co_loans) * 0.40) * avg_co_loss

    co_salvage = float(co_loans["total_payment"].sum())
    recovery_haircut = co_salvage * 0.25

    total_loss_impact = incremental_co_loss + recovery_haircut
    scen_received = received - total_loss_impact
    scen_margin = scen_received - funded

    return ScenarioOutcome(
        scenario_name="severe_macro_crisis",
        description="Severe stagflation: +40% default spike combined with 25% salvage haircut.",
        baseline_funded=round(funded, 2),
        scenario_funded=round(funded, 2),
        baseline_received=round(received, 2),
        scenario_received=round(scen_received, 2),
        baseline_net_margin=round(base_margin, 2),
        scenario_net_margin=round(scen_margin, 2),
        margin_impact_usd=round(-total_loss_impact, 2),
        baseline_default_pct=round(base_def_rate, 2),
        scenario_default_pct=round(base_def_rate * 1.40, 2),
        expected_loss_proxy_usd=round(total_loss_impact, 2),
        sensitivity_tier="Severe Capital Erosion",
    )


def run_all_scenarios(df: pd.DataFrame) -> list[ScenarioOutcome]:
    """Execute standard suite of credit risk stress tests."""
    return [
        scenario_default_rate_shock(df, 25.0),
        scenario_recovery_haircut(df, 30.0),
        scenario_underwriting_tightening(df, ("F", "G")),
        scenario_macro_crisis(df),
    ]


def scenarios_to_dataframe(outcomes: list[ScenarioOutcome]) -> pd.DataFrame:
    """Convert stress test outcomes into a displayable summary table."""
    return pd.DataFrame([s.to_dict() for s in outcomes])
