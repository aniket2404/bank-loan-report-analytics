"""KPI calculations for the Bank Loan Report.

Every function here mirrors one of the SQL queries in ``sql/`` so the Python,
SQL, Power BI, Excel and Tableau layers all return identical numbers.

Conventions taken from the problem statement:
* ``int_rate`` and ``dti`` are stored as decimal fractions and multiplied by 100
  for presentation.
* MTD  = the latest month present in the data (based on ``issue_date``).
* PMTD = the calendar month immediately before that latest month.
* Good loans = loan_status in ('Fully Paid', 'Current'); bad loans = 'Charged Off'.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from . import config


# --------------------------------------------------------------------------- #
# period helpers
# --------------------------------------------------------------------------- #
def latest_period(df: pd.DataFrame) -> tuple[int, int]:
    """Return ``(year, month)`` of the most recent ``issue_date`` in the data."""
    latest = df["issue_date"].max()
    if pd.isna(latest):
        raise ValueError("issue_date contains no valid dates.")
    return int(latest.year), int(latest.month)


def previous_period(year: int, month: int) -> tuple[int, int]:
    """Return the calendar month before ``(year, month)``."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def filter_period(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    return df[(df["issue_year"] == year) & (df["issue_month"] == month)]


def mtd_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Month-to-date slice (latest month in the dataset)."""
    return filter_period(df, *latest_period(df))


def pmtd_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Previous-month-to-date slice."""
    return filter_period(df, *previous_period(*latest_period(df)))


# --------------------------------------------------------------------------- #
# atomic metrics
# --------------------------------------------------------------------------- #
def total_loan_applications(df: pd.DataFrame) -> int:
    return int(df["id"].count())


def total_funded_amount(df: pd.DataFrame) -> float:
    return float(df["loan_amount"].sum())


def total_amount_received(df: pd.DataFrame) -> float:
    return float(df["total_payment"].sum())


def average_interest_rate(df: pd.DataFrame) -> float:
    """Average interest rate as a percentage."""
    return float(df["int_rate"].mean() * 100) if len(df) else 0.0


def average_dti(df: pd.DataFrame) -> float:
    """Average debt-to-income ratio as a percentage."""
    return float(df["dti"].mean() * 100) if len(df) else 0.0


def mom_change(current: float, previous: float) -> float:
    """Month-over-month change as a percentage. Returns 0.0 when previous is 0."""
    if not previous:
        return 0.0
    return (current - previous) / previous * 100


# --------------------------------------------------------------------------- #
# summary dashboard
# --------------------------------------------------------------------------- #
@dataclass
class KpiBlock:
    """One KPI with its total, MTD, PMTD and MoM values."""

    name: str
    total: float
    mtd: float
    pmtd: float
    mom_pct: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_METRICS = {
    "Total Loan Applications": total_loan_applications,
    "Total Funded Amount": total_funded_amount,
    "Total Amount Received": total_amount_received,
    "Average Interest Rate": average_interest_rate,
    "Average DTI": average_dti,
}


def summary_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """All five headline KPIs with Total / MTD / PMTD / MoM columns."""
    mtd, pmtd = mtd_frame(df), pmtd_frame(df)
    rows = []
    for name, fn in _METRICS.items():
        total, m, p = float(fn(df)), float(fn(mtd)), float(fn(pmtd))
        rows.append(KpiBlock(name, total, m, p, mom_change(m, p)).as_dict())
    return pd.DataFrame(rows)


