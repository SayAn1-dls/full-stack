# Decisions

Reversible decisions made without asking, with the reason. Newest context first within each theme.
URLs actually used are recorded in D-02.

## Scope and layout

**D-01 Repo layout follows the product PRD (React + Python/FastAPI, Docker).** The repo was empty, so the data pipeline lives at
`backend/app/data/` and its tests at `backend/tests/`, as the brief says to do when a layout exists; `data/` and `docs/` sit at the
root. The dashboard can grow around this without moving files. Run commands from `backend/`.

**D-18 NESO demand data is not wired into the wind app.** The PRD limits the application to Elexon FUELHH/WINDFOR wind actuals and forecasts, "no other data beyond this";
serving NESO demand in the app would break that scope, and the brief's own Section 2 says the same (supporting dataset, never charted as forecast/actual wind). The optional
"hook into Wind Intelligence" step was therefore not built. Reversible: the clean parquet is ready to be served read-only if the scope changes.

**D-21 What was and was not built from the PRD.** Built: the React front end, the Python (FastAPI) back end, Docker packaging and a Vercel deployment (see D-24 to D-36).
Not built, because they are not code in this repository or need the user: the recorded demo video, creating a separately named *anonymous* public repository, the submission form,
and a Heroku deployment (Vercel was chosen; the PRD says "Vercel or Heroku").

## Inputs

**D-02 Source of the raw files and URLs used.**
- NESO portal page (official): https://www.neso.energy/data-portal/historic-demand-data ; resource list from
  https://api.neso.energy/api/3/action/datapackage_show?id=historic-demand-data (yearly resources, e.g. `.../resource/<id>/download/demanddata_2009.csv`).
- Kaggle bundle (third-party, ODbL 1.0), fetched anonymously from
  https://www.kaggle.com/api/v1/datasets/download/albertovidalrod/electricity-consumption-uk-20092022 (no login was required for this endpoint
  on 2026-10-24). It is the only source of the audited bytes for 2019-2024 and of the two combined files.
- Field definitions and sign conventions: NESO datastore schema, `https://api.neso.energy/api/3/action/datastore_search?resource_id=f6d02c0f-957b-48cb-82ee-09003f2ba759&limit=1`.
- Bank holidays: https://www.gov.uk/bank-holidays.json (snapshot frozen in `backend/app/data/reference/`).

**D-03 The audited vintage is the input; NESO's current 2019-2024 files are not.** NESO re-published those years on 2025-04-08: hashes differ,
embedded wind/solar estimates were re-modelled, 2024 now runs to 2024-12-31, and 2023 uses `DD-Mon-YY` dates. Using the new files would silently
change the data and invalidate every number in the brief. `python -m app.data.compare_neso_current` documents the difference. The audited
files are installed from the Kaggle bundle after SHA-256 verification.

**D-04 Raw files keep the brief's names** (`historic_demand_year_YYYY.csv`), not NESO's current `demanddata_YYYY.csv`; content is unchanged. They are
set read-only on install, and a test proves the pipeline leaves them byte-identical.

**D-05 A hash mismatch stops the run** (`HashMismatchError`). `--allow-hash-mismatch` records the mismatch in the manifest and continues, for someone
who knowingly processes a different vintage; the Section 4 numbers then no longer apply and the real-data tests will (correctly) fail.

