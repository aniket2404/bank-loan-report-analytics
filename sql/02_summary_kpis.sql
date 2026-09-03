/* ==========================================================================
   BANK LOAN REPORT - 02 | DASHBOARD 1: SUMMARY - headline KPIs
   --------------------------------------------------------------------------
   Definitions
     MTD  = the latest month present in the data (December 2021 for this dataset)
     PMTD = the month immediately before that latest month (November 2021)
   int_rate and dti are stored as decimal fractions, so they are multiplied by
   100 for presentation.

   These queries derive MTD / PMTD from MAX(issue_date) instead of hard-coding
   month 12, so they keep working when the dataset is refreshed.
   ========================================================================== */

USE bank_loan_db;
GO

/* --------------------------------------------------------------------------
   Reporting period anchors (reused by every KPI below)
   -------------------------------------------------------------------------- */
DECLARE @max_date  DATE = (SELECT MAX(issue_date) FROM dbo.bank_loan_data);
DECLARE @mtd_start DATE = DATEFROMPARTS(YEAR(@max_date), MONTH(@max_date), 1);
DECLARE @pmtd_start DATE = DATEADD(MONTH, -1, @mtd_start);

/* --------------------------------------------------------------------------
   All five KPIs in one result set: Total / MTD / PMTD / MoM %
   -------------------------------------------------------------------------- */
WITH periods AS (
    SELECT
        CASE
            WHEN issue_date >= @mtd_start                              THEN 'MTD'
            WHEN issue_date >= @pmtd_start AND issue_date < @mtd_start THEN 'PMTD'
        END AS period,
        loan_amount,
        total_payment,
        int_rate,
        dti,
        id
    FROM dbo.bank_loan_data
),
agg AS (
    SELECT
        COUNT(id)                    AS total_applications,
        SUM(loan_amount)             AS total_funded_amount,
        SUM(total_payment)           AS total_amount_received,
        AVG(int_rate) * 100          AS avg_interest_rate,
        AVG(dti) * 100               AS avg_dti,
        COUNT(CASE WHEN period = 'MTD'  THEN id END)            AS mtd_applications,
        COUNT(CASE WHEN period = 'PMTD' THEN id END)            AS pmtd_applications,
        SUM(CASE WHEN period = 'MTD'  THEN loan_amount END)     AS mtd_funded_amount,
        SUM(CASE WHEN period = 'PMTD' THEN loan_amount END)     AS pmtd_funded_amount,
        SUM(CASE WHEN period = 'MTD'  THEN total_payment END)   AS mtd_amount_received,
        SUM(CASE WHEN period = 'PMTD' THEN total_payment END)   AS pmtd_amount_received,
        AVG(CASE WHEN period = 'MTD'  THEN int_rate END) * 100  AS mtd_avg_interest_rate,
        AVG(CASE WHEN period = 'PMTD' THEN int_rate END) * 100  AS pmtd_avg_interest_rate,
        AVG(CASE WHEN period = 'MTD'  THEN dti END) * 100       AS mtd_avg_dti,
        AVG(CASE WHEN period = 'PMTD' THEN dti END) * 100       AS pmtd_avg_dti
    FROM periods
)
SELECT
    kpi.metric,
    kpi.total_value,
    kpi.mtd_value,
    kpi.pmtd_value,
    CASE
        WHEN kpi.pmtd_value = 0 THEN NULL
        ELSE (kpi.mtd_value - kpi.pmtd_value) * 100.0 / kpi.pmtd_value
    END AS mom_pct
FROM agg
CROSS APPLY (VALUES
    ('Total Loan Applications', CAST(total_applications    AS FLOAT), CAST(mtd_applications      AS FLOAT), CAST(pmtd_applications      AS FLOAT)),
    ('Total Funded Amount',     CAST(total_funded_amount   AS FLOAT), CAST(mtd_funded_amount     AS FLOAT), CAST(pmtd_funded_amount     AS FLOAT)),
    ('Total Amount Received',   CAST(total_amount_received AS FLOAT), CAST(mtd_amount_received   AS FLOAT), CAST(pmtd_amount_received   AS FLOAT)),
    ('Average Interest Rate',   CAST(avg_interest_rate     AS FLOAT), CAST(mtd_avg_interest_rate AS FLOAT), CAST(pmtd_avg_interest_rate AS FLOAT)),
    ('Average DTI',             CAST(avg_dti               AS FLOAT), CAST(mtd_avg_dti           AS FLOAT), CAST(pmtd_avg_dti           AS FLOAT))
) AS kpi(metric, total_value, mtd_value, pmtd_value);
GO

/* --------------------------------------------------------------------------
   Individual KPI queries (handy for validating a single card on the dashboard)
   -------------------------------------------------------------------------- */

-- Total Loan Applications
SELECT COUNT(id) AS total_loan_applications FROM dbo.bank_loan_data;

-- Total Funded Amount
SELECT SUM(loan_amount) AS total_funded_amount FROM dbo.bank_loan_data;

-- Total Amount Received
SELECT SUM(total_payment) AS total_amount_received FROM dbo.bank_loan_data;

-- Average Interest Rate (%)
SELECT AVG(int_rate) * 100 AS avg_interest_rate FROM dbo.bank_loan_data;

-- Average Debt-to-Income Ratio (%)
SELECT AVG(dti) * 100 AS avg_dti FROM dbo.bank_loan_data;
GO

-- MTD versions, anchored on the latest month in the data
DECLARE @m INT = (SELECT MONTH(MAX(issue_date)) FROM dbo.bank_loan_data);
DECLARE @y INT = (SELECT YEAR(MAX(issue_date))  FROM dbo.bank_loan_data);

SELECT
    COUNT(id)           AS mtd_loan_applications,
    SUM(loan_amount)    AS mtd_funded_amount,
    SUM(total_payment)  AS mtd_amount_received,
    AVG(int_rate) * 100 AS mtd_avg_interest_rate,
    AVG(dti) * 100      AS mtd_avg_dti
FROM dbo.bank_loan_data
WHERE MONTH(issue_date) = @m AND YEAR(issue_date) = @y;

-- PMTD versions
SELECT
    COUNT(id)           AS pmtd_loan_applications,
    SUM(loan_amount)    AS pmtd_funded_amount,
    SUM(total_payment)  AS pmtd_amount_received,
    AVG(int_rate) * 100 AS pmtd_avg_interest_rate,
    AVG(dti) * 100      AS pmtd_avg_dti
FROM dbo.bank_loan_data
WHERE MONTH(issue_date) = @m - 1 AND YEAR(issue_date) = @y;
GO
