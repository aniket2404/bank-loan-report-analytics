/* ==========================================================================
   BANK LOAN REPORT - 06 | Risk, ranking and cohort analysis (T-SQL)
   --------------------------------------------------------------------------
   Run order: 01 -> 02 -> 03 -> 04 -> 05 -> 06

   WHY THIS FILE EXISTS
   Scripts 02-05 reproduce the dashboard KPIs: they are aggregation queries
   that answer "how much" and "how many". They deliberately mirror the Power BI
   measures one-for-one so the two layers can be reconciled.

   This script answers the questions the dashboard does NOT: which segments
   lose money, how each segment ranks against its peers, how the portfolio
   accumulates over the year, and whether risk-based pricing actually held.
   Those questions need CTEs, window functions and self-joins rather than
   plain GROUP BY, so this file is also where the SQL in this repository
   demonstrates that toolset.

   IMPORTANT - the results of this script are reproduced and unit-tested in
   Python (src/bank_loan_report/risk.py, tests/test_risk.py). Every number
   below has a Python counterpart, which is how the two layers cross-check
   each other. See docs/VERIFICATION.md.

   CONVENTIONS USED THROUGHOUT
     * Good loan  = loan_status IN ('Fully Paid', 'Current')
     * Bad loan   = loan_status  = 'Charged Off'
     * int_rate and dti are stored as decimal fractions (0.1104 = 11.04%),
       so they are multiplied by 100 exactly once, at presentation time.
     * "recovery rate" = SUM(total_payment) / SUM(loan_amount). Above 100%
       means interest collected has exceeded principal lent.
     * A default rate computed over ALL loans understates risk, because loans
       still 'Current' have not had the chance to default yet. Sections that
       measure realised credit risk therefore use only CLOSED loans
       ('Fully Paid' + 'Charged Off') as the denominator, and say so.
   ========================================================================== */

USE bank_loan_db;
GO

SET DATEFORMAT dmy;
GO


/* ==========================================================================
   1. Portfolio economics - is the book actually profitable?
   --------------------------------------------------------------------------
   Business question: for every rupee/dollar lent, how much came back, and
   which loan status destroys value?

   Technique: GROUP BY with window functions (SUM ... OVER ()) to express each
   status as a share of the whole book without a second pass over the table or
   a subquery. This is the single most useful window-function pattern in
   analytics: a row-level value next to its grand total.
   ========================================================================== */
WITH status_economics AS (
    SELECT
        loan_status,
        COUNT(*)                AS loans,
        SUM(loan_amount)        AS funded,
        SUM(total_payment)      AS received,
        SUM(total_payment) - SUM(loan_amount) AS net_cash
    FROM dbo.bank_loan_data
    GROUP BY loan_status
)
SELECT
    loan_status,
    loans,
    funded,
    received,
    net_cash,
    CAST(received * 100.0 / NULLIF(funded, 0)          AS DECIMAL(8, 2)) AS recovery_pct,
    -- window functions: share of the total book
    CAST(loans  * 100.0 / SUM(loans)  OVER ()          AS DECIMAL(8, 2)) AS pct_of_loans,
    CAST(funded * 100.0 / SUM(funded) OVER ()          AS DECIMAL(8, 2)) AS pct_of_funded,
    -- net cash of this status expressed against the whole book's funding
    CAST(net_cash * 100.0 / SUM(funded) OVER ()        AS DECIMAL(8, 2)) AS net_cash_pct_of_funded
FROM status_economics
ORDER BY net_cash;
GO
/* Expected (full 38,576-row dataset):
     Charged Off  5,333 loans   65,532,225 funded   37,284,763 received
                  recovery 56.90%   net -28,247,462  (-6.48% of total funded)
     Current      1,098          18,866,500         24,199,914   128.27%
     Fully Paid  32,145         351,358,350        411,586,256   117.14%
   Whole book: 435,757,075 funded, 473,070,933 received, net +37,313,858
               (recovery 108.56%). The book is profitable overall; charge-offs
               cost 6.48% of everything lent. */


