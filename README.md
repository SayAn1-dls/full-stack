# Wind Intelligence: NESO demand data pipeline

The cleaning, validation and documentation pipeline for **NESO "Historic Demand Data" (Great Britain, half-hourly, 2009-01-01 to
2024-12-05)**, the supporting dataset of the Wind Intelligence project (UK wind forecast evaluation dashboard; React front end, Python/FastAPI
back end per the product PRD).

## Status and scope (please read)

- **Built so far: the data pipeline only.** The dashboard (React), the API (FastAPI), Docker packaging and any Vercel/Heroku deployment are **not built**
  in this repository yet. **There is no deployed app, so there is no app link.**
- **This is NESO demand data, not Elexon data.** It is not FUELHH actual generation or WINDFOR wind forecasts, which the app is meant to evaluate, and
  `embedded_wind_generation` is NESO's *estimate* of distribution-connected wind only, not national wind output. The PRD scopes the application to Elexon
  wind actuals and forecasts alone, so this dataset is **not wired into any app** and must not be shown as forecast or actual wind.
- **Coverage ends 2024-12-05** (the audited vintage). It does not cover January 2026, the PRD's target period.
- **AI disclosure:** this work was produced with an AI coding assistant (Claude Code, by Anthropic), which wrote the code, tests and documentation;
  the outputs were verified by running the pipeline and the test suite (see `TEST_REPORT.md`).

## Quick start

Requires Python 3.13 (developed and tested on 3.13.17).

```bash
cd backend
pip install -r requirements-dev.txt

python -m app.data.fetch_raw_data   # only if data/raw/ is empty; verifies SHA-256 before installing
python -m app.data.clean_demand     # ~30 s, idempotent: writes data/interim/ and data/processed/ only
python -m app.data.build_docs       # regenerates docs/DATA_DICTIONARY.md from the run manifest

python -m pytest tests -q               # everything: logic tests + real-data tests (about 1 minute)
python -m pytest tests -q -m "not data" # fast logic suite only (about 3 seconds)
```

The committed `data/raw/` and `data/processed/` already contain the verified inputs and outputs, so the tests run on a fresh clone without fetching.

## Files and directories

```
README.md              this file
DECISIONS.md           every decision made without asking, with reasons (D-01 ...)
BUG_LOG.md             defects found while building, and how each was fixed
TEST_REPORT.md         what was run, results, mutation checks, remaining risks
backend/
  requirements.txt, requirements-dev.txt, pytest.ini
  app/data/
    clean_demand.py      the pipeline: `python -m app.data.clean_demand`
    demand_schema.py     column names, flags and NESO definitions (single source of truth)
    holiday_calendar.py  England & Wales observed bank holidays
    reference_checks.py  combined-file cross-validation, noNaN critique, is_holiday comparison
    fetch_raw_data.py    installs the 18 audited raw files after SHA-256 verification
    compare_neso_current.py  diff of the audited files vs NESO's re-published 2019-2024 files
    build_docs.py        renders docs/DATA_DICTIONARY.md
    expected_hashes.json SHA-256, row and column counts of the 18 audited files
    reference/bank_holidays_gov_uk.json   frozen gov.uk snapshot (2019+), used as a cross-check
  tests/
    test_demand_logic.py       86 fast deterministic tests on small fixtures
    test_demand_real_data.py   43 real-data tests (marker `data`) against data/raw
    helpers.py, conftest.py    fixture builders (all five schema eras) and the shared real-data run
data/
  README.md            provenance, licences, file list
  raw/                 18 read-only inputs: 16 yearly NESO files + 2 combined third-party files
  interim/             regenerable staging (git-ignored)
  processed/
    demand_clean.parquet, demand_clean.csv   the clean dataset (279,264 rows)
    demand_daily_completeness.csv            one row per day: expected/present/flagged periods
    demand_null_reasons.csv                  every null with its reason
    run_manifest.json                        input hashes, row counts, flags per rule, versions
    reference_checks.json, is_holiday_disagreements.csv
docs/
  DATA_DICTIONARY.md       every output column: type, unit, definition, range, null policy, first date published
  DATA_CLEANING_REPORT.md  before/after, every anomaly, decisions, noNaN critique, is_holiday comparison, scope limits
```

## What the pipeline guarantees

- Built from the 16 yearly files, mapped by column name across five schema eras; the combined files are used only for cross-validation.
- DST-correct timestamps: `period_start_utc` is unique and increases in exact 30-minute steps from 2009-01-01T00:00Z to 2024-12-05T23:30Z (46- and 50-period clock-change days handled).
- 279,264 rows in, 279,264 out; nothing dropped, nothing imputed. Invalid zero readings are set to null and flagged; suspect readings are kept and flagged;
  columns a year's file does not publish are null (never 0) with the reason recorded.
- Raw files are never modified (verified by test); a SHA-256 mismatch stops the run.

## Data licences

NESO Historic Demand Data: NESO Open Data Licence (https://www.neso.energy/data-portal). Combined files `historic_demand_2009_2024*.csv`:
"Electricity Consumption UK 2009-2024" by albertovidalrod on Kaggle, ODbL 1.0. See `data/README.md`.
