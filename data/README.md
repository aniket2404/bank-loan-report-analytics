# Data Storage & Ingestion

## Committed Sample vs Full Dataset

| Path | Contents |
|---|---|
| `sample/financial_loan_sample.csv` | A 600-row stratified sample, committed to allow automated tests, CI, and local verification out of the box. |
| `raw/` | Local directory for full portfolio dataset (`financial_loan.csv`). |

The full `financial_loan.csv` (7.8 MB, 38,576 rows) is tracked under `.gitignore` to keep repository clones fast and lightweight.

## Adding the Full Dataset

Place the complete `financial_loan.csv` file inside:

```
data/raw/financial_loan.csv
```

All package loaders, analytics modules, and test runners automatically detect and prioritize `data/raw/financial_loan.csv` if present, falling back gracefully to `sample/financial_loan_sample.csv` in lightweight environments.

## Schema

See `docs/data_dictionary.md` for full column contracts, derived features, and domain validations.
