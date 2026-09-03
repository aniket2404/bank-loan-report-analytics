/* ==========================================================================
   BANK LOAN REPORT - 03 | DASHBOARD 1: SUMMARY
   Good Loan vs Bad Loan KPIs + Loan Status grid view
   --------------------------------------------------------------------------
   Business rule from the problem statement:
     Good Loan = loan_status IN ('Fully Paid', 'Current')
     Bad Loan  = loan_status  =  'Charged Off'
   ========================================================================== */

USE bank_loan_db;
GO

/* --------------------------------------------------------------------------
   Good vs Bad loan block - both categories in a single result set
   -------------------------------------------------------------------------- */
SELECT
    quality.category,
    COUNT(*)                                                       AS applications,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ()                       AS application_pct,
    SUM(loan_amount)                                               AS funded_amount,
    SUM(total_payment)                                             AS amount_received
FROM dbo.bank_loan_data AS l
CROSS APPLY (VALUES (
    CASE WHEN l.loan_status IN ('Fully Paid', 'Current') THEN 'Good Loan'
         ELSE 'Bad Loan'
    END
)) AS quality(category)
GROUP BY quality.category
ORDER BY quality.category;
GO

/* --------------------------------------------------------------------------
   Individual Good Loan KPIs
   -------------------------------------------------------------------------- */
SELECT
    COUNT(CASE WHEN loan_status IN ('Fully Paid', 'Current') THEN id END) * 100.0
        / COUNT(id) AS good_loan_percentage
FROM dbo.bank_loan_data;

SELECT
    COUNT(id)          AS good_loan_applications,
    SUM(loan_amount)   AS good_loan_funded_amount,
    SUM(total_payment) AS good_loan_amount_received
FROM dbo.bank_loan_data
WHERE loan_status IN ('Fully Paid', 'Current');
GO

/* --------------------------------------------------------------------------
   Individual Bad Loan KPIs
   -------------------------------------------------------------------------- */
SELECT
    COUNT(CASE WHEN loan_status = 'Charged Off' THEN id END) * 100.0
        / COUNT(id) AS bad_loan_percentage
FROM dbo.bank_loan_data;

SELECT
    COUNT(id)          AS bad_loan_applications,
    SUM(loan_amount)   AS bad_loan_funded_amount,
    SUM(total_payment) AS bad_loan_amount_received
FROM dbo.bank_loan_data
WHERE loan_status = 'Charged Off';
GO

/* --------------------------------------------------------------------------
   LOAN STATUS GRID VIEW
   One row per loan_status with total and MTD measures side by side.
   -------------------------------------------------------------------------- */
DECLARE @max_date  DATE = (SELECT MAX(issue_date) FROM dbo.bank_loan_data);
DECLARE @mtd_start DATE = DATEFROMPARTS(YEAR(@max_date), MONTH(@max_date), 1);

SELECT
    loan_status,
    COUNT(id)                                                                   AS total_loan_applications,
    SUM(loan_amount)                                                            AS total_funded_amount,
    SUM(total_payment)                                                          AS total_amount_received,
    SUM(CASE WHEN issue_date >= @mtd_start THEN loan_amount   ELSE 0 END)        AS mtd_funded_amount,
    SUM(CASE WHEN issue_date >= @mtd_start THEN total_payment ELSE 0 END)        AS mtd_amount_received,
    AVG(int_rate) * 100                                                         AS avg_interest_rate,
    AVG(dti) * 100                                                              AS avg_dti
FROM dbo.bank_loan_data
GROUP BY loan_status
ORDER BY loan_status;
GO
