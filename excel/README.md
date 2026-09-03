# Excel Layer — Build Guide

The `.xlsx` dashboard is a binary that cannot be reconstructed from a video, so this
file documents how to rebuild it. Every number it produces is cross-checked against
`docs/VERIFICATION.md`.

---

## 1. Get the data in

**Option A — connect to SQL Server (standard implementation)**

Data → Get Data → From Database → From SQL Server Database
- Server: `localhost`
- Database: `bank_loan_db`
- Select `vw_bank_loan_enriched` → **Load To… → Only Create Connection → Add this data to the Data Model**

**Option B — load the CSV**

Data → Get Data → From Text/CSV → `data/raw/financial_loan.csv` → Transform Data →
set the four `*_date` columns to Date **using locale English (United Kingdom)**
(the file is DD-MM-YYYY) → Close & Load To → Only Create Connection + Data Model.

Loading to the Data Model rather than a sheet keeps the workbook small and lets the
pivot tables share one cache and one set of slicers.

## 2. Pivot tables

Create each on a hidden `Pivots` worksheet. All of them use the same connection.

| Pivot | Rows | Columns | Values |
|---|---|---|---|
| `pvt_kpi` | — | — | Count of `id`; Sum of `loan_amount`; Sum of `total_payment`; Average of `int_rate`; Average of `dti` |
| `pvt_kpi_mtd` | — | — | same five, filtered to the latest month |
| `pvt_kpi_pmtd` | — | — | same five, filtered to the previous month |
| `pvt_quality` | `loan_quality` | — | Count of `id`; Sum of `loan_amount`; Sum of `total_payment` |
| `pvt_status_grid` | `loan_status` | — | Count of `id`; Sum of `loan_amount`; Sum of `total_payment`; Average of `int_rate`; Average of `dti` |
| `pvt_month` | `issue_month_name` (sorted by `issue_month`) | — | Count of `id`; Sum of `loan_amount`; Sum of `total_payment` |
| `pvt_state` | `address_state` | — | same three |
| `pvt_term` | `term_clean` | — | same three |
| `pvt_emp_length` | `emp_length` | — | same three |
| `pvt_purpose` | `purpose` | — | same three |
| `pvt_home` | `home_ownership` | — | same three |

For the MTD / PMTD pivots, put `issue_month` in the Filters area and select `12`
(MTD) and `11` (PMTD) for this dataset.

**Number formats:** interest rate and DTI are decimal fractions in the source, so
format those value fields as **Percentage, 2 decimals** — do not multiply by 100 in
the pivot, or the percent format will double-scale them.

## 3. KPI cells

On the `Summary` sheet, reference the pivots with `GETPIVOTDATA` so the cards survive
a pivot refresh. Using named cells `Total_Apps`, `MTD_Apps`, `PMTD_Apps` etc.:

```excel
' Totals
=GETPIVOTDATA("Count of id",       Pivots!$A$3)
=GETPIVOTDATA("Sum of loan_amount",   Pivots!$A$3)
=GETPIVOTDATA("Sum of total_payment", Pivots!$A$3)
=GETPIVOTDATA("Average of int_rate",  Pivots!$A$3)
=GETPIVOTDATA("Average of dti",       Pivots!$A$3)

' Month-over-month change, shown under each card
=IFERROR((MTD_Funded - PMTD_Funded) / PMTD_Funded, "")

' Good vs bad loan share
=GETPIVOTDATA("Count of id", Pivots!$A$20, "loan_quality", "Good Loan") / Total_Apps
=GETPIVOTDATA("Count of id", Pivots!$A$20, "loan_quality", "Bad Loan")  / Total_Apps

' Compact card label, e.g. $435.76M
="$" & TEXT(Total_Funded / 1000000, "0.00") & "M"

' MoM direction arrow
=IF(MoM_Funded >= 0, "▲ ", "▼ ") & TEXT(ABS(MoM_Funded), "0.0%") & " MoM"
```

Adjust the anchor cells (`Pivots!$A$3`, `$A$20`, …) to wherever your pivots actually
start.

## 4. Charts

| Chart | Type | Source pivot |
|---|---|---|
| Monthly Trends by Issue Date | Line with markers | `pvt_month` |
| Regional Analysis by State | Filled Map (Excel 2016+) or sorted Bar | `pvt_state` |
| Loan Term Analysis | Doughnut | `pvt_term` |
| Employee Length Analysis | Clustered Column | `pvt_emp_length` |
| Loan Purpose Breakdown | Clustered Bar, sorted descending | `pvt_purpose` |
| Home Ownership Analysis | Treemap | `pvt_home` |
| Good vs Bad Loan | Doughnut ×2 | `pvt_quality` |

Excel's Filled Map needs `address_state` recognised as a geography; if the two-letter
codes are not picked up, add a helper column with the full state name.

## 5. Slicers and timeline

Insert → Slicer on: `grade`, `sub_grade`, `purpose`, `term_clean`, `home_ownership`,
`verification_status`, `address_state`.
Insert → Timeline on `issue_date`.

Then, for **each** slicer: right-click → Report Connections → tick every pivot table.
Without this the slicers only filter one chart.

## 6. Layout

Three worksheets — `Summary`, `Overview`, `Details` — plus the hidden `Pivots` sheet.

- **Summary:** five KPI cards in a row (each with total, MTD and MoM), Good Loan and
  Bad Loan doughnuts, and the Loan Status grid pivot.
- **Overview:** the six charts in a 3×2 grid with the slicer panel down the left.
- **Details:** the flat table (a pivot in Tabular layout, or the loaded query as a table).

Presentation touches used in the standard: View → uncheck Gridlines, Formula Bar and
Headings; a dark fill behind the cards; and rounded rectangles as card backgrounds.

## 7. Navigation buttons

Insert → Shapes → Rounded Rectangle ×3, labelled SUMMARY / OVERVIEW / DETAILS.
Right-click each → Link → Place in This Document → pick the target sheet.
Copy the same three shapes onto all three sheets so navigation is consistent.

## 8. Validation

Refresh All, then confirm the Summary sheet reads: 38,576 applications,
$435.76M funded, $473.07M received, 12.05% interest rate, 13.33% DTI,
86.18% good / 13.82% bad.
