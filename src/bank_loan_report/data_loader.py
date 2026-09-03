"""Data loading and cleaning for the Bank Loan Report project."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config

EXPECTED_COLUMNS = [
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

EMP_LENGTH_ORDER = [
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


def resolve_data_path(path: str | Path | None = None, *, use_sample: bool = False) -> Path:
    """Pick the dataset to use: explicit path > raw CSV > bundled sample."""
    if path is not None:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Dataset not found: {resolved}")
        return resolved
    if use_sample:
        return config.SAMPLE_CSV_PATH
    if config.RAW_CSV_PATH.exists():
        return config.RAW_CSV_PATH
    if config.SAMPLE_CSV_PATH.exists():
        return config.SAMPLE_CSV_PATH
    raise FileNotFoundError(
        f"No dataset found. Place '{config.RAW_CSV_NAME}' in {config.RAW_DATA_DIR} "
        "(see data/README.md for the download link)."
    )


def load_loans(
    path: str | Path | None = None,
    *,
    use_sample: bool = False,
    clean: bool = True,
) -> pd.DataFrame:
    """Load the loan dataset into a tidy DataFrame."""
    csv_path = resolve_data_path(path, use_sample=use_sample)
    df = pd.read_csv(csv_path)

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing expected columns: {missing}")

    return clean_loans(df) if clean else df


def clean_loans(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the cleaning steps needed by every downstream calculation.

    * parse the four DD-MM-YYYY date columns into real datetimes
    * strip the leading space from ``term`` values (" 36 months" -> "36 months")
    * normalise whitespace on the remaining text columns
    * add helper columns used by the charts (month number, month name, loan quality)
    * order ``emp_length`` as an ordered categorical so bar charts sort correctly
    """
    out = df.copy()

    for col in config.DATE_COLUMNS:
        if col in out.columns:
            s = out[col].astype("string").str.strip().str.replace("/", "-")
            parsed = pd.to_datetime(s, format=config.SOURCE_DATE_FORMAT, errors="coerce")
            if parsed.isna().any():
                fallback = pd.to_datetime(s, dayfirst=True, errors="coerce")
                parsed = parsed.fillna(fallback)
            out[col] = parsed

    text_cols = out.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        out[col] = out[col].astype("string").str.strip()

    out["issue_month"] = out["issue_date"].dt.month
    out["issue_year"] = out["issue_date"].dt.year
    out["issue_month_name"] = out["issue_date"].dt.strftime("%B")
    out["issue_month_short"] = out["issue_date"].dt.strftime("%b")

    # Classify explicitly instead of "anything that isn't good is bad": an
    # unrecognised status must surface as Unclassified so validate.py can flag
    # it, rather than silently inflating the Bad Loan KPI.
    good = set(config.GOOD_LOAN_STATUSES)
    bad = set(config.BAD_LOAN_STATUSES)

    def _classify(status: object) -> str:
        if status in good:
            return "Good Loan"
        if status in bad:
            return "Bad Loan"
        return "Unclassified"

    out["loan_quality"] = out["loan_status"].apply(_classify)

    if "emp_length" in out.columns:
        present = [v for v in EMP_LENGTH_ORDER if v in set(out["emp_length"].dropna())]
        out["emp_length"] = pd.Categorical(
            out["emp_length"], categories=present, ordered=True
        )

    return out


def data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column null count, null share, dtype and distinct-value count."""
    return pd.DataFrame(
        {
            "dtype": df.dtypes.astype(str),
            "nulls": df.isna().sum(),
            "null_pct": (df.isna().mean() * 100).round(2),
            "distinct": df.nunique(dropna=True),
        }
    ).sort_values("nulls", ascending=False)
