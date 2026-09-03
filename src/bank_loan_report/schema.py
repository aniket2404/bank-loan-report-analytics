"""Schema contracts, domain rules, and validation types for Bank Loan Analytics.

Defines all expected fields, allowed categorical sets, numeric ranges,
and typing constraints that govern the lending data pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# All 24 source columns expected in the dataset
SOURCE_COLUMNS: list[str] = [
    "id",
    "address_state",
    "application_type",
    "emp_length",
    "emp_title",
    "grade",
    "home_ownership",
    "issue_date",
    "last_credit_pull_date",
    "last_payment_date",
    "loan_status",
    "next_payment_date",
    "member_id",
    "purpose",
    "sub_grade",
    "term",
    "verification_status",
    "annual_income",
    "dti",
    "installment",
    "int_rate",
    "loan_amount",
    "total_acc",
    "total_payment",
]

# Derived columns produced by the clean_loans transformation
DERIVED_COLUMNS: list[str] = [
    "issue_month",
    "issue_year",
    "issue_month_name",
    "issue_month_short",
    "loan_quality",
]

# Date columns stored as DD-MM-YYYY strings in the source CSV
DATE_COLUMNS: tuple[str, ...] = (
    "issue_date",
    "last_credit_pull_date",
    "last_payment_date",
    "next_payment_date",
)

# Numeric fields with domain constraints
NUMERIC_COLUMNS: tuple[str, ...] = (
    "annual_income",
    "dti",
    "installment",
    "int_rate",
    "loan_amount",
    "total_acc",
    "total_payment",
)

# Categorical fields
CATEGORICAL_COLUMNS: tuple[str, ...] = (
    "address_state",
    "application_type",
    "emp_length",
    "grade",
    "home_ownership",
    "loan_status",
    "purpose",
    "sub_grade",
    "term",
    "verification_status",
)

# Key identifiers
IDENTIFIER_COLUMNS: tuple[str, ...] = ("id", "member_id")

# Allowed categorical domains
VALID_TERMS: frozenset[str] = frozenset(["36 months", "60 months"])
VALID_GRADES: frozenset[str] = frozenset(["A", "B", "C", "D", "E", "F", "G"])
VALID_SUBGRADES: frozenset[str] = frozenset(
    [f"{g}{i}" for g in "ABCDEFG" for i in range(1, 6)]
)
VALID_LOAN_STATUSES: frozenset[str] = frozenset(["Fully Paid", "Current", "Charged Off"])
GOOD_LOAN_STATUSES: tuple[str, ...] = ("Fully Paid", "Current")
BAD_LOAN_STATUSES: tuple[str, ...] = ("Charged Off",)

VALID_HOME_OWNERSHIPS: frozenset[str] = frozenset(["RENT", "MORTGAGE", "OWN", "OTHER", "NONE"])
VALID_VERIFICATION_STATUSES: frozenset[str] = frozenset(
    ["Verified", "Source Verified", "Not Verified"]
)
VALID_APPLICATION_TYPES: frozenset[str] = frozenset(["INDIVIDUAL", "JOINT"])

EMP_LENGTH_ORDER: list[str] = [
    "< 1 year",
    "1 year",
    "2 years",
    "3 years",
    "4 years",
    "5 years",
    "6 years",
    "7 years",
    "8 years",
    "9 years",
    "10+ years",
]

# Numeric boundary rules (min, max)
NUMERIC_BOUNDS: dict[str, dict[str, float]] = {
    "loan_amount": {"min": 500.0, "max": 100_000.0},
    "total_payment": {"min": 0.0, "max": 200_000.0},
    "annual_income": {"min": 0.0, "max": 10_000_000.0},
    "installment": {"min": 0.0, "max": 5_000.0},
    "int_rate": {"min": 0.001, "max": 1.0},
    "dti": {"min": 0.0, "max": 1.5},
    "total_acc": {"min": 1.0, "max": 200.0},
}

SeverityLevel = Literal["BLOCKER", "ERROR", "WARNING", "INFO"]


@dataclass(frozen=True)
class ColumnContract:
    """Specification for a single dataset column."""

    name: str
    dtype: str
    nullable: bool
    description: str
    is_kpi_driver: bool = False
    is_pre_origination: bool = False
