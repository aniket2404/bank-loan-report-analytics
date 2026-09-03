/* ==========================================================================
   BANK LOAN REPORT - 04 | DASHBOARD 2: OVERVIEW
   One query per required chart. Every query returns the same three measures:
   Total Loan Applications, Total Funded Amount, Total Amount Received.
   ========================================================================== */

USE bank_loan_db;
GO

/* --------------------------------------------------------------------------
   1. Monthly Trends by Issue Date  ->  Line chart
   -------------------------------------------------------------------------- */
SELECT
    MONTH(issue_date)                 AS month_number,
    DATENAME(MONTH, issue_date)       AS month_name,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY MONTH(issue_date), DATENAME(MONTH, issue_date)
ORDER BY month_number;
GO

/* --------------------------------------------------------------------------
   2. Regional Analysis by State  ->  Filled map
   -------------------------------------------------------------------------- */
SELECT
    address_state                     AS state,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY address_state
ORDER BY total_funded_amount DESC;
GO

/* --------------------------------------------------------------------------
   3. Loan Term Analysis  ->  Donut chart
   -------------------------------------------------------------------------- */
SELECT
    LTRIM(RTRIM(term))                AS term,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY LTRIM(RTRIM(term))
ORDER BY term;
GO

/* --------------------------------------------------------------------------
   4. Employee Length Analysis  ->  Bar chart
   emp_length is text, so an explicit sort key keeps "< 1 year" first and
   "10+ years" last instead of sorting alphabetically.
   -------------------------------------------------------------------------- */
SELECT
    emp_length                        AS employee_length,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY emp_length
ORDER BY
    CASE emp_length
        WHEN '< 1 year'  THEN 0
        WHEN '1 year'    THEN 1
        WHEN '2 years'   THEN 2
        WHEN '3 years'   THEN 3
        WHEN '4 years'   THEN 4
        WHEN '5 years'   THEN 5
        WHEN '6 years'   THEN 6
        WHEN '7 years'   THEN 7
        WHEN '8 years'   THEN 8
        WHEN '9 years'   THEN 9
        WHEN '10+ years' THEN 10
        ELSE 99
    END;
GO

/* --------------------------------------------------------------------------
   5. Loan Purpose Breakdown  ->  Bar chart
   -------------------------------------------------------------------------- */
SELECT
    purpose,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY purpose
ORDER BY total_loan_applications DESC;
GO

/* --------------------------------------------------------------------------
   6. Home Ownership Analysis  ->  Tree map
   -------------------------------------------------------------------------- */
SELECT
    home_ownership,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
GROUP BY home_ownership
ORDER BY total_loan_applications DESC;
GO

/* --------------------------------------------------------------------------
   Bonus: the same breakdowns with a dashboard filter applied.
   Every Overview visual is sliced by grade, sub_grade, purpose, term,
   home_ownership, verification_status, address_state and issue_date, so add a
   WHERE clause to reproduce a filtered dashboard state. Example - grade A only:
   -------------------------------------------------------------------------- */
SELECT
    purpose,
    COUNT(id)                         AS total_loan_applications,
    SUM(loan_amount)                  AS total_funded_amount,
    SUM(total_payment)                AS total_amount_received
FROM dbo.bank_loan_data
WHERE grade = 'A'
GROUP BY purpose
ORDER BY total_loan_applications DESC;
GO