/* ==========================================================================
   2. Credit-grade gradient with RANK and LAG
   --------------------------------------------------------------------------
   Business question: does default risk rise monotonically with the credit
   grade the bank assigned, and does the interest rate rise with it?

   Techniques:
     * CTE to build the per-grade aggregate once
     * RANK()   - order grades by realised default rate
     * LAG()    - the step change from the previous (better) grade
     * SUM() OVER (ORDER BY ...) - running share of the portfolio, which shows
       how much of the book sits in the safe grades
   ========================================================================== */
WITH grade_stats AS (
    SELECT
        grade,
        COUNT(*)                                                       AS loans,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END)   AS charged_off,
        SUM(loan_amount)                                               AS funded,
        SUM(total_payment)                                             AS received,
        AVG(int_rate) * 100.0                                          AS avg_int_rate_pct
    FROM dbo.bank_loan_data
    GROUP BY grade
),
grade_rates AS (
    SELECT
        grade,
        loans,
        charged_off,
        funded,
        received,
        CAST(avg_int_rate_pct AS DECIMAL(8, 2))                              AS avg_int_rate_pct,
        CAST(charged_off * 100.0 / NULLIF(loans, 0) AS DECIMAL(8, 2))        AS default_rate_pct,
        CAST(received * 100.0 / NULLIF(funded, 0)   AS DECIMAL(8, 2))        AS recovery_pct,
        received - funded                                                     AS net_cash
    FROM grade_stats
)
SELECT
    grade,
    loans,
    default_rate_pct,
    avg_int_rate_pct,
    recovery_pct,
    net_cash,
    RANK() OVER (ORDER BY default_rate_pct DESC)                    AS risk_rank,
    -- change in default rate versus the next-better grade
    CAST(default_rate_pct
         - LAG(default_rate_pct) OVER (ORDER BY grade)
         AS DECIMAL(8, 2))                                          AS default_rate_step_vs_prev_grade,
    CAST(avg_int_rate_pct
         - LAG(avg_int_rate_pct) OVER (ORDER BY grade)
         AS DECIMAL(8, 2))                                          AS int_rate_step_vs_prev_grade,
    -- cumulative share of the funded book, walking from grade A downwards
    CAST(SUM(funded) OVER (ORDER BY grade ROWS UNBOUNDED PRECEDING)
         * 100.0 / SUM(funded) OVER ()
         AS DECIMAL(8, 2))                                          AS cumulative_pct_of_funded
FROM grade_rates
ORDER BY grade;
GO
/* Expected: default rate climbs A 5.70% -> B 11.50% -> C 16.02% -> D 20.69%
   -> E 24.80% -> F 30.25% -> G 31.31%, and the average interest rate climbs
   with it (7.35% -> 21.40%). The grading model is directionally sound, and
   every grade still recovers more than 100% of principal, so the bank is
   paid for the extra risk it takes. */


/* ==========================================================================
   3. Sub-grade risk ranking - the worst pockets in the book
   --------------------------------------------------------------------------
   Business question: which specific sub-grades should underwriting review?

   Techniques: ROW_NUMBER() to take a Top-N, PARTITION BY to rank sub-grades
   WITHIN their parent grade (so we can see the worst A, the worst B, and so
   on), and NTILE() to bucket sub-grades into risk quartiles.

   The HAVING clause enforces a minimum volume: a 46% default rate on 115
   loans is a real signal, but a 100% default rate on 3 loans is noise. Every
   segment cut in this project applies a minimum-count floor for that reason.
   ========================================================================== */
