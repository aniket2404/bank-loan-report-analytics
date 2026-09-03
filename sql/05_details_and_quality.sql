/* ==========================================================================
   BANK LOAN REPORT - 05 | DASHBOARD 3: DETAILS + data quality checks
   ========================================================================== */

USE bank_loan_db;
GO

/* --------------------------------------------------------------------------
   DETAILS grid - the flat table behind Dashboard 3
   -------------------------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_loan_details AS
SELECT
    id,
    purpose,
    home_ownership,
    grade,
    sub_grade,
    issue_date,
    loan_status,
    LTRIM(RTRIM(term))    AS term,
    emp_length,
    address_state,
    verification_status,
    annual_income,
    dti        * 100      AS dti_pct,
    int_rate   * 100      AS interest_rate_pct,
    installment,
    loan_amount           AS funded_amount,
    total_payment         AS amount_received
FROM dbo.bank_loan_data;
GO

SELECT TOP (100) * FROM dbo.vw_loan_details ORDER BY issue_date;
GO

/* --------------------------------------------------------------------------
   Reusable view for the BI tools. Power BI, Excel and Tableau all connect to
   this view so the derived columns are defined once, in the database.
   -------------------------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_bank_loan_enriched AS
SELECT
    l.*,
    LTRIM(RTRIM(l.term))                    AS term_clean,
    YEAR(l.issue_date)                      AS issue_year,
    MONTH(l.issue_date)                     AS issue_month,
    DATENAME(MONTH, l.issue_date)           AS issue_month_name,
    LEFT(DATENAME(MONTH, l.issue_date), 3)  AS issue_month_short,
    CASE WHEN l.loan_status IN ('Fully Paid', 'Current')
         THEN 'Good Loan' ELSE 'Bad Loan' END AS loan_quality
FROM dbo.bank_loan_data AS l;
GO

/* --------------------------------------------------------------------------
   DATA QUALITY CHECKS
   -------------------------------------------------------------------------- */

-- 1. Row count and duplicate primary keys (expect 38576 rows, 0 duplicates)
SELECT
    COUNT(*)             AS row_count,
    COUNT(DISTINCT id)   AS distinct_ids,
    COUNT(*) - COUNT(DISTINCT id) AS duplicate_ids
FROM dbo.bank_loan_data;

-- 2. NULL counts on the columns the dashboards depend on
SELECT
    SUM(CASE WHEN issue_date     IS NULL THEN 1 ELSE 0 END) AS null_issue_date,
    SUM(CASE WHEN loan_status    IS NULL THEN 1 ELSE 0 END) AS null_loan_status,
    SUM(CASE WHEN loan_amount    IS NULL THEN 1 ELSE 0 END) AS null_loan_amount,
    SUM(CASE WHEN total_payment  IS NULL THEN 1 ELSE 0 END) AS null_total_payment,
    SUM(CASE WHEN int_rate       IS NULL THEN 1 ELSE 0 END) AS null_int_rate,
    SUM(CASE WHEN dti            IS NULL THEN 1 ELSE 0 END) AS null_dti,
    SUM(CASE WHEN emp_title      IS NULL THEN 1 ELSE 0 END) AS null_emp_title
FROM dbo.bank_loan_data;

-- 3. Distinct values of every categorical column used by a slicer
SELECT 'loan_status'         AS column_name, loan_status         AS value, COUNT(*) AS rows FROM dbo.bank_loan_data GROUP BY loan_status
UNION ALL SELECT 'term',                LTRIM(RTRIM(term)),  COUNT(*) FROM dbo.bank_loan_data GROUP BY LTRIM(RTRIM(term))
UNION ALL SELECT 'grade',               grade,               COUNT(*) FROM dbo.bank_loan_data GROUP BY grade
UNION ALL SELECT 'home_ownership',      home_ownership,      COUNT(*) FROM dbo.bank_loan_data GROUP BY home_ownership
UNION ALL SELECT 'verification_status', verification_status, COUNT(*) FROM dbo.bank_loan_data GROUP BY verification_status
ORDER BY column_name, value;

-- 4. Ranges of the numeric measures (catches bad imports and stray negatives)
SELECT
    MIN(loan_amount)   AS min_loan_amount,   MAX(loan_amount)   AS max_loan_amount,
    MIN(total_payment) AS min_total_payment, MAX(total_payment) AS max_total_payment,
    MIN(int_rate)      AS min_int_rate,      MAX(int_rate)      AS max_int_rate,
    MIN(dti)           AS min_dti,           MAX(dti)           AS max_dti,
    MIN(annual_income) AS min_annual_income, MAX(annual_income) AS max_annual_income
FROM dbo.bank_loan_data;

-- 5. Recovery rate by status - a quick reasonableness check on the load
SELECT
    loan_status,
    SUM(total_payment) * 100.0 / NULLIF(SUM(loan_amount), 0) AS recovery_pct
FROM dbo.bank_loan_data
GROUP BY loan_status
ORDER BY recovery_pct DESC;
GO
