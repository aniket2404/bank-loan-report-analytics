"""Command line interface for the Bank Loan & Credit Risk Analytics Platform.

Examples
--------
    python -m bank_loan_report report
    python -m bank_loan_report report --sample
    python -m bank_loan_report quality
    python -m bank_loan_report validate
    python -m bank_loan_report insights
    python -m bank_loan_report risk
    python -m bank_loan_report model
    python -m bank_loan_report monitor
    python -m bank_loan_report scenario
    python -m bank_loan_report recommendations
    python -m bank_loan_report charts --outdir reports/figures
    python -m bank_loan_report export --outdir reports/tables
    python -m bank_loan_report all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import (
    charts,
    config,
    data_loader,
    kpis,
    model,
    monitoring,
    quality,
    recommendations,
    reporting,
    risk,
    risk_charts,
    scenario,
    signals,
)


def _money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.1f}K"
    return f"${value:,.2f}"


def _fmt(value: float, unit: str) -> str:
    if unit == "usd":
        return _money(value)
    if unit == "pct":
        return f"{value:.2f}%"
    return f"{value:,.0f}"


def _print_summary(df: pd.DataFrame) -> None:
    year, month = kpis.latest_period(df)
    p_year, p_month = kpis.previous_period(year, month)
    print("=" * 76)
    print("BANK LOAN REPORT  |  DASHBOARD 1: SUMMARY")
    print("=" * 76)
    print(f"Rows: {len(df):,}   MTD period: {month:02d}/{year}   PMTD period: {p_month:02d}/{p_year}")
    print("-" * 76)

    summary = kpis.summary_kpis(df)
    for row in summary.itertuples():
        pct = row.name in ("Average Interest Rate", "Average DTI")
        count = row.name == "Total Loan Applications"
        if pct:
            fmt = lambda v: f"{v:.2f}%"  # noqa: E731
        elif count:
            fmt = lambda v: f"{v:,.0f}"  # noqa: E731
        else:
            fmt = _money
        print(
            f"{row.name:<24} Total {fmt(row.total):>14}   "
            f"MTD {fmt(row.mtd):>13}   PMTD {fmt(row.pmtd):>13}   "
            f"MoM {row.mom_pct:>7.2f}%"
        )

    print("\n" + "-" * 76)
    print("GOOD LOAN vs BAD LOAN")
    print("-" * 76)
    for row in kpis.good_bad_loan_kpis(df).itertuples():
        print(
            f"{row.category:<12} {row.application_pct:>6.2f}%  "
            f"applications {row.applications:>7,}  "
            f"funded {_money(row.funded_amount):>12}  "
            f"received {_money(row.amount_received):>12}"
        )

    print("\n" + "-" * 76)
    print("LOAN STATUS GRID")
    print("-" * 76)
    grid = kpis.loan_status_grid(df).copy()
    for col in ("total_funded_amount", "total_amount_received",
                "mtd_funded_amount", "mtd_amount_received"):
        grid[col] = grid[col].map(lambda v: f"{v:,.0f}")
    for col in ("avg_interest_rate", "avg_dti"):
        grid[col] = grid[col].map(lambda v: f"{v:.2f}%")
    print(grid.to_string(index=False))


def _print_overview(df: pd.DataFrame) -> None:
    print("\n" + "=" * 76)
    print("BANK LOAN REPORT  |  DASHBOARD 2: OVERVIEW")
    print("=" * 76)
    for name, fn in kpis.OVERVIEW_AGGREGATIONS.items():
        table = fn(df)
        print(f"\n--- {name} ({len(table)} rows) ---")
        print(table.head(12).to_string(index=False))


def _print_validation(df: pd.DataFrame, json_path: str | None = None) -> int:
    results = quality.run_quality_audit(df)
    summary = quality.audit_summary(results)

    print("=" * 96)
    print("ENTERPRISE DATA QUALITY & GOVERNANCE AUDIT")
    print("=" * 96)
    for r in results:
        marker = f"[{r.severity}]" if not r.passed else "[PASS]"
        print(f"{marker:<10} {r.check_name:<36} {r.message}")

    print("-" * 96)
    print(
        f"Checks: {summary['total_checks']}  |  Passed: {summary['passed']}  |  "
        f"Blockers: {summary['blockers']}  |  Errors: {summary['errors']}  |  "
        f"Warnings: {summary['warnings']} (Known Defects)"
    )
    print(f"CI Gate Status: {summary['ci_status']}")

    if json_path:
        quality.results_to_json(results, json_path)
        print(f"Exported JSON quality report to {json_path}")

    return 0 if summary["ci_status"] == "PASSED" else 1


def _print_insights(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("BANK LOAN REPORT  |  RISK & PROFITABILITY ANALYSIS")
    print("=" * 88)

    print("\n--- Portfolio headline metrics ---")
    for row in risk.headline_risk_metrics(df).itertuples():
        print(f"{row.metric:<38} {_fmt(row.value, row.unit):>16}")

    print("\n--- Cash economics by loan status ---")
    econ = risk.portfolio_economics(df).copy()
    for col in ("funded_amount", "amount_received", "net_margin"):
        econ[col] = econ[col].map(_money)
    for col in ("recovery_rate_pct", "share_of_funded_pct"):
        econ[col] = econ[col].map(lambda v: f"{v:.2f}%")
    print(econ.to_string(index=False))

    print("\n--- Default rate by credit grade ---")
    grade = risk.segment_risk(df, "grade").sort_values("grade")
    print(
        grade[["grade", "loans", "default_rate_pct", "avg_interest_rate",
               "recovery_rate_pct", "net_margin"]]
        .assign(
            default_rate_pct=lambda d: d.default_rate_pct.map("{:.2f}%".format),
            avg_interest_rate=lambda d: d.avg_interest_rate.map("{:.2f}%".format),
            recovery_rate_pct=lambda d: d.recovery_rate_pct.map("{:.1f}%".format),
            net_margin=lambda d: d.net_margin.map(_money),
        )
        .to_string(index=False)
    )

    print("\n--- Does risk-based pricing work? ---")
    pricing = risk.pricing_power(df, "sub_grade")
    print(pricing.to_string(index=False))
    rho = pricing.iloc[0]["spearman_rho"]
    print(f"Interpretation: rank correlation of {rho:.3f} between the rate charged and the")
    print("default rate realised across sub-grades.")

    print("\n--- Loss-making segments (received less cash than funded) ---")
    losers = risk.unprofitable_segments(df, "purpose")
    if losers.empty:
        print("None: every loan purpose returned more cash than it consumed.")
    else:
        print(
            losers[["purpose", "loans", "default_rate_pct", "recovery_rate_pct", "net_margin"]]
            .assign(
                default_rate_pct=lambda d: d.default_rate_pct.map("{:.2f}%".format),
                recovery_rate_pct=lambda d: d.recovery_rate_pct.map("{:.1f}%".format),
                net_margin=lambda d: d.net_margin.map(_money),
            )
            .to_string(index=False)
        )

    print("\n--- Portfolio concentration ---")
    conc = risk.concentration(df)
    print(
        conc.assign(share_of_funded_pct=lambda d: d.share_of_funded_pct.map("{:.1f}%".format))
        .to_string(index=False)
    )


def _print_risk(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("ADVANCED CROSS-SEGMENT RISK & HHI CONCENTRATION")
    print("=" * 88)

    print("\n--- Herfindahl-Hirschman Concentration Index (HHI) ---")
    hhi = risk.hhi_concentration_table(df)
    print(hhi.to_string(index=False))

    print("\n--- Cross-Segment Interaction: Grade x Term (Top 8 Default Tiers) ---")
    gt = risk.cross_segment_risk(df, "grade", "term", min_loans=50).head(8)
    print(
        gt[["grade", "term", "loans", "default_rate_pct", "risk_multiple", "net_margin"]]
        .assign(
            default_rate_pct=lambda d: d.default_rate_pct.map("{:.2f}%".format),
            risk_multiple=lambda d: d.risk_multiple.map("{:.2f}x".format),
            net_margin=lambda d: d.net_margin.map(_money),
        )
        .to_string(index=False)
    )

    print("\n--- Statistical Signal Monotonicity (Credit Grades) ---")
    mono = signals.check_monotonicity(df, "grade")
    print(f"Monotonic Progression: {mono.is_monotonic}")
    if mono.violations:
        print(f"Violations: {', '.join(mono.violations)}")
    print(f"Spearman Rank Correlation: {mono.spearman_rho:.4f}")


def _print_model(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("PREDICTIVE DEFAULT RISK BENCHMARKING (LEAKAGE-FREE)")
    print("=" * 88)
    models = model.train_and_evaluate_models(df)

    eval_rows = []
    for name, bundle in models.items():
        ev = bundle.evaluation
        eval_rows.append({
            "model": name,
            "roc_auc": ev.roc_auc,
            "pr_auc": ev.pr_auc,
            "brier_score": ev.brier_score,
            "cv_roc_auc": f"{ev.cv_roc_auc_mean:.4f} +/- {ev.cv_roc_auc_std:.4f}",
            "precision": ev.precision,
            "recall": ev.recall,
            "f1": ev.f1,
        })
    print(pd.DataFrame(eval_rows).to_string(index=False))

    # Sample risk explanation
    sample_borrower = {
        "loan_amount": 25000,
        "int_rate": 0.185,
        "annual_income": 48000,
        "dti": 0.23,
        "installment": 640.0,
        "term": "60 months",
        "grade": "E",
        "home_ownership": "RENT",
        "verification_status": "Verified",
        "purpose": "small business",
    }
    print("\n--- Sample Borrower Explainability Audit ---")
    explanation = model.explain_borrower_risk(models["logistic_regression"], sample_borrower)
    print(f"Predicted Default Probability : {explanation['default_probability_pct']}")
    print(f"Risk Rating Band              : {explanation['risk_tier']}")
    print("Primary Risk Drivers:")
    for driver in explanation["primary_risk_drivers"]:
        print(f"  * {driver}")


def _print_monitor(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("TEMPORAL COHORT MONITORING & FEATURE DRIFT ANALYSIS")
    print("=" * 88)
    drift = monitoring.compute_portfolio_drift(df, split_month=7)
    df_drift = monitoring.drift_to_dataframe(drift)
    print(df_drift[["metric", "dimension", "baseline", "current", "abs_change", "rel_change_pct", "severity"]].to_string(index=False))


def _print_scenario(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("PORTFOLIO STRESS TESTING & WHAT-IF SCENARIOS")
    print("=" * 88)
    scens = scenario.run_all_scenarios(df)
    df_scens = scenario.scenarios_to_dataframe(scens)
    print(
        df_scens[["scenario_name", "margin_impact_usd", "baseline_default_pct", "scenario_default_pct", "sensitivity_tier"]]
        .assign(margin_impact_usd=lambda d: d.margin_impact_usd.map(_money))
        .to_string(index=False)
    )


def _print_recommendations(df: pd.DataFrame) -> None:
    print("=" * 88)
    print("DETERMINISTIC CREDIT POLICY RECOMMENDATIONS")
    print("=" * 88)
    recs = recommendations.generate_recommendations(df)
    for r in recs:
        print(f"[{r.action:<7}] {r.affected_segment:<28} | Metric: {r.metric} = {r.observed_value} ({r.confidence} Confidence)")
        print(f"          Rationale : {r.rationale}")
        print(f"          Caveat    : {r.caveat}\n")


def _load(args: argparse.Namespace) -> pd.DataFrame:
    path = data_loader.resolve_data_path(args.data, use_sample=args.sample)
    df = data_loader.load_loans(path)
    print(f"Loaded {len(df):,} rows from {path}")
    return df


def _default_outdir(args: argparse.Namespace, kind: str) -> Path:
    if getattr(args, "sample", False):
        return config.SAMPLE_FIGURES_DIR if kind == "figures" else config.SAMPLE_TABLES_DIR
    return config.FIGURES_DIR if kind == "figures" else config.TABLES_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bank_loan_report",
        description="Vehiql Bank Loan & Credit Risk Analytics Platform",
    )
    parser.add_argument("--data", default=None, help="path to a loan CSV file")
    parser.add_argument("--sample", action="store_true",
                        help="use the bundled 600-row sample instead of the full dataset")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="print the Summary and Overview dashboards")
    sub.add_parser("quality", help="print a data quality / null report")
    val_p = sub.add_parser("validate", help="run data quality audit (non-zero exit on failure)")
    val_p.add_argument("--json", default=None, help="path to export JSON validation report")

    sub.add_parser("insights", help="print risk and profitability analysis")
    sub.add_parser("risk", help="print cross-segment risk and HHI concentration")
    sub.add_parser("model", help="train and evaluate predictive default risk models")
    sub.add_parser("monitor", help="run temporal cohort drift monitoring")
    sub.add_parser("scenario", help="run stress testing and what-if simulation")
    sub.add_parser("recommendations", help="generate deterministic policy recommendations")

    charts_p = sub.add_parser("charts", help="render the Overview and risk charts as PNGs")
    charts_p.add_argument("--outdir", default=None)
    charts_p.add_argument("--risk-only", action="store_true", help="render only the risk charts")

    export_p = sub.add_parser("export", help="export every aggregation and model report")
    export_p.add_argument("--outdir", default=None)
    export_p.add_argument("--include-model", action="store_true", default=True)

    sub.add_parser("all", help="execute full analytics pipeline end-to-end")

    args = parser.parse_args(argv)
    config.ensure_output_dirs()
    df = _load(args)

    if args.command == "report":
        _print_summary(df)
        _print_overview(df)
    elif args.command == "quality":
        print(quality.profile_dataset(df).to_dataframe().to_string(index=False))
    elif args.command == "validate":
        return _print_validation(df, json_path=getattr(args, "json", None))
    elif args.command == "insights":
        _print_insights(df)
    elif args.command == "risk":
        _print_risk(df)
    elif args.command == "model":
        _print_model(df)
    elif args.command == "monitor":
        _print_monitor(df)
    elif args.command == "scenario":
        _print_scenario(df)
    elif args.command == "recommendations":
        _print_recommendations(df)
    elif args.command == "charts":
        outdir = Path(args.outdir) if args.outdir else _default_outdir(args, "figures")
        written = [] if args.risk_only else charts.build_all(df, outdir)
        written += risk_charts.build_all(df, outdir)
        for path in written:
            print(f"wrote {path}")
    elif args.command == "export":
        outdir = Path(args.outdir) if args.outdir else _default_outdir(args, "tables")
        outdir.mkdir(parents=True, exist_ok=True)
        exports = {
            "summary_kpis": kpis.summary_kpis(df),
            "good_bad_loan_kpis": kpis.good_bad_loan_kpis(df),
            "loan_status_grid": kpis.loan_status_grid(df),
            **{name: fn(df) for name, fn in kpis.OVERVIEW_AGGREGATIONS.items()},
            **{name: fn(df) for name, fn in risk.RISK_TABLES.items()},
            "recommendations": recommendations.recommendations_to_dataframe(recommendations.generate_recommendations(df)),
            "scenarios": scenario.scenarios_to_dataframe(scenario.run_all_scenarios(df)),
            "drift_monitoring": monitoring.drift_to_dataframe(monitoring.compute_portfolio_drift(df)),
        }
        for name, table in exports.items():
            path = outdir / f"{name}.csv"
            table.to_csv(path, index=False)
            print(f"wrote {path}")

        # Also export machine-readable JSON
        json_paths = reporting.export_machine_readable_json(df, outdir / "json", include_model=args.include_model)
        for _j_key, j_path in json_paths.items():
            print(f"wrote {j_path}")
    elif args.command == "all":
        print(reporting.generate_executive_summary_text(df))
        _print_summary(df)
        _print_insights(df)
        _print_risk(df)
        _print_model(df)
        _print_monitor(df)
        _print_scenario(df)
        _print_recommendations(df)
        _print_validation(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