WITH sub_grade_stats AS (
    SELECT
        grade,
        sub_grade,
        COUNT(*)                                                     AS loans,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) AS charged_off,
        AVG(int_rate) * 100.0                                        AS avg_int_rate_pct,
        SUM(total_payment) - SUM(loan_amount)                        AS net_cash
    FROM dbo.bank_loan_data
    GROUP BY grade, sub_grade
    HAVING COUNT(*) >= 20          -- volume floor: ignore statistically thin buckets
),
ranked AS (
    SELECT
        grade,
        sub_grade,
        loans,
        CAST(charged_off * 100.0 / loans AS DECIMAL(8, 2)) AS default_rate_pct,
        CAST(avg_int_rate_pct           AS DECIMAL(8, 2)) AS avg_int_rate_pct,
        net_cash,
        ROW_NUMBER() OVER (ORDER BY charged_off * 1.0 / loans DESC)        AS overall_risk_rank,
        ROW_NUMBER() OVER (PARTITION BY grade
                           ORDER BY charged_off * 1.0 / loans DESC)       AS risk_rank_in_grade,
        NTILE(4)     OVER (ORDER BY charged_off * 1.0 / loans DESC)        AS risk_quartile
    FROM sub_grade_stats
)
SELECT *
FROM ranked
WHERE overall_risk_rank <= 10        -- the ten riskiest sub-grades in the book
ORDER BY overall_risk_rank;
GO
/* Expected top of the list: F5 46.09% (115 loans), G3 39.58%, G2 35.90%,
   G5 33.33%, F4 31.90%. For contrast the safest are A1 2.28%, A2 4.65%,
   A3 5.11% - a 20x spread between the best and worst sub-grade. */


/* ==========================================================================
   4. Monthly origination cohorts with running totals and MoM growth
   --------------------------------------------------------------------------
   Business question: how fast did lending grow through 2021, and did the
   quality of what we originated drift as volume grew?

   Techniques: date truncation into a month key, LAG() for month-on-month
   growth, and SUM() OVER (ORDER BY ...) for a running (year-to-date) total.

   CAUTION - this is an ORIGINATION cohort view, not a vintage-performance
   view. The non-issue_date columns in this dataset are not internally
   consistent (40.1% of rows have last_payment_date BEFORE issue_date), so a
   true vintage curve - "of the loans issued in March, how many had defaulted
   by month 6" - cannot be built from this data. The default rate below is
   therefore the FINAL observed status of each month's cohort, not a
   time-to-default measure. See docs/DATA_QUALITY.md.
   ========================================================================== */
