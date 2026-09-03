"""Matplotlib chart builders for the six Overview dashboard visuals."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe: works in CI and on servers
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

from . import config, kpis  # noqa: E402

ACCENT = "#1f77b4"
ACCENT_2 = "#ff7f0e"
ACCENT_3 = "#2ca02c"
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]


def _style_axis(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _thousands(ax: plt.Axes) -> None:
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))


def _save(fig: plt.Figure, filename: str, outdir: Path | None) -> Path | None:
    if outdir is None:
        return None
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / filename
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def monthly_trend(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Line chart: applications, funded amount and amount received by month."""
    data = kpis.by_month(df)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(data["issue_month_short"], data["total_funded_amount"], marker="o",
            color=ACCENT, label="Total Funded Amount")
    ax.plot(data["issue_month_short"], data["total_amount_received"], marker="s",
            color=ACCENT_2, label="Total Amount Received")
    _style_axis(ax, "Monthly Trends by Issue Date", "Month", "Amount (USD)")
    _thousands(ax)

    ax2 = ax.twinx()
    ax2.bar(data["issue_month_short"], data["total_loan_applications"],
            alpha=0.18, color=ACCENT_3, label="Total Loan Applications")
    ax2.set_ylabel("Loan Applications", fontsize=10)
    ax2.grid(False)

    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(handles, labels, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    return _save(fig, "01_monthly_trend.png", outdir)


def state_analysis(df: pd.DataFrame, outdir: Path | None = None, top_n: int = 15) -> Path | None:
    """Horizontal bar chart standing in for the Power BI / Tableau filled map."""
    data = kpis.by_state(df).nlargest(top_n, "total_funded_amount").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(data["address_state"], data["total_funded_amount"], color=ACCENT)
    _style_axis(ax, f"Regional Analysis by State (Top {top_n} by Funded Amount)",
                "Total Funded Amount (USD)", "State")
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e6:,.1f}M"))
    fig.tight_layout()
    return _save(fig, "02_state_analysis.png", outdir)


def term_donut(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Donut chart: loan applications split by term."""
    data = kpis.by_term(df)
    fig, ax = plt.subplots(figsize=(6.5, 6))
    wedges, _, autotexts = ax.pie(
        data["total_loan_applications"],
        labels=data["term"],
        autopct="%1.1f%%",
        startangle=90,
        colors=PALETTE[: len(data)],
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        pctdistance=0.79,
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontweight("bold")
    ax.set_title("Loan Term Analysis", fontsize=13, fontweight="bold", pad=14)
    total = int(data["total_loan_applications"].sum())
    ax.text(0, 0, f"{total:,}\napplications", ha="center", va="center",
            fontsize=11, fontweight="bold")
    fig.tight_layout()
    return _save(fig, "03_term_donut.png", outdir)


def emp_length_bar(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Bar chart: applications by employment length."""
    data = kpis.by_emp_length(df)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(data["emp_length"].astype(str), data["total_loan_applications"], color=ACCENT)
    _style_axis(ax, "Employee Length Analysis", "Employment Length", "Total Loan Applications")
    _thousands(ax)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    return _save(fig, "04_emp_length.png", outdir)


def purpose_bar(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Horizontal bar chart: applications by loan purpose."""
    data = kpis.by_purpose(df).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(data["purpose"], data["total_loan_applications"], color=ACCENT)
    _style_axis(ax, "Loan Purpose Breakdown", "Total Loan Applications", "Purpose")
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    fig.tight_layout()
    return _save(fig, "05_purpose.png", outdir)


def home_ownership_treemap(df: pd.DataFrame, outdir: Path | None = None) -> Path | None:
    """Tree map by home ownership. Falls back to a bar chart if squarify is absent."""
    data = kpis.by_home_ownership(df)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    try:
        import squarify  # type: ignore
        from matplotlib.patches import Patch

        total = data["total_loan_applications"].sum()
        share = data["total_loan_applications"] / total
        # Label only tiles big enough to hold text; the rest go in the legend.
        labels = [
            f"{row.home_ownership}\n{row.total_loan_applications:,}"
            if pct >= 0.10
            else ""
            for row, pct in zip(data.itertuples(), share, strict=True)
        ]
        colors = PALETTE[: len(data)]
        squarify.plot(
            sizes=data["total_loan_applications"],
            label=labels,
            color=colors,
            ax=ax,
            text_kwargs={"color": "white", "fontsize": 11, "fontweight": "bold"},
            pad=True,
        )
        ax.axis("off")
        ax.set_title("Home Ownership Analysis (Tree Map)", fontsize=13,
                     fontweight="bold", pad=12)
        handles = [
            Patch(facecolor=c, label=f"{row.home_ownership} — {row.total_loan_applications:,} ({pct:.1%})")
            for c, row, pct in zip(colors, data.itertuples(), share, strict=True)
        ]
        ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02),
                  ncol=3, frameon=False, fontsize=9)
    except ImportError:
        ax.bar(data["home_ownership"], data["total_loan_applications"],
               color=PALETTE[: len(data)])
        _style_axis(ax, "Home Ownership Analysis", "Home Ownership",
                    "Total Loan Applications")
        _thousands(ax)
    fig.tight_layout()
    return _save(fig, "06_home_ownership.png", outdir)


CHART_BUILDERS = (
    monthly_trend,
    state_analysis,
    term_donut,
    emp_length_bar,
    purpose_bar,
    home_ownership_treemap,
)


def build_all(df: pd.DataFrame, outdir: Path | None = None) -> list[Path]:
    """Render all six Overview charts to ``outdir`` (defaults to reports/figures)."""
    target = outdir or config.FIGURES_DIR
    written: list[Path] = []
    for builder in CHART_BUILDERS:
        path = builder(df, target)
        if path is not None:
            written.append(path)
    return written
