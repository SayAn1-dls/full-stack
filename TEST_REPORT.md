# Test report

Two parts: the **Wind Intelligence app** (React + FastAPI, deployed) and the **NESO demand pipeline** (supporting data, not used by the app).
Run on 2026-10-24, Linux, Python 3.13.17, Node 22.22.0, pandas 3.0.5, pyarrow 26.0.0, holidays 0.107, pytest 9.1.1, vitest 5.0.5.

## Part 1: Wind Intelligence app

### Commands and results

| Command | Result |
|---|---|
| `cd backend && python -m pytest tests -q` | **219 passed** in 63 s (129 NESO + 90 wind/deploy) |
| `python -m pytest tests -q -m "not data"` | 176 passed, 43 deselected, 9 s |
| `python -m pytest tests -q -k "wind or vercel"` | 90 passed, 6 s |
| `cd frontend && npm test` | 19 passed (2 files: scales, formatters) |
| `cd frontend && npx tsc --noEmit` | exit 0 |
| Playwright interaction suite, 19 checks (below) | 19/19 against the local build, 19/19 against the Docker stack, 19/19 against https://wind-intelligence.vercel.app |
| Python suite on 3.12.15 in a clean container | 206 passed, run earlier in the session; the final 219 ran on 3.13.17 only |

Nothing was skipped, deleted or weakened; the weak assertions found on review are in `BUG_LOG.md` (BUG-017).

The Playwright checks (`frontend/e2e/interact.cjs <baseUrl>`; Playwright is not a repository dependency, see the file header): headline figures on both views equal the API's numbers; the tooltip lists forecast, outturn, error and band; it disappears on leave; arrow keys drive the crosshair; the table view
has all 24 hours; showing other forecast runs adds lines; the 09:50 preset picks the 09:30 run and updates the URL; the next-day button moves the date; an early cutoff explains the missing hours; an out-of-scope day shows a clear error; 1 January is flagged
as decided on 31 December; the histogram bar tooltip works; the 7-day preset re-scopes every figure to 168 hours; the theme toggle sets `data-theme`; the Method page states the scope limits; the only failed request is the intentional out-of-scope one; there are no console errors.
The 390 px phone layout was checked by screenshot (BUG-014), not by an automated assertion. The committed copy of the script was re-run against the live site on 2026-10-24 (19/19 passed).

### What the app tests cover

- **Analytics on synthetic data** (`test_wind_analytics.py`): the forecast chosen at a cutoff is the newest publication at or before it (a run published exactly at the cutoff counts); the cutoff is D-1 in UK local time, including
  clock-change days; error sign and lead time; lower-inclusive horizon buckets; persistence uses only half-hours that have ended; the planning band is conditional on the forecast level, exact (P10/P50/P90 of a known sample), smooth across a bucket
  edge, and excludes the day being viewed; tied and tiny samples do not crash; missing hours are reported, not skipped.
- **API on the real snapshot** (`test_wind_api.py`): every endpoint is recomputed independently from the raw snapshot JSON and compared; the headline numbers in `docs/APP_DESIGN.md` are asserted; the P10-P90 band covers 72-88% of outturns
  (observed 78.4%, nominal 80%); scope 404s, bad time 422s, cache headers.
- **Ingest and loading** (`test_wind_ingest.py`, `test_wind_dataset.py`): gaps, conflicting duplicates, non-hourly runs and dropped rows all fail the build; serialisation is deterministic and round-trips; a gzipped snapshot loads to the same dataset and SHA-256;
  a missing or empty snapshot is a clear error; unordered publications are rejected.
- **Deployment** (`test_vercel_config.py`): `/api/*` is rewritten to the function, the entrypoint exposes the FastAPI app, every module the API imports is in the `includeFiles` bundle, the snapshot ships and the heavy NESO pipeline does not,
  and the serverless requirements stay tiny.

### Mutation checks on the app (re-run on the final code, 2026-10-24)

| Injected bug | Caught by |
|---|---|
| W1 a run published exactly at the cutoff is ignored | `test_latest_forecast_is_the_latest_publication_at_or_before_the_cutoff` |
| W2 error sign flipped (outturn - forecast) | 4+ tests, e.g. `test_pair_error_and_horizon`, `test_accuracy_view_recovers_a_constant_bias` |
| W3 the viewed day is not excluded from its own band | `test_decision_view_error_model_excludes_the_day_being_viewed`, `test_decision_summary_matches_its_hours` |
| W4 cutoff taken on the delivery day instead of D-1 | `test_decision_cutoff_is_previous_day_local_time` and 3 more |
| W5 horizon buckets upper-inclusive | `test_horizon_bucket_boundaries_are_lower_inclusive` |
| W6 persistence uses a half-hour that has not ended | `test_last_actual_before_uses_only_finished_half_hours` |
| W7 band P90 taken at P80 | **survived the first time**; fixed by `test_regression_band_edges_are_exactly_the_stated_percentiles` and `test_the_p10_p90_band_is_calibrated_on_the_real_data`, now caught by both (BUG-016) |
| W8 ingest keeps conflicting duplicates silently | `test_identical_duplicates_are_collapsed_but_conflicting_ones_fail` |

