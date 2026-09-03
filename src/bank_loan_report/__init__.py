"""Bank Loan Report - end-to-end lending analytics.

Layers
------
``config``       environment-driven settings and the shared business rules
``data_loader``  loading, cleaning and profiling the source data
``validate``     executable data-quality contract (FAIL / WARN / INFO checks)
``kpis``         the dashboard KPI layer, mirroring ``sql/02``-``sql/04``
``risk``         risk and profitability analysis, mirroring ``sql/06``
``charts``       the six Overview dashboard visuals
``risk_charts``  visuals for the risk findings
``cli``          ``python -m bank_loan_report <command>``
"""

__version__ = "2.0.0"

from . import charts, config, data_loader, kpis, risk, risk_charts, validate  # noqa: F401

__all__ = [
    "charts",
    "config",
    "data_loader",
    "kpis",
    "risk",
    "risk_charts",
    "validate",
    "__version__",
]