WITH monthly AS (
    SELECT
        DATEFROMPARTS(YEAR(issue_date), MONTH(issue_date), 1)        AS issue_month,
        COUNT(*)                                                     AS applications,
        SUM(loan_amount)                                             AS funded,
        SUM(total_payment)                                           AS received,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) AS charged_off,
        AVG(int_rate) * 100.0                                        AS avg_int_rate_pct
    FROM dbo.bank_loan_data
    GROUP BY DATEFROMPARTS(YEAR(issue_date), MONTH(issue_date), 1)
)
SELECT
    issue_month,
    applications,
    funded,
    received,
    CAST(charged_off * 100.0 / NULLIF(applications, 0) AS DECIMAL(8, 2)) AS cohort_default_rate_pct,
    CAST(avg_int_rate_pct AS DECIMAL(8, 2))                             AS avg_int_rate_pct,
    -- running (year-to-date) totals
    SUM(applications) OVER (ORDER BY issue_month ROWS UNBOUNDED PRECEDING) AS ytd_applications,
    SUM(funded)       OVER (ORDER BY issue_month ROWS UNBOUNDED PRECEDING) AS ytd_funded,
    -- month-on-month growth, the same definition the dashboard's MoM cards use
    CAST((applications - LAG(applications) OVER (ORDER BY issue_month)) * 100.0
         / NULLIF(LAG(applications) OVER (ORDER BY issue_month), 0)
         AS DECIMAL(8, 2))                                                AS applications_mom_pct,
    CAST((funded - LAG(funded) OVER (ORDER BY issue_month)) * 100.0
         / NULLIF(LAG(funded) OVER (ORDER BY issue_month), 0)
         AS DECIMAL(8, 2))                                                AS funded_mom_pct,
    -- 3-month moving average of volume, which smooths the monthly noise
    CAST(AVG(applications * 1.0) OVER (ORDER BY issue_month
                                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
         AS DECIMAL(10, 1))                                               AS applications_3mo_avg
FROM monthly
ORDER BY issue_month;
GO
/* Expected: applications rise every month bar one, 2,332 in January to 4,314
   in December (+85.0% over the year); funded amount grows +115.7%, i.e. the
   average loan also got bigger. December MoM = +6.91% applications and
   +13.04% funded, which is exactly what the dashboard MoM cards show.
   Cohort default rate drifts mildly upward, 13.25% in January to 15.04% in
   December - consistent with, but not proof of, looser underwriting. */


/* ==========================================================================
   5. Purpose profitability - the only loss-making product
   --------------------------------------------------------------------------
   Business question: is every loan purpose worth offering?

   Techniques: CTE + window functions for share-of-book, plus a CASE flag for
   below-break-even products.
   ========================================================================== */
WITH purpose_stats AS (
    SELECT
        purpose,
        COUNT(*)                                                     AS loans,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) AS charged_off,
        SUM(loan_amount)                                             AS funded,
        SUM(total_payment)                                           AS received
    FROM dbo.bank_loan_data
    GROUP BY purpose
    HAVING COUNT(*) >= 50           -- volume floor
)
SELECT
    purpose,
    loans,
    funded,
    received,
    received - funded                                                     AS net_cash,
    CAST(charged_off * 100.0 / loans          AS DECIMAL(8, 2))           AS default_rate_pct,
    CAST(received * 100.0 / NULLIF(funded, 0) AS DECIMAL(8, 2))           AS recovery_pct,
    CAST(funded * 100.0 / SUM(funded) OVER () AS DECIMAL(8, 2))           AS pct_of_funded,
    DENSE_RANK() OVER (ORDER BY received * 1.0 / NULLIF(funded, 0))       AS worst_recovery_rank,
    CASE WHEN received < funded THEN 'LOSS-MAKING' ELSE 'profitable' END  AS verdict
FROM purpose_stats
ORDER BY recovery_pct;
GO
/* Expected: small business is the ONLY purpose below break-even - 1,776
   loans, 25.62% default rate, 98.7% recovery, net -308,283. Debt
   consolidation is 53.3% of the whole funded book at 109.2% recovery.
   Actionable finding: small-business lending needs repricing or tighter
   criteria, not withdrawal - it is 1 of 14 products and a small share of
   funding. */


/* ==========================================================================
   6. Concentration risk - how lopsided is the book geographically?
   --------------------------------------------------------------------------
   Business question: how exposed is the portfolio to a downturn in one state?

   Technique: a running total over a descending order produces a cumulative
   concentration curve, the SQL equivalent of a Pareto chart.
   ========================================================================== */
WITH state_stats AS (
    SELECT
        address_state,
        COUNT(*)                                                     AS loans,
        SUM(loan_amount)                                             AS funded,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) AS charged_off
    FROM dbo.bank_loan_data
    GROUP BY address_state
)
SELECT
    address_state,
    loans,
    funded,
    CAST(charged_off * 100.0 / NULLIF(loans, 0) AS DECIMAL(8, 2)) AS default_rate_pct,
    ROW_NUMBER() OVER (ORDER BY funded DESC)                       AS funding_rank,
    CAST(funded * 100.0 / SUM(funded) OVER ()  AS DECIMAL(8, 2))   AS pct_of_funded,
    CAST(SUM(funded) OVER (ORDER BY funded DESC ROWS UNBOUNDED PRECEDING)
         * 100.0 / SUM(funded) OVER ()
         AS DECIMAL(8, 2))                                          AS cumulative_pct_of_funded
FROM state_stats
ORDER BY funded DESC;
GO
/* Expected: California alone is 18.0% of funded, the top 3 states 34.8%, the
   top 5 46.7% and the top 10 64.9% - across 50 states. That is meaningful
   geographic concentration. Note also that Nevada has the worst default rate
   of any state with >= 300 loans (20.95%) while Texas has one of the best
   (11.30%). */


