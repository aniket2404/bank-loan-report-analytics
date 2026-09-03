"""Central configuration for the Bank Loan Report project.

All values can be overridden with environment variables (see ``.env.example``).
No secrets are hard-coded in this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

try:  # optional dependency, only needed for local .env files
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
SAMPLE_DATA_DIR = DATA_DIR / "sample"
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", PROJECT_ROOT / "reports"))
FIGURES_DIR = REPORTS_DIR / "figures"
TABLES_DIR = REPORTS_DIR / "tables"

# Sample runs write here instead of over the committed full-dataset artefacts.
# Without this split, `--sample charts` silently overwrites reports/figures/ with
# 600-row charts, and the next commit publishes them as if they were the real
# thing. That happened once; this is the fix.
SAMPLE_REPORTS_DIR = REPORTS_DIR / "sample"
SAMPLE_FIGURES_DIR = SAMPLE_REPORTS_DIR / "figures"
SAMPLE_TABLES_DIR = SAMPLE_REPORTS_DIR / "tables"

# Primary dataset used by the standard.
RAW_CSV_NAME = os.getenv("RAW_CSV_NAME", "financial_loan.csv")
RAW_CSV_PATH = RAW_DATA_DIR / RAW_CSV_NAME
SAMPLE_CSV_PATH = SAMPLE_DATA_DIR / "financial_loan_sample.csv"

# Date columns stored as DD-MM-YYYY strings in the source CSV.
DATE_COLUMNS = (
    "issue_date",
    "last_credit_pull_date",
    "last_payment_date",
    "next_payment_date",
)
SOURCE_DATE_FORMAT = "%d-%m-%Y"

# Business rules from the problem statement.
GOOD_LOAN_STATUSES = ("Fully Paid", "Current")
BAD_LOAN_STATUSES = ("Charged Off",)

TABLE_NAME = os.getenv("DB_TABLE", "bank_loan_data")


@dataclass(frozen=True)
class DatabaseSettings:
    """SQL Server connection settings, read from the environment."""

    server: str = field(default_factory=lambda: os.getenv("DB_SERVER", "localhost"))
    port: str = field(default_factory=lambda: os.getenv("DB_PORT", "1433"))
    database: str = field(default_factory=lambda: os.getenv("DB_NAME", "bank_loan_db"))
    username: str | None = field(default_factory=lambda: os.getenv("DB_USER"))
    password: str | None = field(default_factory=lambda: os.getenv("DB_PASSWORD"))
    driver: str = field(
        default_factory=lambda: os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    )
    trusted_connection: bool = field(
        default_factory=lambda: os.getenv("DB_TRUSTED_CONNECTION", "no").lower()
        in {"1", "true", "yes"}
    )

    def sqlalchemy_url(self) -> str:
        """Build a SQLAlchemy URL for pyodbc without ever printing credentials."""
        driver = quote_plus(self.driver)
        if self.trusted_connection:
            return (
                f"mssql+pyodbc://{self.server},{self.port}/{self.database}"
                f"?driver={driver}&trusted_connection=yes"
            )
        if not self.username or not self.password:
            raise RuntimeError(
                "DB_USER and DB_PASSWORD must be set (or enable DB_TRUSTED_CONNECTION)."
            )
        user = quote_plus(self.username)
        pwd = quote_plus(self.password)
        return (
            f"mssql+pyodbc://{user}:{pwd}@{self.server},{self.port}/{self.database}"
            f"?driver={driver}"
        )


def ensure_output_dirs() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