### Packaging and deployment checks

- **Docker:** `docker compose up --build` built both images and served the app on :8080 with nginx proxying `/api` to the API container; the Playwright suite passed against it. The sandbox re-terminates TLS and rate-limits Docker Hub, so the build used local shim base
  images that trust the sandbox CA and a Google mirror of the node/nginx images (`DECISIONS.md` D-35). The repository Dockerfiles were not changed for this, and TLS verification was never disabled. A build against the stock base images on an unrestricted network was not run.
- **Vercel:** deployment `dpl_Czyqk1XsNCe8jaXSxv6TzC5bkJD2` (commit `2e6fc52`) is READY and publicly reachable without authentication; `/api/health` returns the committed snapshot's SHA-256 (`da46ed49...3307`);
  all 41 API requests I compared against the local server returned byte-identical bodies; no runtime errors or warnings were logged in the 30 minutes checked; API responses took about 0.2-0.3 s.
- Not exercised: a Vercel cold start under load, other browsers than Chromium, and a screen reader.

### Remaining risks and gaps (app)

- **The deployment is not Git-linked**, so a push does not redeploy it; the live site runs commit `2e6fc52`, and later commits (documentation only) are not in it.
- **One month, one source.** The +1.8 GW over-forecast is an observation of January 2026, not a general property of WINDFOR, and its cause cannot be determined from Elexon data. The band is in-sample for the window.
- **Decision cutoff is an assumption** (09:20 UK default; the PRD only says "one day before"). The Method page says so and the control is editable.
- **No total buy volume**: demand and prices are out of scope per the PRD.
- **The tests were written alongside the code**, not test-first; the mutation table is the evidence they can fail, and it found one real gap (W7).
- **No CI** is configured in this repository; everything above was run in this session.

## Part 2: NESO demand data pipeline

### Commands and results

| Command (from `backend/`) | Result |
|---|---|
| `python -m pytest tests -q -k "not wind and not vercel"` | **129 passed** in about 60 s (part of the 219 above) |
| `python -m pytest tests -q -m "not data"` | 86 NESO logic tests (the 176 above also include the 90 wind/deploy tests) in about 3 s |
| `python -m pytest tests -q -m data` | 43 passed (about 60 s; one full pipeline run is shared, a second one proves idempotency) |
| `python -m app.data.clean_demand` | `OK: 279264 rows in, 279264 rows out, 17162 rows carry a quality flag` (about 27 s) |

Nothing was skipped, deleted or weakened. A missing raw file makes the real-data suite *fail* with the fix command rather than skip.

## What is covered

**Logic suite (86 tests, small deterministic fixtures, `tests/test_demand_logic.py`)**

- Both date formats parse; 11 garbage strings and 5 impossible calendar dates raise.
- Header normalisation maps all five schema eras (built with columns in normal and reversed order) to one schema, values landing under the right name;
  the 2023 `scottish_transfer`-before-`ifa_flow` order is checked explicitly; unknown columns, blank, non-numeric, non-integer and out-of-range cells fail loudly.
- Timestamps: winter day (UTC = local), summer day (UTC = local - 1 h), spring day (46 periods, period 3 = 01:00 UTC = 02:00 BST, a 47th period is rejected),
  autumn day (50 periods, periods 3-4 and 5-6 cover the repeated local hour with distinct UTC times, a 51st is rejected); exact 30-minute steps across both clock changes; gaps fail.
- `tsd == 0` becomes NaN with the right flag and every other cell of the row is untouched; `england_wales_demand == 0` and `nd == 0` likewise; zeros in other columns are kept;
  negative flows keep their sign.
- Suspect flags trigger exactly at their thresholds (`tsd == nd` no, `tsd == nd - 1` yes; wind generation equal to capacity no, +1 yes; storage 0 no, -1 yes); constant-column rule
  (enough published values, one distinct value); multi-flag string order.
- Duplicate keys fail hard (function level and full run); `period_start_utc` duplicates fail.
- Era files with missing columns give NA, never 0; the reason table records `column_not_published`.
- Completeness: a truncated final day and a mid-day gap both fail (the completeness CSV is written first); hash mismatch fails by default and is recorded under `--allow-hash-mismatch`;
  outputs inside the raw directory are refused; a missing raw file names the fix.