**D-06 Only two date formats are accepted** (`DD-MON-YYYY`, `YYYY-MM-DD`), parsed with fixed regex-plus-calendar logic (locale independent, no
`format="mixed"`). Unparseable or impossible dates raise. Blank, non-numeric and non-integer cells, unknown columns and out-of-range periods also raise: a
future schema change must be a deliberate edit, not a silent coercion (NESO's 2026 file stops on its new `forecast_actual_indicator` column).

**D-22 Newer NESO data (2025; 2026 including January 2026) was noticed but not ingested.** It is out of the PRD's scope and has a different
schema. Reported in the cleaning report so nobody assumes January 2026 is unobtainable.

## Cleaning rules

**D-07 Invalid-zero rule covers `nd`, `tsd`, `england_wales_demand`.** The brief requires the last two; `nd == 0` is equally impossible and costs nothing
(0 rows today; unit-tested). The cell is nulled, the row and the rest of the row are kept, and a flag records it. Whole days are never dropped.

**D-08 Suspect flags are evaluated on cleaned values.** After nulling, a missing TSD is not "TSD below ND". The brief's 501 `tsd < nd` rows reproduce from raw data
(manifest `tsd_below_nd.raw_rows`), and 501 = 479 nulled invalid zeros + **22** genuinely suspect rows that carry `flag_tsd_below_nd`. A test asserts the identity.

**D-09 `constant_column` is a column-level property** (one distinct value across the column's whole published history, at least 1,000 values), so only
`greenlink_flow` is flagged. Zero-filled columns that later become real (e.g. `nemo_flow` before 2019) are documented per column with their first non-zero
date rather than flagged row by row, which would mark most of the dataset.

**D-10 Structural missing values are NaN with the reason in `demand_null_reasons.csv`** (`column_not_published`, per source file with date span), not repeated on
every row. Invalid readings carry their reason as a row flag and in the same table.

**D-11 Flags are booleans plus one `quality_flags` string** of `;`-joined tokens, `ok` for clean rows (a sentinel that survives a CSV round trip, unlike an empty string).

**D-16 Six odd non-zero `england_wales_demand` readings are listed, not flagged or nulled.** E&W/ND is normally 0.86-0.98 but six rows sit at 0.19, 0.60, 0.73, 0.76, 1.06 and 1.11.
The tail is continuous with no natural gap, so any threshold would be arbitrary, and the brief's rule is about exact zeros. They are in the cleaning report for human review.

**D-12 Output formats.** Timestamps are nanosecond UTC; the CSV uses ISO-8601 (`...Z` for UTC, with offset for local), LF line endings, blank for null, so outputs are byte-stable across OSes.
`settlement_date` is a date, `settlement_period` int16, power columns nullable `Int64`.

**D-13 Missing or extra periods are hard failures** (time-axis gap -> `TimeContinuityError`; short/extra day -> `CompletenessError`). The completeness CSV is written first, so a failing run still leaves the evidence.
No such case exists in the audited data.

**D-17 No imputed variant was produced** (the brief makes it optional). `demand_clean` never contains an imputed value.

## Holidays and reference files

**D-14 `is_bank_holiday_ew` replaces `is_holiday`.** Definition: England & Wales bank holiday *observed* on the date (substitute days included, nominal weekend dates excluded), from
`holidays.UnitedKingdom(subdiv="England")`, package pinned at 0.107. gov.uk's JSON no longer carries years before 2019, so gov.uk is a cross-check for 2019-2024-12-05 only (0 differences);
2009-2018 rely on the package. The original column is not carried: its definition is undocumented and it disagrees with the recomputation on 10 days (5 genuine omissions, 5 definitional). Scotland/Northern Ireland holidays are excluded.

**D-15 The `noNaN` combined file is rejected as a source** and used only to demonstrate its defects (cleaning report section 8). The plain combined file is used only for cross-validation.

## Repository content

**D-19 Data committed to git.** Raw files (the brief's `data/raw/` convention; needed to reproduce and test), processed outputs including the 67 MB CSV (explicit deliverable;
under GitHub's 100 MB limit, over its 50 MB warning). `data/interim/` is regenerable and ignored. Licences: NESO yearly data under the NESO Open Data Licence, the Kaggle combined
files under ODbL 1.0 (attribution in `data/README.md`). Reversible: if repo size becomes a problem, drop the combined files and the CSV from git; `fetch_raw_data` and the pipeline recreate them in about a minute.

**D-20 Dependencies are pinned** to the versions verified here (pandas 3.0.5, pyarrow 26, holidays 0.107, Python 3.13). pandas 3 changed string and datetime defaults; the code and tests assume it.

**D-23 Tests fail, not skip, when raw files are missing.** The real-data suite is marked `data`; a missing raw file fails with the fix command. Run `pytest -m "not data"` for the fast suite.

## Wind app (React + FastAPI) - added with the deployment request

**D-24 Scope window.** "Purchase decisions to be made in January 2026": decisions on 1-31 January give delivery days 2 January - 1 February; delivery on 1 January (decided 31 December) is
included too so every January target time is covered, and the UI labels it. One constant file (`backend/app/wind/scope.py`) holds the window.

**D-25 Decision cutoff.** The PRD says only "one day before the delivery day". Default 09:20 UK time on D-1 (EPEX GB day-ahead gate closure), preset 09:50 (N2EX), free time input. Sources: Nord Pool support page
(N2EX 09:50) and EPEX (10:20 CET = 09:20 UK); a 2020 trade-press note says 09:40 for N2EX, hence "editable". The forecast "available" is the newest WINDFOR run published at or before the cutoff, per hour.

**D-26 Alignment of hourly forecast and half-hourly outturn.** Compare the forecast for start time T with the outturn whose start time is T (the literal PRD reading). Tested alternatives (T+30, hourly mean, T-30..T, centred)
move MAE between 2,060 and 2,105 MW (<2%), so the choice does not drive any conclusion; this is stated on the Method page.

**D-27 Error = forecast - outturn** (positive = forecast too high = wind came in below it, the costly side for a buyer). Red = over-forecast, blue = under-forecast everywhere.

**D-28 A committed snapshot, not live Elexon calls.** January 2026 is history. The 147 KB snapshot makes cold starts network-free and the app immune to Elexon outages; `python -m app.wind.ingest` rebuilds it and fails on gaps, conflicting
duplicates, non-hourly runs or any row it would drop. Reversible: `routes.py` could call the client instead.

**D-29 Pure-Python analytics, minimal API dependencies.** No pandas/numpy in the API, so the serverless bundle is FastAPI plus a few tens of KB. Requirements are split: `requirements.txt` (deployed API), `backend/requirements.txt` (adds uvicorn),
`backend/requirements-data.txt` (NESO pipeline only), `backend/requirements-dev.txt` (everything plus pytest/httpx).

**D-30 Planning band.** P10-P90 of past error for forecasts of a similar size: data-driven quartiles of the forecast, interpolated linearly between quartile centres (hard steps made the plotted band jump), the viewed day excluded from its own band.
It is in-sample for the window (uses later days) and says so. Calibration check on the real data: the band contains 78.4% of outturns (nominal 80%), pinned by a test.

**D-31 No procurement volume.** With wind data only, the app reports "wind to count on" (the band's lower edge) and the error statistics. It does not invent a total buy volume; the Method page says why.

**D-32 Hand-written SVG charts, no chart library.** The dataviz spec (2px lines, <=24px bars with a 4px rounded end and 2px gap, ringed markers, snapping crosshair, 24px scatter reach, table twin for every chart, light/dark steps) needed fine control,
and it keeps the front end to React alone (265 KB, 82 KB gzipped). Palette validated with the dataviz validator in both modes (all PASS).

**D-33 Missing hours are shown as missing.** At a very early cutoff the newest run does not reach the end of the delivery day (a 22:30 run looks 46.5 h ahead). The API lists `hours_without_forecast`, the chart leaves them blank and a notice explains; nothing is estimated.

**D-34 Vercel deployment by direct file upload, not Git.** The connected Vercel team has no write access to `SayAn1-dls/full-stack` (`repo_no_access`), so the project is not Git-linked: pushes to GitHub do **not** redeploy. To redeploy, upload again or link the repository from an account with access.
The data snapshot's SHA-256 is exposed by `/api/health` so a deployment can be checked against the committed file. The project is `wind-intelligence` in team `tathagat-harshs-projects`, the account the user confirmed.

**D-35 Docker was verified in the sandbox with local shim base images.** The sandbox re-terminates TLS and rate-limits Docker Hub, so builds used local base images that trust the sandbox CA (and a Google mirror of the same node/nginx images). The repository
Dockerfiles are unchanged and portable; TLS verification was never disabled.

**D-36 Python 3.12 is the compatibility target** (a likely serverless default); the full suite (206 tests at that point) was run on 3.12.15 in a clean container as well as on 3.13.
