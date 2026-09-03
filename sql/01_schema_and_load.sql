/* ==========================================================================
   BANK LOAN REPORT - 01 | Database, table and data load (Microsoft SQL Server)
   --------------------------------------------------------------------------
   Run order: 01 -> 02 -> 03 -> 04 -> 05
   Source file: financial_loan.csv  (38,576 rows, 24 columns)
   ========================================================================== */

/* --------------------------------------------------------------------------
   1. Database
   -------------------------------------------------------------------------- */
IF DB_ID('bank_loan_db') IS NULL
    CREATE DATABASE bank_loan_db;
GO

USE bank_loan_db;
GO

/* --------------------------------------------------------------------------
   2. Table
   The standard imports the CSV with the SQL Server Import Flat File wizard,
   which infers these types. Creating the table explicitly makes the project
   reproducible and keeps the date columns as real DATE values.
   -------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.bank_loan_data', 'U') IS NOT NULL
    DROP TABLE dbo.bank_loan_data;
GO

CREATE TABLE dbo.bank_loan_data (
    id                     INT           NOT NULL,
    address_state          VARCHAR(10)   NULL,
    application_type       VARCHAR(20)   NULL,
    emp_length             VARCHAR(20)   NULL,
    emp_title              VARCHAR(150)  NULL,
    grade                  VARCHAR(5)    NULL,
    home_ownership         VARCHAR(20)   NULL,
    issue_date             DATE          NULL,
    last_credit_pull_date  DATE          NULL,
    last_payment_date      DATE          NULL,
    loan_status            VARCHAR(25)   NULL,
    next_payment_date      DATE          NULL,
    member_id              INT           NULL,
    purpose                VARCHAR(50)   NULL,
    sub_grade              VARCHAR(5)    NULL,
    term                   VARCHAR(15)   NULL,
    verification_status    VARCHAR(25)   NULL,
    annual_income          FLOAT         NULL,
    dti                    FLOAT         NULL,
    installment            FLOAT         NULL,
    int_rate               FLOAT         NULL,
    loan_amount            INT           NULL,
    total_acc              INT           NULL,
    total_payment          INT           NULL,
    CONSTRAINT pk_bank_loan_data PRIMARY KEY (id)
);
GO

/* --------------------------------------------------------------------------
   3. Load the CSV
   Option A - Import Flat File wizard (standard implementation):
       Right-click bank_loan_db > Tasks > Import Flat File... > financial_loan.csv
       Keep the column names, and set the four *_date columns to DATE.

   Option B - BULK INSERT (scripted, repeatable).
   The CSV stores dates as DD-MM-YYYY, so set DATEFORMAT before loading.
   Update the file path to match your machine.
   -------------------------------------------------------------------------- */
SET DATEFORMAT dmy;
GO

-- BULK INSERT dbo.bank_loan_data
-- FROM 'C:\path\to\bank-loan-report-analytics\data\raw\financial_loan.csv'
-- WITH (
--     FORMAT           = 'CSV',
--     FIRSTROW         = 2,
--     FIELDTERMINATOR = ',',
--     ROWTERMINATOR   = '0x0a',
--     TABLOCK,
--     MAXERRORS        = 0
-- );
-- GO

/* --------------------------------------------------------------------------
   4. Helpful indexes for the dashboard queries
   -------------------------------------------------------------------------- */
CREATE INDEX ix_bank_loan_data_issue_date   ON dbo.bank_loan_data (issue_date);
CREATE INDEX ix_bank_loan_data_loan_status  ON dbo.bank_loan_data (loan_status);
CREATE INDEX ix_bank_loan_data_state        ON dbo.bank_loan_data (address_state);
GO

/* --------------------------------------------------------------------------
   5. Post-load sanity checks - expected values for the lending dataset
        row_count            = 38576
        distinct_statuses    = 3   (Fully Paid, Current, Charged Off)
        min/max issue_date   = 2021-01-01 .. 2021-12-12
   -------------------------------------------------------------------------- */
SELECT
    COUNT(*)                        AS row_count,
    COUNT(DISTINCT loan_status)     AS distinct_statuses,
    MIN(issue_date)                 AS first_issue_date,
    MAX(issue_date)                 AS last_issue_date,
    SUM(CASE WHEN issue_date IS NULL THEN 1 ELSE 0 END) AS null_issue_dates
FROM dbo.bank_loan_data;
GO

/* --------------------------------------------------------------------------
   6. Production Reusable Views (Staging, Enriched Analytics, and KPI Reporting)
   -------------------------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_stg_bank_loan AS
SELECT
    id,
    LTRIM(RTRIM(address_state))        AS address_state,
    LTRIM(RTRIM(application_type))     AS application_type,
    LTRIM(RTRIM(emp_length))           AS emp_length,
    LTRIM(RTRIM(emp_title))            AS emp_title,
    LTRIM(RTRIM(grade))                AS grade,
    LTRIM(RTRIM(home_ownership))       AS home_ownership,
    issue_date,
    last_credit_pull_date,
    last_payment_date,
    LTRIM(RTRIM(loan_status))          AS loan_status,
    next_payment_date,
    member_id,
    LTRIM(RTRIM(purpose))              AS purpose,
    LTRIM(RTRIM(sub_grade))            AS sub_grade,
    LTRIM(RTRIM(term))                 AS term,
    LTRIM(RTRIM(verification_status))  AS verification_status,
    annual_income,
    dti,
    installment,
    int_rate,
    loan_amount,
    total_acc,
    total_payment
FROM dbo.bank_loan_data;
GO

CREATE OR ALTER VIEW dbo.vw_enriched_bank_loan AS
SELECT
    id,
    address_state,
    application_type,
    emp_length,
    emp_title,
    grade,
    home_ownership,
    issue_date,
    DATEPART(YEAR, issue_date)         AS issue_year,
    DATEPART(MONTH, issue_date)        AS issue_month,
    DATENAME(MONTH, issue_date)        AS issue_month_name,
    last_credit_pull_date,
    last_payment_date,
    loan_status,
    CASE
        WHEN loan_status IN ('Fully Paid', 'Current') THEN 'Good Loan'
        WHEN loan_status = 'Charged Off'              THEN 'Bad Loan'
        ELSE 'Unclassified'
    END                                AS loan_quality,
    CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END AS is_charged_off,
    CASE WHEN loan_status IN ('Fully Paid', 'Charged Off') THEN 1 ELSE 0 END AS is_closed,
    next_payment_date,
    member_id,
    purpose,
    sub_grade,
    term,
    verification_status,
    annual_income,
    dti,
    dti * 100.0                        AS dti_pct,
    installment,
    int_rate,
    int_rate * 100.0                   AS int_rate_pct,
    loan_amount,
    total_acc,
    total_payment,
    total_payment - loan_amount        AS net_margin
FROM dbo.vw_stg_bank_loan;
GO

CREATE OR ALTER VIEW dbo.vw_kpi_summary AS
SELECT
    COUNT(id)                          AS total_loan_applications,
    SUM(loan_amount)                   AS total_funded_amount,
    SUM(total_payment)                 AS total_amount_received,
    AVG(int_rate * 100.0)              AS avg_interest_rate,
    AVG(dti * 100.0)                   AS avg_dti,
    SUM(total_payment) - SUM(loan_amount) AS net_cash_margin,
    CAST(SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(id) * 100.0 AS default_rate_pct
FROM dbo.vw_enriched_bank_loan;
GO

