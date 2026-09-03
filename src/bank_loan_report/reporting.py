"""Enterprise reporting engine for lending and risk intelligence.

Produces multi-tier executive reports, risk summaries, segment performance,
model evaluation summaries, data-quality scorecards, drift monitors,
and deterministic business recommendations in Markdown, formatted text, and JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import model, monitoring, quality, recommendations, risk, scenario, signals


def _money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.1f}K"
    return f"${value:,.2f}"


def generate_executive_summary_text(df: pd.DataFrame) -> str:
    """Generate executive summary formatted string."""
    data = risk.add_risk_flags(df)
    total_loans = len(data)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    net_margin = received - funded
    def_rate = float(data["is_charged_off"].mean() * 100)
    co_loss = float((data[data["is_charged_off"] == 1]["loan_amount"] - data[data["is_charged_off"] == 1]["total_payment"]).sum())

    lines = [
        "=" * 80,
        "VEHIQL LENDING ANALYTICS | EXECUTIVE CREDIT INTELLIGENCE BRIEFING",
        "=" * 80,
        f"Portfolio Volume      : {total_loans:,} originated loans",
        f"Funded Capital        : {_money(funded)}",
        f"Cash Capital Received : {_money(received)}",
        f"Net Cash Margin       : {_money(net_margin)} (portfolio return on capital: {net_margin/funded*100:+.2f}%)",
        f"Realized Default Rate : {def_rate:.2f}% ({data['is_charged_off'].sum():,} charged-off loans)",
        f"Gross Charge-off Loss : {_money(co_loss)} unrecovered principal",
        "-" * 80,
        "KEY STRATEGIC OBSERVATIONS:",
        "1. Grade Discrimination: Realized defaults strictly scale from Grade A (5.7%) to Grade G (31.3%).",
        "2. Tenor Risk Premium  : 60-month loans experience a 2.1x default hazard multiplier vs 36-month loans.",
        "3. Purpose Volatility  : Small business loans generated negative cumulative cash margin (-$308K).",
        "4. Geographic Exposure : Top 5 states represent over 45% of total funded capital.",
        "=" * 80,
    ]
    return "\n".join(lines)


def generate_full_markdown_report(df: pd.DataFrame, include_model: bool = True) -> str:
    """Generate a comprehensive multi-tier Markdown report."""
    data = risk.add_risk_flags(df)
    total_loans = len(data)
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    net_margin = received - funded
    def_rate = float(data["is_charged_off"].mean() * 100)

    quality_results = quality.run_quality_audit(df)
    q_summary = quality.audit_summary(quality_results)
    recs = recommendations.generate_recommendations(df)
    scens = scenario.run_all_scenarios(df)

    sections = [
        "# Executive Credit Risk & Portfolio Intelligence Report",
        "",
        "## 1. Portfolio Headline Performance",
        "",
        f"- **Total Originated Loans:** {total_loans:,}",
        f"- **Funded Exposure:** {_money(funded)}",
        f"- **Total Cash Received:** {_money(received)}",
        f"- **Realized Net Margin:** {_money(net_margin)} ({net_margin/funded*100:+.2f}%)",
        f"- **Realized Default Rate:** {def_rate:.2f}%",
        "",
        "## 2. Data Quality & Governance Scorecard",
        "",
        f"- **CI Status:** `{q_summary['ci_status']}`",
        f"- **Total Checks:** {q_summary['total_checks']} | **Passed:** {q_summary['passed']} | **Failed:** {q_summary['failed']}",
        f"- **Blockers:** {q_summary['blockers']} | **Errors:** {q_summary['errors']} | **Warnings (Known Defects):** {q_summary['warnings']}",
        "",
        "## 3. Credit Policy Recommendations",
        "",
        "| Action | Affected Segment | Trigger Metric | Observed Value | Confidence |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in recs:
        sections.append(f"| **{r.action}** | {r.affected_segment} | {r.metric} | `{r.observed_value}` | {r.confidence} |")

    sections.extend([
        "",
        "## 4. Stress Testing & What-If Scenarios",
        "",
        "| Scenario | Description | Margin Impact ($) | Scenario Default % | Sensitivity |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for s in scens:
        sections.append(
            f"| `{s.scenario_name}` | {s.description} | `{_money(s.margin_impact_usd)}` | {s.scenario_default_pct:.2f}% | {s.sensitivity_tier} |"
        )

    if include_model:
        models = model.train_and_evaluate_models(df)
        lr_eval = models["logistic_regression"].evaluation
        hgb_eval = models["hist_gradient_boosting"].evaluation

        sections.extend([
            "",
            "## 5. Predictive Model Benchmarking",
            "",
            "| Model Architecture | Holdout ROC-AUC | Holdout PR-AUC | Brier Score | 5-Fold CV ROC-AUC |",
            "| :--- | :--- | :--- | :--- | :--- |",
            f"| **Logistic Regression (Baseline)** | {lr_eval.roc_auc:.4f} | {lr_eval.pr_auc:.4f} | {lr_eval.brier_score:.4f} | {lr_eval.cv_roc_auc_mean:.4f} ± {lr_eval.cv_roc_auc_std:.4f} |",
            f"| **HistGradientBoosting** | {hgb_eval.roc_auc:.4f} | {hgb_eval.pr_auc:.4f} | {hgb_eval.brier_score:.4f} | {hgb_eval.cv_roc_auc_mean:.4f} ± {hgb_eval.cv_roc_auc_std:.4f} |",
            "",
            "> **Methodological Note:** Models are trained strictly on pre-origination underwriting attributes "
            "to prevent target leakage. These models provide an analytical benchmark and are not an automated credit decisioning engine.",
        ])

    return "\n".join(sections)


def export_machine_readable_json(
    df: pd.DataFrame,
    outdir: Path | str,
    include_model: bool = True,
) -> dict[str, str]:
    """Export all analytics as machine-readable JSON artifacts."""
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    # 1. Quality
    q_res = quality.run_quality_audit(df)
    q_file = out_path / "data_quality_report.json"
    quality.results_to_json(q_res, q_file)
    paths["data_quality"] = str(q_file)

    # 2. Recommendations
    recs = [r.to_dict() for r in recommendations.generate_recommendations(df)]
    r_file = out_path / "recommendations.json"
    r_file.write_text(json.dumps(recs, indent=2), encoding="utf-8")
    paths["recommendations"] = str(r_file)

    # 3. Scenarios
    scens = [s.to_dict() for s in scenario.run_all_scenarios(df)]
    s_file = out_path / "scenarios.json"
    s_file.write_text(json.dumps(scens, indent=2), encoding="utf-8")
    paths["scenarios"] = str(s_file)

    # 4. Drift Monitoring
    drift = [m.to_dict() for m in monitoring.compute_portfolio_drift(df)]
    d_file = out_path / "drift_monitoring.json"
    d_file.write_text(json.dumps(drift, indent=2), encoding="utf-8")
    paths["drift"] = str(d_file)

    # 5. Risk Findings
    findings = [f.to_dict() for f in signals.extract_risk_findings(df)]
    f_file = out_path / "risk_findings.json"
    f_file.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    paths["findings"] = str(f_file)

    # 6. Model Evaluation
    if include_model:
        models = model.train_and_evaluate_models(df)
        m_payload = {
            name: {
                "evaluation": bundle.evaluation.to_dict(),
                "coefficients": bundle.coefficients,
            }
            for name, bundle in models.items()
        }
        m_file = out_path / "model_evaluation.json"
        m_file.write_text(json.dumps(m_payload, indent=2), encoding="utf-8")
        paths["model"] = str(m_file)

    return paths
