"""Risk and profitability analysis for the Bank Loan Report project.

The Summary and Overview dashboards answer *how much* the bank lent. This module
answers *whether the lending was any good*: which segments default, whether the
bank's own risk pricing predicts those defaults, where the losses actually land,
and how concentrated the book is.

Definitions used throughout
---------------------------
default rate
    Share of loans with ``loan_status = 'Charged Off'``. Reported on all loans
    (matching the dashboard's Bad Loan %) and on *closed* loans only, which
    excludes the still-open ``Current`` book from the denominator.
recovery rate
    ``total_payment / loan_amount``. Above 100% means interest collected
    exceeded principal lent; below 100% is a cash loss.
net margin
    ``total_payment - loan_amount``. Cash in minus cash out, with no discounting
    and no cost of funds - this dataset supports nothing more sophisticated.
"""

from __future__ import annotations

import pandas as pd

from . import config

BAD_STATUS = list(config.BAD_LOAN_STATUSES)

# Segments worth a risk breakdown, mapped to the column that defines them.
RISK_SEGMENTS = {
    "grade": "grade",
    "sub_grade": "sub_grade",
    "term": "term",
    "purpose": "purpose",
    "home_ownership": "home_ownership",
    "verification_status": "verification_status",
    "emp_length": "emp_length",
    "address_state": "address_state",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def add_risk_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the boolean and banded columns the risk views need."""
    out = df.copy()
    out["is_charged_off"] = out["loan_status"].isin(BAD_STATUS).astype(int)
    out["is_closed"] = out["loan_status"].isin(["Fully Paid", *BAD_STATUS]).astype(int)
    out["net_margin"] = out["total_payment"] - out["loan_amount"]

    out["dti_band"] = pd.cut(
        out["dti"] * 100,
        bins=[-0.01, 10, 15, 20, 25, 100],
        labels=["0-10%", "10-15%", "15-20%", "20-25%", "25%+"],
    )
    out["loan_size_band"] = pd.cut(
        out["loan_amount"],
        bins=[0, 5_000, 10_000, 15_000, 20_000, 25_000, 1_000_000],
        labels=["<$5K", "$5-10K", "$10-15K", "$15-20K", "$20-25K", "$25K+"],
    )
    out["income_quintile"] = pd.qcut(
        out["annual_income"],
        5,
        labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"],
        duplicates="drop",
    )
    return out


# --------------------------------------------------------------------------- #
# portfolio level
# --------------------------------------------------------------------------- #
def portfolio_economics(df: pd.DataFrame) -> pd.DataFrame:
    """Cash-in vs cash-out for the whole book and for each loan status."""
    data = add_risk_flags(df)
    rows = []

    def _row(label: str, subset: pd.DataFrame) -> dict:
        funded = float(subset["loan_amount"].sum())
        received = float(subset["total_payment"].sum())
        return {
            "segment": label,
            "loans": int(len(subset)),
            "funded_amount": funded,
            "amount_received": received,
            "net_margin": received - funded,
            "recovery_rate_pct": (received / funded * 100) if funded else 0.0,
            "share_of_funded_pct": (funded / float(data["loan_amount"].sum()) * 100)
            if len(data)
            else 0.0,
        }

    rows.append(_row("Total portfolio", data))
    for status in sorted(data["loan_status"].dropna().unique()):
        rows.append(_row(status, data[data["loan_status"] == status]))
    return pd.DataFrame(rows)


def headline_risk_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """The handful of numbers that summarise portfolio health."""
    data = add_risk_flags(df)
    closed = data[data["is_closed"] == 1]
    charged_off = data[data["is_charged_off"] == 1]
    funded = float(data["loan_amount"].sum())
    received = float(data["total_payment"].sum())
    co_funded = float(charged_off["loan_amount"].sum())
    co_received = float(charged_off["total_payment"].sum())

    metrics = [
        ("Loans in book", len(data), "count"),
        ("Total funded", funded, "usd"),
        ("Total received", received, "usd"),
        ("Net margin", received - funded, "usd"),
        ("Portfolio recovery rate", (received / funded * 100) if funded else 0, "pct"),
        (
            "Default rate (all loans)",
            (len(charged_off) / len(data) * 100) if len(data) else 0,
            "pct",
        ),
        (
            "Default rate (closed loans only)",
            (int(charged_off["is_closed"].sum()) / len(closed) * 100) if len(closed) else 0,
            "pct",
        ),
        (
            "Open book still amortising",
            (int((data["is_closed"] == 0).sum()) / len(data) * 100) if len(data) else 0,
            "pct",
        ),
        (
            "Recovery on charged-off loans",
            (co_received / co_funded * 100) if co_funded else 0,
            "pct",
        ),
        ("Net cash lost to charge-offs", co_funded - co_received, "usd"),
        (
            "Charge-off loss as share of funded",
            ((co_funded - co_received) / funded * 100) if funded else 0,
            "pct",
        ),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "unit"])


# --------------------------------------------------------------------------- #
# segment level
# --------------------------------------------------------------------------- #
def segment_risk(df: pd.DataFrame, column: str, min_loans: int = 1) -> pd.DataFrame:
    """Default rate, pricing and profitability for one segmenting column.

    ``min_loans`` suppresses segments too small to read anything into - a
    47-loan state with a 30% default rate is noise, not a finding.
    """
    if column not in df.columns:
        raise KeyError(f"unknown segment column: {column}")
    data = add_risk_flags(df)
    grouped = (
        data.groupby(column, observed=True)
        .agg(
            loans=("id", "count"),
            funded_amount=("loan_amount", "sum"),
            amount_received=("total_payment", "sum"),
            charged_off_loans=("is_charged_off", "sum"),
            avg_interest_rate=("int_rate", "mean"),
            avg_dti=("dti", "mean"),
            median_annual_income=("annual_income", "median"),
            avg_loan_amount=("loan_amount", "mean"),
        )
        .reset_index()
    )
    grouped["default_rate_pct"] = grouped["charged_off_loans"] / grouped["loans"] * 100
    grouped["recovery_rate_pct"] = (
        grouped["amount_received"] / grouped["funded_amount"].replace(0, pd.NA) * 100
    )
    grouped["net_margin"] = grouped["amount_received"] - grouped["funded_amount"]
    grouped["avg_interest_rate"] = grouped["avg_interest_rate"] * 100
    grouped["avg_dti"] = grouped["avg_dti"] * 100
    grouped["share_of_loans_pct"] = grouped["loans"] / len(data) * 100

    grouped = grouped[grouped["loans"] >= min_loans]
    return grouped.sort_values("default_rate_pct", ascending=False).reset_index(drop=True)


def risk_ranking(df: pd.DataFrame, min_loans: int = 300) -> pd.DataFrame:
    """One row per segment value across every dimension, ranked by default rate.

    Useful as a single "where is the risk" table for the Details dashboard.
    """
    frames = []
    for name, column in RISK_SEGMENTS.items():
        seg = segment_risk(df, column, min_loans=min_loans)
        seg = seg.rename(columns={column: "segment_value"})
        seg.insert(0, "dimension", name)
        frames.append(
            seg[
                [
                    "dimension",
                    "segment_value",
                    "loans",
                    "default_rate_pct",
                    "avg_interest_rate",
                    "recovery_rate_pct",
                    "net_margin",
                ]
            ]
        )
    populated = [f for f in frames if not f.empty]
    if not populated:
        # every dimension fell below the volume floor - real on small samples
        return pd.DataFrame(columns=[
            "dimension", "segment_value", "loans", "default_rate_pct",
            "avg_interest_rate", "recovery_rate_pct", "net_margin",
        ])
    combined = pd.concat(populated, ignore_index=True)
    return combined.sort_values("default_rate_pct", ascending=False).reset_index(drop=True)


def unprofitable_segments(df: pd.DataFrame, column: str = "purpose", min_loans: int = 50) -> pd.DataFrame:
    """Segments where the bank received less cash than it lent."""
    seg = segment_risk(df, column, min_loans=min_loans)
    return seg[seg["net_margin"] < 0].sort_values("net_margin").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# does the bank's risk pricing work?
# --------------------------------------------------------------------------- #
def pricing_power(df: pd.DataFrame, column: str = "sub_grade", min_loans: int = 20) -> pd.DataFrame:
    """Correlate the interest rate charged with the default rate realised.

    If the bank's grading system works, segments it prices higher should default
    more. A strong positive rank correlation is evidence that risk-based pricing
    is doing its job; a weak one would mean the grade is decorative.
    """
    seg = segment_risk(df, column, min_loans=min_loans)
    rate, default = seg["avg_interest_rate"], seg["default_rate_pct"]
    pearson = rate.corr(default)
    # Spearman's rho is Pearson's r on the ranks, computed here directly rather
    # than via method="spearman", which delegates to scipy. Keeping the
    # dependency list to pandas and matplotlib means the whole analysis layer
    # installs anywhere; average-rank tie handling matches scipy's default, so
    # the value is identical.
    spearman = rate.rank().corr(default.rank())
    return pd.DataFrame(
        [
            {
                "dimension": column,
                "segments_compared": len(seg),
                "min_loans_per_segment": min_loans,
                "pearson_r": pearson,
                "spearman_rho": spearman,
            }
        ]
    )


def concentration(df: pd.DataFrame) -> pd.DataFrame:
    """How much of the book sits in its largest few buckets."""
    funded_total = float(df["loan_amount"].sum())
    rows = []
    for label, column, tops in (
        ("States", "address_state", (1, 3, 5, 10)),
        ("Purposes", "purpose", (1, 3, 5)),
        ("Grades", "grade", (1, 3)),
    ):
        ranked = df.groupby(column, observed=True)["loan_amount"].sum().sort_values(ascending=False)
        for n in tops:
            rows.append(
                {
                    "dimension": label,
                    "top_n": n,
                    "members": ", ".join(map(str, ranked.head(n).index.tolist())),
                    "share_of_funded_pct": ranked.head(n).sum() / funded_total * 100
                    if funded_total
                    else 0.0,
                }
            )
    return pd.DataFrame(rows)


def monthly_risk_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Volume, pricing and default rate by issue month.

    Read the default-rate column with care: see ``docs/DATA_QUALITY.md``. The
    source dates are not internally consistent, so this is a comparison of
    *issue cohorts as labelled*, not a true seasoning curve.
    """
    data = add_risk_flags(df)
    trend = (
        data.groupby(["issue_month", "issue_month_short"], observed=True)
        .agg(
            loans=("id", "count"),
            funded_amount=("loan_amount", "sum"),
            charged_off_loans=("is_charged_off", "sum"),
            avg_interest_rate=("int_rate", "mean"),
            avg_dti=("dti", "mean"),
        )
        .reset_index()
        .sort_values("issue_month")
    )
    trend["default_rate_pct"] = trend["charged_off_loans"] / trend["loans"] * 100
    trend["avg_interest_rate"] = trend["avg_interest_rate"] * 100
    trend["avg_dti"] = trend["avg_dti"] * 100
    trend["loans_mom_pct"] = trend["loans"].pct_change() * 100
    trend["funded_mom_pct"] = trend["funded_amount"].pct_change() * 100
    return trend.reset_index(drop=True)


def term_grade_risk(df: pd.DataFrame, min_loans: int = 100) -> pd.DataFrame:
    """Realised default rate per term x grade, benchmarked against the portfolio.

    This is the Python counterpart of section 7 of
    ``sql/06_risk_and_cohort_analysis.sql``; the two are expected to agree, and
    that agreement is what makes the SQL layer trustworthy without a live
    SQL Server in CI.

    Denominator note: only CLOSED loans ('Fully Paid' + 'Charged Off') are
    counted. A loan still 'Current' has not had the opportunity to default, so
    including it understates realised credit risk. On the full dataset this
    moves the portfolio default rate from 13.82% (all loans) to 14.23%
    (closed only).
    """
    data = add_risk_flags(df)
    closed = data[data["loan_status"].isin(["Fully Paid", "Charged Off"])]
    if closed.empty:
        return pd.DataFrame(
            columns=[
                "term", "grade", "loans", "funded_amount", "segment_default_pct",
                "portfolio_default_pct", "excess_default_pp", "risk_multiple", "risk_rank",
            ]
        )
    portfolio_default = closed["is_charged_off"].mean() * 100

    grouped = (
        closed.groupby(["term", "grade"], observed=True)
        .agg(
            loans=("id", "count"),
            funded_amount=("loan_amount", "sum"),
            charged_off_loans=("is_charged_off", "sum"),
        )
        .reset_index()
    )
    grouped = grouped[grouped["loans"] >= min_loans].copy()
    grouped["segment_default_pct"] = grouped["charged_off_loans"] / grouped["loans"] * 100
    grouped["portfolio_default_pct"] = portfolio_default
    grouped["excess_default_pp"] = grouped["segment_default_pct"] - portfolio_default
    grouped["risk_multiple"] = grouped["segment_default_pct"] / portfolio_default
    grouped = grouped.sort_values("segment_default_pct", ascending=False).reset_index(drop=True)
    grouped["risk_rank"] = grouped.index + 1
    return grouped.drop(columns=["charged_off_loans"])




# --------------------------------------------------------------------------- #
# Advanced Cross-Segment Interactions & Concentration
# --------------------------------------------------------------------------- #
def cross_segment_risk(
    df: pd.DataFrame,
    dim1: str,
    dim2: str,
    min_loans: int = 50,
) -> pd.DataFrame:
    """Analyze risk interactions between two categorical/banded dimensions.

    Calculates loan counts, funded volume, realized default rate, recovery rate,
    net cash margin, and risk multiple against portfolio baseline.
    ``min_loans`` suppresses sparse combinations to prevent noise.
    """
    data = add_risk_flags(df)
    for dim in (dim1, dim2):
        if dim not in data.columns:
            raise KeyError(f"dimension not found: {dim}")

    portfolio_default = data["is_charged_off"].mean() * 100

    grouped = (
        data.groupby([dim1, dim2], observed=True)
        .agg(
            loans=("id", "count"),
            funded_amount=("loan_amount", "sum"),
            amount_received=("total_payment", "sum"),
            charged_off_loans=("is_charged_off", "sum"),
            avg_interest_rate=("int_rate", "mean"),
            avg_dti=("dti", "mean"),
        )
        .reset_index()
    )

    grouped = grouped[grouped["loans"] >= min_loans].copy()
    if grouped.empty:
        return pd.DataFrame(
            columns=[
                dim1, dim2, "loans", "funded_amount", "amount_received",
                "default_rate_pct", "recovery_rate_pct", "net_margin",
                "risk_multiple", "avg_interest_rate", "avg_dti"
            ]
        )

    grouped["default_rate_pct"] = grouped["charged_off_loans"] / grouped["loans"] * 100
    grouped["recovery_rate_pct"] = (
        grouped["amount_received"] / grouped["funded_amount"].replace(0, pd.NA) * 100
    )
    grouped["net_margin"] = grouped["amount_received"] - grouped["funded_amount"]
    grouped["risk_multiple"] = grouped["default_rate_pct"] / portfolio_default if portfolio_default else 1.0
    grouped["avg_interest_rate"] = grouped["avg_interest_rate"] * 100
    grouped["avg_dti"] = grouped["avg_dti"] * 100

    return grouped.sort_values("default_rate_pct", ascending=False).reset_index(drop=True)


def hhi_concentration_table(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate the Herfindahl-Hirschman Index (HHI) for key portfolio dimensions.

    HHI = sum(market_share_percentage ^ 2).
    Standard DOJ / Regulatory concentration tiers:
    - HHI < 1,500: Unconcentrated / Diversified
    - 1,500 <= HHI <= 2,500: Moderately Concentrated
    - HHI > 2,500: Highly Concentrated
    """
    funded_total = float(df["loan_amount"].sum())
    dimensions = [
        ("address_state", "Geographic (State)"),
        ("purpose", "Loan Purpose"),
        ("grade", "Credit Grade"),
        ("term", "Loan Term"),
    ]

    records = []
    for col, label in dimensions:
        if col not in df.columns:
            continue
        shares = (
            df.groupby(col, observed=True)["loan_amount"].sum() / funded_total * 100
        )
        hhi = float((shares ** 2).sum())
        top_bucket = shares.idxmax()
        top_share = float(shares.max())

        if hhi < 1500:
            status = "Diversified (<1500)"
        elif hhi <= 2500:
            status = "Moderate Concentration (1500-2500)"
        else:
            status = "High Concentration (>2500)"

        records.append({
            "dimension": label,
            "distinct_buckets": len(shares),
            "hhi_index": round(hhi, 2),
            "concentration_tier": status,
            "top_bucket": top_bucket,
            "top_bucket_share_pct": round(top_share, 2),
        })

    return pd.DataFrame(records)


def cumulative_exposure(df: pd.DataFrame, column: str = "address_state") -> pd.DataFrame:
    """Calculate cumulative concentration curves (Lorenz/Gini style)."""
    funded_total = float(df["loan_amount"].sum())
    grouped = (
        df.groupby(column, observed=True)["loan_amount"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    grouped["share_of_funded_pct"] = grouped["loan_amount"] / funded_total * 100
    grouped["cum_funded_pct"] = grouped["share_of_funded_pct"].cumsum()
    grouped["cum_segment_pct"] = (grouped.index + 1) / len(grouped) * 100
    return grouped


RISK_TABLES = {
    "headline_risk_metrics": headline_risk_metrics,
    "portfolio_economics": portfolio_economics,
    "risk_ranking": risk_ranking,
    "concentration": concentration,
    "hhi_concentration": hhi_concentration_table,
    "monthly_risk_trend": monthly_risk_trend,
    "risk_by_grade": lambda df: segment_risk(df, "grade"),
    "risk_by_term": lambda df: segment_risk(df, "term"),
    "risk_by_purpose": lambda df: segment_risk(df, "purpose"),
    "risk_by_dti_band": lambda df: segment_risk(add_risk_flags(df), "dti_band"),
    "risk_by_income_quintile": lambda df: segment_risk(add_risk_flags(df), "income_quintile"),
    "risk_by_loan_size": lambda df: segment_risk(add_risk_flags(df), "loan_size_band"),
    "risk_by_term_and_grade": term_grade_risk,
    "cross_grade_purpose": lambda df: cross_segment_risk(df, "grade", "purpose", min_loans=50),
    "cross_income_dti": lambda df: cross_segment_risk(add_risk_flags(df), "income_quintile", "dti_band", min_loans=50),
}