def good_bad_loan_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Good loan vs bad loan KPI block."""
    total_apps = total_loan_applications(df)
    rows = []
    for label, statuses in (
        ("Good Loan", config.GOOD_LOAN_STATUSES),
        ("Bad Loan", config.BAD_LOAN_STATUSES),
    ):
        subset = df[df["loan_status"].isin(list(statuses))]
        apps = total_loan_applications(subset)
        rows.append(
            {
                "category": label,
                "loan_status_included": ", ".join(statuses),
                "application_pct": (apps / total_apps * 100) if total_apps else 0.0,
                "applications": apps,
                "funded_amount": total_funded_amount(subset),
                "amount_received": total_amount_received(subset),
            }
        )
    return pd.DataFrame(rows)


def loan_status_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Grid view by loan_status, including MTD funded / received columns."""
    grid = (
        df.groupby("loan_status", observed=True)
        .agg(
            total_loan_applications=("id", "count"),
            total_funded_amount=("loan_amount", "sum"),
            total_amount_received=("total_payment", "sum"),
            avg_interest_rate=("int_rate", "mean"),
            avg_dti=("dti", "mean"),
        )
        .reset_index()
    )
    grid["avg_interest_rate"] = grid["avg_interest_rate"] * 100
    grid["avg_dti"] = grid["avg_dti"] * 100

    mtd = (
        mtd_frame(df)
        .groupby("loan_status", observed=True)
        .agg(
            mtd_funded_amount=("loan_amount", "sum"),
            mtd_amount_received=("total_payment", "sum"),
        )
        .reset_index()
    )
    merged = grid.merge(mtd, on="loan_status", how="left")
    merged[["mtd_funded_amount", "mtd_amount_received"]] = merged[
        ["mtd_funded_amount", "mtd_amount_received"]
    ].fillna(0)
    return merged.sort_values("loan_status").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# overview dashboard aggregations
# --------------------------------------------------------------------------- #
def _aggregate(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        df.groupby(keys, observed=True)
        .agg(
            total_loan_applications=("id", "count"),
            total_funded_amount=("loan_amount", "sum"),
            total_amount_received=("total_payment", "sum"),
        )
        .reset_index()
    )


def by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly trend by issue date (line chart)."""
    out = _aggregate(df, ["issue_month", "issue_month_name", "issue_month_short"])
    return out.sort_values("issue_month").reset_index(drop=True)


def by_state(df: pd.DataFrame) -> pd.DataFrame:
    """Regional analysis by state (filled map)."""
    return _aggregate(df, ["address_state"]).sort_values("address_state").reset_index(drop=True)


def by_term(df: pd.DataFrame) -> pd.DataFrame:
    """Loan term analysis (donut chart)."""
    return _aggregate(df, ["term"]).sort_values("term").reset_index(drop=True)


def by_emp_length(df: pd.DataFrame) -> pd.DataFrame:
    """Employee length analysis (bar chart), ordered < 1 year -> 10+ years."""
    return _aggregate(df, ["emp_length"]).sort_values("emp_length").reset_index(drop=True)


def by_purpose(df: pd.DataFrame) -> pd.DataFrame:
    """Loan purpose breakdown (bar chart), ranked by applications."""
    return (
        _aggregate(df, ["purpose"])
        .sort_values("total_loan_applications", ascending=False)
        .reset_index(drop=True)
    )


def by_home_ownership(df: pd.DataFrame) -> pd.DataFrame:
    """Home ownership analysis (tree map)."""
    return (
        _aggregate(df, ["home_ownership"])
        .sort_values("total_loan_applications", ascending=False)
        .reset_index(drop=True)
    )


OVERVIEW_AGGREGATIONS = {
    "by_month": by_month,
    "by_state": by_state,
    "by_term": by_term,
    "by_emp_length": by_emp_length,
    "by_purpose": by_purpose,
    "by_home_ownership": by_home_ownership,
}


def details_table(df: pd.DataFrame, limit: int | None = None) -> pd.DataFrame:
    """Flat detail grid backing the Details dashboard."""
    cols = [
        "id",
        "purpose",
        "home_ownership",
        "grade",
        "sub_grade",
        "issue_date",
        "loan_status",
        "term",
        "emp_length",
        "address_state",
        "verification_status",
        "annual_income",
        "dti",
        "int_rate",
        "installment",
        "loan_amount",
        "total_payment",
    ]
    out = df[cols].sort_values("issue_date")
    return out.head(limit) if limit else out
