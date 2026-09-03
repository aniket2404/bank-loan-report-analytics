"""Charts for the risk analysis layer.

These are deliberately separate from ``charts.py``: that module reproduces the
six Overview dashboard visuals, whereas these visualise the risk findings
documented in ``docs/INSIGHTS.md``.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

from . import config, risk  # noqa: E402
from .charts import _save, _style_axis  # noqa: E402

RISK_RED = "#c0392b"
RISK_BLUE = "#2471a3"
NEUTRAL = "#7f8c8d"
GOOD_GREEN = "#1e8449"


def default_rate_by_grade(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Default rate and average interest rate side by side, by credit grade.

    The headline risk chart: it shows whether the bank's own grading system
    actually separates good borrowers from bad ones.
    """
    data = risk.segment_risk(df, "grade").sort_values("grade")
    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars = ax.bar(data["grade"], data["default_rate_pct"], color=RISK_RED, alpha=0.85,
                  label="Default rate (charged off %)")
    _style_axis(ax, "Default Rate vs Interest Rate Charged, by Credit Grade",
                "Credit grade", "Default rate (%)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_ylim(0, max(data["default_rate_pct"]) * 1.18)
    for bar, value in zip(bars, data["default_rate_pct"], strict=True):
        # anchored at the bar base: the interest-rate line tracks the bar tops,
        # so any label near the top of a bar risks colliding with it
        ax.annotate(f"{value:.1f}%", (bar.get_x() + bar.get_width() / 2, 0),
                    ha="center", va="bottom", xytext=(0, 6), textcoords="offset points",
                    fontsize=9.5, fontweight="bold", color="white")

    ax2 = ax.twinx()
    ax2.plot(data["grade"], data["avg_interest_rate"], marker="o", color=RISK_BLUE,
             linewidth=2.2, label="Avg interest rate charged")
    ax2.set_ylabel("Average interest rate (%)", fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.set_ylim(0, max(data["avg_interest_rate"]) * 1.35)

    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(handles, labels, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    return _save(fig, "07_default_rate_by_grade.png", outdir)


def recovery_by_purpose(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Recovery rate by loan purpose against the 100% break-even line.

    Plotted as recovery rate rather than absolute margin on purpose: absolute
    margin is dominated by volume, which hides the fact that one product is
    loss-making. Against a break-even reference, the outlier is unmissable.
    """
    data = risk.segment_risk(df, "purpose", min_loans=50).sort_values("recovery_rate_pct")
    labels = [p.replace("_", " ") for p in data["purpose"]]
    colors = [RISK_RED if v < 100 else GOOD_GREEN for v in data["recovery_rate_pct"]]

    fig, ax = plt.subplots(figsize=(11, 6.8))
    bars = ax.barh(labels, data["recovery_rate_pct"], color=colors, alpha=0.88)
    ax.axvline(100, color="black", linewidth=1.4, linestyle="--")
    ax.annotate("break-even (100%)", xy=(100, len(labels) - 0.35), xytext=(4, 0),
                textcoords="offset points", fontsize=9, fontweight="bold", va="center")

    _style_axis(ax, "Cash Recovery Rate by Loan Purpose", "Cash received as % of principal lent", "")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlim(90, max(data["recovery_rate_pct"]) * 1.045)

    for bar, row in zip(bars, data.itertuples(), strict=True):
        ax.annotate(
            f"{row.recovery_rate_pct:.1f}%   ({row.default_rate_pct:.1f}% default, "
            f"{row.loans:,} loans)",
            (bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(6, 0), textcoords="offset points", va="center", fontsize=8.5,
            color="#333333",
        )
    ax.set_xlim(90, max(data["recovery_rate_pct"]) + 6.5)
    fig.tight_layout()
    return _save(fig, "08_recovery_by_purpose.png", outdir)


def _volume_floor(df: pd.DataFrame, fraction: float = 0.0065, minimum: int = 5) -> int:
    """Minimum loans a segment needs before it is plotted.

    Expressed as a share of the dataset rather than a fixed count so the charts
    still render on the 600-row bundled sample. On the full 38,576-row dataset
    this returns 250, which is what suppresses noisy buckets such as the
    98-loan ``home_ownership = OTHER`` group.
    """
    return max(minimum, round(len(df) * fraction))


def default_rate_by_segment(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Small-multiple panel: which borrower attributes actually predict default."""
    flagged = risk.add_risk_flags(df)
    panels = [
        ("term", "Loan term", flagged),
        ("income_quintile", "Annual income quintile", flagged),
        ("loan_size_band", "Loan size", flagged),
        ("dti_band", "Debt-to-income ratio", flagged),
        ("home_ownership", "Home ownership", flagged),
        ("emp_length", "Employment length", flagged),
    ]
    overall = flagged["is_charged_off"].mean() * 100

    floor = _volume_floor(flagged)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
    for ax, (column, title, data) in zip(axes.flat, panels, strict=True):
        seg = risk.segment_risk(data, column, min_loans=floor)
        if column in {"income_quintile", "loan_size_band", "dti_band", "emp_length"}:
            seg = seg.sort_values(column)
        else:
            seg = seg.sort_values("default_rate_pct", ascending=False)
        if seg.empty or seg["default_rate_pct"].max() <= 0:
            # small dataset (e.g. the bundled sample): no bucket clears the
            # volume floor, or nothing in this cut defaulted. Say so rather
            # than drawing an empty or misleading panel.
            _style_axis(ax, title, "", "Default rate (%)")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.text(0.5, 0.5, f"no segment with >= {floor} loans", transform=ax.transAxes,
                    ha="center", va="center", fontsize=9, color="#888888")
            continue
        ax.bar(seg[column].astype(str), seg["default_rate_pct"], color=RISK_BLUE, alpha=0.85)
        ax.axhline(overall, color=RISK_RED, linestyle="--", linewidth=1.2)
        _style_axis(ax, title, "", "Default rate (%)")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.set_ylim(0, max(seg["default_rate_pct"]) * 1.28)
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
        for label in ax.get_xticklabels():
            label.set_ha("right")

    fig.suptitle(
        f"Default Rate by Borrower Attribute  (dashed line = portfolio average {overall:.1f}%)",
        fontsize=14, fontweight="bold", y=0.985,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _save(fig, "09_default_rate_by_segment.png", outdir)


def risk_pricing_scatter(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Interest rate vs realised default rate across the 35 sub-grades."""
    seg = risk.segment_risk(df, "sub_grade", min_loans=20)
    stats = risk.pricing_power(df, "sub_grade", min_loans=20).iloc[0]

    fig, ax = plt.subplots(figsize=(9.5, 6))
    sizes = (seg["loans"] / seg["loans"].max() * 480) + 25
    scatter = ax.scatter(seg["avg_interest_rate"], seg["default_rate_pct"], s=sizes,
                         c=seg["loans"], cmap="viridis", alpha=0.82, edgecolor="white",
                         linewidth=0.8)
    ordered = seg.sort_values("avg_interest_rate").reset_index(drop=True)
    for i, row in enumerate(ordered.itertuples()):
        # alternate above/below so neighbouring sub-grades cannot overlap
        dy = 9 if i % 2 == 0 else -15
        ax.annotate(row.sub_grade, (row.avg_interest_rate, row.default_rate_pct),
                    fontsize=7.5, xytext=(0, dy), textcoords="offset points", ha="center",
                    color="#333333")

    _style_axis(ax, "Risk-Based Pricing Check: Rate Charged vs Default Rate Realised",
                "Average interest rate charged (%)", "Realised default rate (%)")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.annotate(
        f"Spearman rho = {stats.spearman_rho:.3f}\nPearson r = {stats.pearson_r:.3f}\n"
        f"{int(stats.segments_compared)} sub-grades",
        xy=(0.03, 0.95), xycoords="axes fraction", va="top", fontsize=9.5,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#cccccc"},
    )
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("Loans in sub-grade", fontsize=9)
    fig.tight_layout()
    return _save(fig, "10_risk_pricing_scatter.png", outdir)


RISK_CHART_BUILDERS = (
    default_rate_by_grade,
    recovery_by_purpose,
    default_rate_by_segment,
    risk_pricing_scatter,
)


def build_all(df: pd.DataFrame, outdir: Path | None = None) -> list[Path]:
    target = outdir or config.FIGURES_DIR
    written: list[Path] = []
    for builder in RISK_CHART_BUILDERS:
        path = builder(df, target)
        if path is not None:
            written.append(path)
    return written