/* ==========================================================================
   7. Segment vs portfolio benchmark using a JOIN
   --------------------------------------------------------------------------
   Business question: which term x grade combinations are materially worse
   than the portfolio as a whole?

   Technique: a CROSS JOIN against a single-row CTE holding the portfolio
   average. This is the clearest way in SQL to compare every row to a global
   benchmark when you want the benchmark columns available for arithmetic.
   (Section 1 shows the window-function alternative; both are valid and it is
   worth being able to explain the trade-off.)

   Note the denominator: this section measures REALISED credit risk, so it
   restricts to closed loans - 'Current' loans have not finished their term
   and cannot yet be counted as good or bad. Portfolio-wide that shifts the
   default rate from 13.82% (all loans) to 14.23% (closed only).
   ========================================================================== */
WITH closed_loans AS (
    SELECT *
    FROM dbo.bank_loan_data
    WHERE loan_status IN ('Fully Paid', 'Charged Off')
),
portfolio AS (
    SELECT
        COUNT(*)                                                        AS total_closed,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) * 100.0
            / COUNT(*)                                                  AS portfolio_default_pct
    FROM closed_loans
),
segment AS (
    SELECT
        LTRIM(RTRIM(term))                                              AS term,
        grade,
        COUNT(*)                                                        AS loans,
        SUM(CASE WHEN loan_status = 'Charged Off' THEN 1 ELSE 0 END) * 100.0
            / COUNT(*)                                                  AS default_pct,
        SUM(loan_amount)                                                AS funded
    FROM closed_loans
    GROUP BY LTRIM(RTRIM(term)), grade
    HAVING COUNT(*) >= 100          -- volume floor
)
SELECT
    s.term,
    s.grade,
    s.loans,
    s.funded,
    CAST(s.default_pct           AS DECIMAL(8, 2)) AS segment_default_pct,
    CAST(p.portfolio_default_pct AS DECIMAL(8, 2)) AS portfolio_default_pct,
    CAST(s.default_pct - p.portfolio_default_pct AS DECIMAL(8, 2)) AS excess_default_pp,
    CAST(s.default_pct / NULLIF(p.portfolio_default_pct, 0) AS DECIMAL(8, 2)) AS risk_multiple,
    RANK() OVER (ORDER BY s.default_pct DESC)      AS risk_rank
FROM segment AS s
CROSS JOIN portfolio AS p
ORDER BY s.default_pct DESC;
GO
/* Expected (closed loans only; portfolio benchmark = 14.23% on 37,478 loans;
   13 segments clear the 100-loan floor). Cross-checked in pandas:
     60mo F  751 loans  34.22%  (2.4x portfolio)   <- worst
     60mo G  240        32.08%
     60mo E  1,758      29.75%
     60mo D  1,806      28.68%
     36mo F  206        26.21%
     ...
     36mo B  9,075      10.16%
     60mo A  380         9.21%
     36mo A  9,274       5.57%  (0.39x portfolio)  <- best
   Reading: within every grade the 60-month term is materially riskier than
   the 36-month term, so term is an independent risk factor on top of grade -
   worth knowing, because the dashboard shows term only as a volume split.
   But the effect does not dominate grade: 60-month grade A (9.21%) is still
   safer than 36-month grade B (10.16%). Grade first, term second. */


/* ==========================================================================
   8. Data-quality assertions in SQL
   --------------------------------------------------------------------------
   These mirror the Python validation suite (python -m bank_loan_report
   validate). Each row returns a status so the output can be eyeballed in one
   glance. Two checks are EXPECTED to report a problem: that is the honest
   state of this dataset, not a bug in the query. See docs/DATA_QUALITY.md.

   Technique: UNION ALL over independent scalar checks, and COUNT(*) OVER ()
   is deliberately avoided here - each check is its own aggregate.
   ========================================================================== */
