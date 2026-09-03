# Power Query — Transformation Steps

Applied in Home → Transform data before loading the model.

## 1. Source

- **SQL Server path:** Server `localhost`, Database `bank_loan_db`, object
  `dbo.vw_bank_loan_enriched` (or `dbo.bank_loan_data`). Connectivity mode: **Import**.
- **CSV path:** `data/raw/financial_loan.csv`, delimiter comma, first row as headers,
  encoding 65001 (UTF-8).

## 2. Column profiling (data-quality check)

Turn on View → **Column quality**, **Column distribution** and **Column profile**,
and switch the status-bar profiling from "top 1000 rows" to
**"Column profiling based on entire data set"**.

What you should see on the lending dataset:

| Column | Finding | Action |
|---|---|---|
| `emp_title` | 1,438 empty values (~3.7%) | Leave as-is — it is not used in any KPI |
| all other columns | 0 errors, 0 empty | none |
| `id` | 38,576 distinct = 38,576 rows | confirms the grain is one row per loan |
| `loan_status` | 3 distinct values | confirms the good/bad rule is complete |
| `term` | 2 distinct values, both with a leading space | trim |

## 3. Steps

1. **Promoted Headers** (CSV path only).
2. **Changed Type** — set explicit types rather than accepting the auto-detected ones:
   - `id`, `member_id`, `loan_amount`, `total_acc`, `total_payment` → Whole Number
   - `annual_income`, `dti`, `installment`, `int_rate` → Decimal Number
   - `issue_date`, `last_credit_pull_date`, `last_payment_date`, `next_payment_date` → Date
   - everything else → Text
3. **Parse the dates (CSV path only).** The CSV stores `DD-MM-YYYY`, so a plain type
   change under a US locale silently mis-parses days as months. Use
   *Transform → Data Type → Using Locale… → Date → English (United Kingdom)*, or the
   M snippet below.
4. **Trimmed Text** on `term` (and optionally on all text columns):
   right-click column → Transform → Trim.
5. **Added Custom Column** `loan_quality`:
   ```m
   if List.Contains({"Fully Paid", "Current"}, [loan_status]) then "Good Loan" else "Bad Loan"
   ```
   (Not needed on the SQL Server path — the view already provides it.)
6. **Renamed** the query to `bank_loan_data`.
7. **Close & Apply.**

## 4. Equivalent M script

Paste into Advanced Editor for the CSV path:

```m
let
    Source = Csv.Document(
        File.Contents("C:\path\to\bank-loan-report-analytics\data\raw\financial_loan.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"id", Int64.Type}, {"member_id", Int64.Type},
            {"address_state", type text}, {"application_type", type text},
            {"emp_length", type text}, {"emp_title", type text},
            {"grade", type text}, {"home_ownership", type text},
            {"loan_status", type text}, {"purpose", type text},
            {"sub_grade", type text}, {"term", type text},
            {"verification_status", type text},
            {"annual_income", type number}, {"dti", type number},
            {"installment", type number}, {"int_rate", type number},
            {"loan_amount", Int64.Type}, {"total_acc", Int64.Type},
            {"total_payment", Int64.Type}
        }
    ),
    Dates = Table.TransformColumnTypes(
        Typed,
        {
            {"issue_date", type date}, {"last_credit_pull_date", type date},
            {"last_payment_date", type date}, {"next_payment_date", type date}
        },
        "en-GB"
    ),
    Trimmed = Table.TransformColumns(Dates, {{"term", Text.Trim, type text}}),
    LoanQuality = Table.AddColumn(
        Trimmed,
        "loan_quality",
        each if List.Contains({"Fully Paid", "Current"}, [loan_status])
             then "Good Loan" else "Bad Loan",
        type text
    )
in
    LoanQuality
```

## 5. Validation after loading

Add a temporary card visual with `COUNTROWS(bank_loan_data)` — it must read
**38,576**. Then check `MIN(issue_date)` = 01/01/2021 and `MAX(issue_date)` =
12/12/2021. If the max date lands in a different month, the date parsing step
failed and every MTD/PMTD measure will be wrong.
