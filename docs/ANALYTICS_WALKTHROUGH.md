# Analytics Platform Walkthrough & System Architecture

This guide provides a comprehensive technical walkthrough of the **Bank Loan & Credit Risk Analytics Platform**, explaining the end-to-end data pipeline, analytical methodology, and design choices across SQL, Python, and BI layers.

---

## 1. System Design & Data Pipeline

```
Raw CSV / Database
       │
       ▼
Data Ingestion (schema.py, data_loader.py)
       │
       ├──► 4-Tier Data Quality Audit (quality.py)
       │
       ├──► Financial KPI Engine (kpis.py)
       │
       ├──► Risk & Concentration Analytics (risk.py, signals.py)
       │
       ├──► Leak-Free Predictive Modeling (model.py)
       │
       ├──► Temporal Drift & Stress Testing (monitoring.py, scenario.py)
       │
       └──► Policy Decision Engine & Multi-Tier Reports (recommendations.py, reporting.py)
```

## 2. Key Methodological Architectural Highlights

1. **Deterministic Financial Reconciliation:**
   - 100% agreement between T-SQL, pandas, DAX, and Tableau calculations.
   - Closed-loan default rates are strictly separated from portfolio active balances.

2. **Pre-Origination Feature Isolation (Leakage Prevention):**
   - Post-origination outcomes (e.g. `total_payment`, repayment timestamps) are strictly barred from predictive default models.

3. **Multi-Tier Quality Gate:**
   - Evaluates blockers, errors, warnings, and informational checks prior to publishing analytics.