WITH checks AS (
    SELECT 'row_count = 38576' AS check_name,
           CASE WHEN COUNT(*) = 38576 THEN 'PASS' ELSE 'FAIL' END AS status,
           CAST(COUNT(*) AS VARCHAR(30))                          AS observed
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'id is unique',
           CASE WHEN COUNT(*) = COUNT(DISTINCT id) THEN 'PASS' ELSE 'FAIL' END,
           CAST(COUNT(DISTINCT id) AS VARCHAR(30))
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'only 3 loan_status values',
           CASE WHEN COUNT(DISTINCT loan_status) = 3 THEN 'PASS' ELSE 'FAIL' END,
           CAST(COUNT(DISTINCT loan_status) AS VARCHAR(30))
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'int_rate stored as a fraction (max < 1)',
           CASE WHEN MAX(int_rate) < 1 THEN 'PASS' ELSE 'FAIL' END,
           CAST(MAX(int_rate) AS VARCHAR(30))
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'dti stored as a fraction (max < 1)',
           CASE WHEN MAX(dti) < 1 THEN 'PASS' ELSE 'FAIL' END,
           CAST(MAX(dti) AS VARCHAR(30))
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'no negative loan_amount or total_payment',
           CASE WHEN MIN(loan_amount) >= 0 AND MIN(total_payment) >= 0
                THEN 'PASS' ELSE 'FAIL' END,
           CAST(MIN(loan_amount) AS VARCHAR(15)) + ' / '
               + CAST(MIN(total_payment) AS VARCHAR(15))
    FROM dbo.bank_loan_data

    UNION ALL
    SELECT 'issue_date confined to 2021',
           CASE WHEN MIN(issue_date) >= '2021-01-01' AND MAX(issue_date) < '2022-01-01'
                THEN 'PASS' ELSE 'FAIL' END,
           CONVERT(VARCHAR(10), MIN(issue_date), 23) + ' .. '
               + CONVERT(VARCHAR(10), MAX(issue_date), 23)
    FROM dbo.bank_loan_data

    UNION ALL
    -- KNOWN DEFECT, expected to report WARN: payment dates precede origination
    SELECT 'last_payment_date >= issue_date',
           CASE WHEN SUM(CASE WHEN last_payment_date < issue_date THEN 1 ELSE 0 END) = 0
                THEN 'PASS' ELSE 'WARN - known dataset defect' END,
           CAST(SUM(CASE WHEN last_payment_date < issue_date THEN 1 ELSE 0 END)
                AS VARCHAR(30)) + ' rows'
    FROM dbo.bank_loan_data

    UNION ALL
    -- KNOWN DEFECT, expected to report WARN: 36-month loans cannot close in days
    SELECT '36-month loans span >= 365 days',
           CASE WHEN SUM(CASE WHEN DATEDIFF(DAY, issue_date, last_payment_date) < 365
                              THEN 1 ELSE 0 END) = 0
                THEN 'PASS' ELSE 'WARN - known dataset defect' END,
           CAST(SUM(CASE WHEN DATEDIFF(DAY, issue_date, last_payment_date) < 365
                         THEN 1 ELSE 0 END) AS VARCHAR(30)) + ' of '
               + CAST(COUNT(*) AS VARCHAR(30)) + ' rows'
    FROM dbo.bank_loan_data
    WHERE loan_status = 'Fully Paid' AND LTRIM(RTRIM(term)) = '36 months'
)
SELECT check_name, status, observed
FROM checks
ORDER BY CASE status WHEN 'PASS' THEN 2 ELSE 1 END, check_name;
GO
/* Expected: 7 PASS and 2 WARN. The two WARNs are the documented timeline
   defect in the source data - 15,453 rows (40.1%) have last_payment_date
   before issue_date, and 100% of Fully Paid 36-month loans appear to close
   within a year. This is why no vintage or time-to-default analysis is
   attempted anywhere in this project. */
