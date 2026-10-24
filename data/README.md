# Data

## `raw/` (read-only inputs, 18 files)

| Files | Origin | Licence |
|---|---|---|
| `historic_demand_year_2009.csv` ... `historic_demand_year_2024.csv` (16) | NESO Data Portal "Historic Demand Data" (https://www.neso.energy/data-portal/historic-demand-data). 2009-2018 are byte-identical to NESO's current downloads; 2019-2024 are the **audited vintage** (NESO has since re-published them with different bytes; see `docs/DATA_CLEANING_REPORT.md` section 2) obtained from the Kaggle bundle below. NESO serves these as `demanddata_YYYY.csv`; they are stored under the audit brief's names. | NESO Open Data Licence |
| `historic_demand_2009_2024.csv`, `historic_demand_2009_2024_noNaN.csv` | Third-party compilation "Electricity Consumption UK 2009-2024" by albertovidalrod (https://www.kaggle.com/datasets/albertovidalrod/electricity-consumption-uk-20092022). Used only for cross-validation and for the critique of the `noNaN` file; **never as a data source.** | ODbL 1.0 (attribution and share-alike apply to derived databases) |

SHA-256, row and column counts for every file: `backend/app/data/expected_hashes.json`. Every file in this folder matches it (verified, and tested).
Re-create the folder with `cd backend && python -m app.data.fetch_raw_data`.

Raw files are never modified: the pipeline only reads them (a test hashes them before and after a run).

## `interim/`

Regenerable staging written by the pipeline (`demand_unified_uncleaned.parquet`: the unified schema with timestamps, before any cleaning). Git-ignored.

## `processed/`

Pipeline outputs; column definitions in `docs/DATA_DICTIONARY.md`. Scope: NESO demand data to 2024-12-05, **not** Elexon wind data, and not a January 2026 dataset.
