# Tableau — Calculated Fields, Parameters and Dashboards

The `.twbx` binary cannot be reconstructed from a video, so this file documents
every calculation needed to rebuild the workbook.

**Connection:** Data → New Data Source → Microsoft SQL Server →
Server `localhost`, Database `bank_loan_db` → drag in the view `vw_bank_loan_enriched`
(or use `bank_loan_data` directly). Extract mode is fine.

If you do not have SQL Server, connect to `data/raw/financial_loan.csv` instead and
add the `Issue Date (parsed)` field below to convert the DD-MM-YYYY strings.

---

## 1. Housekeeping fields

```
// Issue Date (parsed)  -- only needed for the CSV connection
DATEPARSE("dd-MM-yyyy", [Issue Date])
```

```
// Term (clean)  -- source values have a leading space
TRIM([Term])
```

```
// Interest Rate %      // DTI %
AVG([Int Rate]) * 100   AVG([Dti]) * 100
```

## 2. Reporting period anchors

```
// Current Month  -- the latest month present in the data
{ FIXED : MAX( DATETRUNC('month', [Issue Date]) ) }
```

```
// Previous Month
DATEADD('month', -1, [Current Month])
```

```
// Period Label
IF DATETRUNC('month', [Issue Date]) = [Current Month]  THEN "MTD"
ELSEIF DATETRUNC('month', [Issue Date]) = [Previous Month] THEN "PMTD"
END
```

> **Alternative used in the standard.** Instead of a period label, the video writes the
> month offset inline with a fixed LOD. Both give identical results — pick one style:
>
> ```
> // MTD Loan Applications (DATEDIFF style)
> COUNT( IF DATEDIFF('month', [Issue Date], { MAX([Issue Date]) }) = 0 THEN [Id] END )
>
> // PMTD Loan Applications (DATEDIFF style)
> COUNT( IF DATEDIFF('month', [Issue Date], { MAX([Issue Date]) }) = 1 THEN [Id] END )
> ```
>
> The curly braces around `MAX([Issue Date])` are required — without them Tableau
> raises "cannot mix aggregate and non-aggregate arguments".

## 3. MTD / PMTD measures

```
// MTD Loan Applications
COUNTD( IF [Period Label] = "MTD" THEN [Id] END )

// PMTD Loan Applications
COUNTD( IF [Period Label] = "PMTD" THEN [Id] END )

// MTD Funded Amount
SUM( IF [Period Label] = "MTD" THEN [Loan Amount] END )

// PMTD Funded Amount
SUM( IF [Period Label] = "PMTD" THEN [Loan Amount] END )

// MTD Amount Received
SUM( IF [Period Label] = "MTD" THEN [Total Payment] END )

// PMTD Amount Received
SUM( IF [Period Label] = "PMTD" THEN [Total Payment] END )

// MTD Avg Interest Rate
AVG( IF [Period Label] = "MTD" THEN [Int Rate] END ) * 100

// PMTD Avg Interest Rate
AVG( IF [Period Label] = "PMTD" THEN [Int Rate] END ) * 100

// MTD Avg DTI
AVG( IF [Period Label] = "MTD" THEN [Dti] END ) * 100

// PMTD Avg DTI
AVG( IF [Period Label] = "PMTD" THEN [Dti] END ) * 100
```

## 4. Month-over-month change

```
// MoM Loan Applications
([MTD Loan Applications] - [PMTD Loan Applications]) / [PMTD Loan Applications]

// MoM Funded Amount
([MTD Funded Amount] - [PMTD Funded Amount]) / [PMTD Funded Amount]

// MoM Amount Received
([MTD Amount Received] - [PMTD Amount Received]) / [PMTD Amount Received]

// MoM Avg Interest Rate
([MTD Avg Interest Rate] - [PMTD Avg Interest Rate]) / [PMTD Avg Interest Rate]

// MoM Avg DTI
([MTD Avg DTI] - [PMTD Avg DTI]) / [PMTD Avg DTI]
```

Format each as a percentage with one decimal place, and add an up/down KPI shape
using a second calculation: `IF [MoM Funded Amount] >= 0 THEN "▲" ELSE "▼" END`.

## 5. Good loan / bad loan

```
// Loan Quality
IF [Loan Status] = "Fully Paid" OR [Loan Status] = "Current"
THEN "Good Loan" ELSE "Bad Loan" END
```

> The standard achieves the same split with a **Group** on `Loan Status`
> (right-click the field → Create → Group → select *Fully Paid* + *Current* → Group,
> rename to "Good Loan"; rename the *Charged Off* member to "Bad Loan").
> The calculated field above is preferred here because it is explicit, version-control
> friendly and matches the SQL and Python layers exactly.

```
// Good Loan Applications
COUNTD( IF [Loan Quality] = "Good Loan" THEN [Id] END )

// Good Loan Percentage
[Good Loan Applications] / COUNTD([Id])

// Good Loan Funded Amount
SUM( IF [Loan Quality] = "Good Loan" THEN [Loan Amount] END )

// Good Loan Amount Received
SUM( IF [Loan Quality] = "Good Loan" THEN [Total Payment] END )

// Bad Loan Applications
COUNTD( IF [Loan Quality] = "Bad Loan" THEN [Id] END )

// Bad Loan Percentage
[Bad Loan Applications] / COUNTD([Id])

// Bad Loan Funded Amount
SUM( IF [Loan Quality] = "Bad Loan" THEN [Loan Amount] END )

// Bad Loan Amount Received
SUM( IF [Loan Quality] = "Bad Loan" THEN [Total Payment] END )
```