- End to end on fixtures across a year boundary and two eras, and across a spring and an autumn clock change; CSV round trip; holiday calendar facts (Boxing Day, substitute days,
  royal wedding 2011, Diamond Jubilee 2012, Platinum Jubilee 2022, state funeral 2022, coronation 2023, Northern Ireland-only days excluded).

**Real-data suite (43 tests, marker `data`, `tests/test_demand_real_data.py`)** - the raw files are re-read with an independent reader so comparisons are not circular.

- SHA-256 of all 18 raw files equals the audited fingerprint (18 parametrised cases); 18 files present.
- Raw files byte-identical before and after the pipeline ran.
- Output rows = 279,264 = rows in; 0 dropped; per-file counts as in the brief.
- `period_start_utc` unique, monotonic, every step exactly 30 minutes, 2009-01-01T00:00Z to 2024-12-05T23:30Z, equal row for row to an independently built `date_range`;
  every period's Europe/London date equals its settlement date; on ordinary days the wall clock equals `(period - 1) x 30` minutes.
- Exactly 16 days with 46 periods (last Sunday of March) and 16 with 50 (last Sunday of October), 5,786 with 48; periods contiguous 1..N.
- Section 4.2 counts from the raw files (479 rows / 15 dates, 21, 501, 308, 13, 0 for `nd`) and from the pipeline flags (479, 21, 22 = 501 - 479, 308, 13); `greenlink_flow` the only constant column, kept as 0.
- Cleaned values equal raw values everywhere except the 500 cells nulled by a rule, and each nulled cell was exactly 0 in a rule column.
- Structurally missing columns are NaN before their first published date and never 0; the reason table totals match.
- Idempotency: two full runs give byte-identical CSVs and reports and equal parquet tables and manifests (apart from the `run` timing block).
- The committed `data/processed/` equals a fresh run; `docs/DATA_DICTIONARY.md` equals a fresh render.
- Combined file: 279,264 keys on both sides, 0 mismatching cells in all 20 columns. noNaN file: 752 rows lost = 32 + 720 (241 with valid TSD), the 2024-03-31 and 2024-10-27 timestamp errors, 1,408 mislabelled rows.
  `is_holiday`: 131 days / 6,288 rows, the 10 disagreements listed by date, gov.uk cross-check 0 differences for 2019+.

## Do the tests have teeth? Mutation checks

Each bug was injected into a copy of the code and the suite re-run; every one was caught by the intended tests:

| Injected bug | Caught by (first failures) |
|---|---|
| Ignore DST (treat local midnight as UTC) | `test_summer_day_utc_is_local_minus_one_hour`, `test_spring_day_has_46_periods_and_period_3_...`, `test_spring_day_rejects_a_47th_period`, `test_autumn_day_has_50_periods_...` |
| Remove the `tsd == 0` rule | `test_tsd_zero_becomes_na_flagged_and_the_rest_of_the_row_is_kept` and 3 more |
| Fill unpublished columns with 0 | `test_missing_column_eras_produce_na_never_zero`, `test_end_to_end_fixture_run_across_a_year_boundary_and_two_eras` |
| `tsd_below_nd` uses `<=` | `test_suspect_flags_trigger_exactly_at_their_thresholds` |
| Also null `ifa2_flow` zeros (real data) | `test_cleaned_values_equal_raw_values_except_cells_nulled_by_a_rule`, `test_structurally_missing_columns_are_na_with_a_reason_never_zero` |

CLI behaviour checked by hand: a tampered raw copy exits 1 with `HashMismatchError` and writes nothing; `--allow-hash-mismatch` completes and records the mismatching file; outputs inside the raw dir
exit 1; `fetch_raw_data` installs 18 verified files, is a no-op on re-run, and refuses to overwrite a file whose hash differs.

## Bugs found

See `BUG_LOG.md`: one audit-report counter bug (fixed, regression-tested), two reporting/label issues, several test-fixture mistakes, and drafting errors in the report. No defect surfaced in the core cleaning logic.

## Remaining risks and gaps

- **Test order.** The audit was reproduced first, but the implementation and its tests were written close together rather than test-first; the mutation checks above are the evidence the tests can fail.
- **Vintage.** Tests pin the audited files by SHA-256. NESO's re-published 2019-2024 files (different hashes, 2024 complete, 2023 with two-digit-year dates) are deliberately rejected; ingesting them is separate work.
- **2009-2018 holidays** depend on a single community-maintained package (only 2019+ has a second source, gov.uk).
- **Six `england_wales_demand` outliers** are reported but not flagged (DECISIONS D-16).
- **pandas 3 / Python 3.13 only.** No other versions were run; dependencies are pinned.
- **No CI** is configured in this repository; the suite was run locally in this session only.
- **Not tested here:** anything outside the data pipeline. This part's output is not served by the app (Part 1 covers the app).