## 6. Dynamic measure for the Overview dashboard

Create a **parameter** so one control drives all six Overview charts.

```
Parameter name: Select Measure
Data type:      String
Allowable:      List
Values:         Total Loan Applications
                Total Funded Amount
                Total Amount Received
Current value:  Total Loan Applications
```

```
// Selected Measure  (IF / ELSEIF form - this is standard implementation)
IF     [Select Measure] = "Total Loan Applications" THEN COUNTD([Id])
ELSEIF [Select Measure] = "Total Funded Amount"     THEN SUM([Loan Amount])
ELSEIF [Select Measure] = "Total Amount Received"   THEN SUM([Total Payment])
END
```

A `CASE` expression is equivalent and slightly shorter, if you prefer it:

```
CASE [Select Measure]
    WHEN "Total Loan Applications" THEN COUNTD([Id])
    WHEN "Total Funded Amount"     THEN SUM([Loan Amount])
    WHEN "Total Amount Received"   THEN SUM([Total Payment])
END
```

Note that Tableau has no `SWITCH` function — that is the Power BI equivalent.

```
// Selected Measure Title  -- drop on the Title shelf of each sheet
"Total by " + [Select Measure]
```

Right-click the parameter → Show Parameter, and place the control once on the
Overview dashboard.

## 7. Employment length sort order

`Emp Length` is a string, so create a sort key and use it as the manual sort field:

```
// Emp Length Sort
CASE [Emp Length]
    WHEN "< 1 year"  THEN 0
    WHEN "1 year"    THEN 1
    WHEN "2 years"   THEN 2
    WHEN "3 years"   THEN 3
    WHEN "4 years"   THEN 4
    WHEN "5 years"   THEN 5
    WHEN "6 years"   THEN 6
    WHEN "7 years"   THEN 7
    WHEN "8 years"   THEN 8
    WHEN "9 years"   THEN 9
    WHEN "10+ years" THEN 10
END
```

## 8. Worksheets

| Sheet | Mark type | Columns / Rows | Marks |
|---|---|---|---|
| `KPI - Applications` | Text | — | `COUNTD(Id)`, `MTD Loan Applications`, `MoM Loan Applications` |
| `KPI - Funded` | Text | — | `SUM(Loan Amount)`, `MTD Funded Amount`, `MoM Funded Amount` |
| `KPI - Received` | Text | — | `SUM(Total Payment)`, `MTD Amount Received`, `MoM Amount Received` |
| `KPI - Interest Rate` | Text | — | `Interest Rate %`, `MTD Avg Interest Rate`, `MoM Avg Interest Rate` |
| `KPI - DTI` | Text | — | `DTI %`, `MTD Avg DTI`, `MoM Avg DTI` |
| `Good Loan` | Pie / Text | `Loan Quality` filtered to Good Loan | `Good Loan Percentage`, `Good Loan Applications`, `Good Loan Funded Amount`, `Good Loan Amount Received` |
| `Bad Loan` | Pie / Text | filtered to Bad Loan | Bad Loan equivalents |
| `Loan Status Grid` | Text table | Rows `Loan Status` | Applications, Funded, Received, MTD Funded, MTD Received, Interest Rate %, DTI % |
| `Monthly Trend` | Line | Columns `MONTH(Issue Date)`; Rows `Selected Measure` | — |
| `State Map` | Map (filled) | `Address State` (geographic role: State/Province) | Colour = `Selected Measure` |
| `Term Donut` | Pie ×2 (dual axis) | `Term (clean)` | Angle = `Selected Measure` |
| `Employee Length` | Bar | Rows `Emp Length` sorted by `Emp Length Sort` | `Selected Measure` |
| `Purpose` | Bar | Rows `Purpose` sorted descending | `Selected Measure` |
| `Home Ownership` | Treemap | `Home Ownership` | Size + colour = `Selected Measure` |
| `Details` | Text table | all detail fields | — |

**Donut in Tableau:** build two pie charts on a dual axis, make the second one a
smaller white circle, then synchronise and hide the axes.

## 9. Dashboards

1. **Summary** — five KPI sheets across the top, Good Loan and Bad Loan panels in
   the middle, Loan Status grid at the bottom.
2. **Overview** — the six chart sheets in a 3×2 grid with the `Select Measure`
   parameter control.
3. **Details** — the full detail table.

Background images for the dashboards ship with the standard's data folder
(`Tableau Background 1-3.jpg`); see `data/README.md` for the download link.

**Filters (applied to all sheets using this data source):** `Grade`, `Sub Grade`,
`Purpose`, `Term (clean)`, `Home Ownership`, `Verification Status`,
`Address State`, and a date range on `Issue Date`.

**Navigation:** add three Navigation objects (Dashboard → Objects → Navigation) to
each dashboard pointing at Summary / Overview / Details.

## 10. Expected numbers

Cross-check against `docs/VERIFICATION.md`: 38,576 applications, $435,757,075
funded, $473,070,933 received, 12.05% interest rate, 13.33% DTI, 86.18% good loans.
