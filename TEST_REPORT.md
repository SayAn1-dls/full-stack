# Test report

Run on 2026-10-24, Linux, Python 3.13.17, pandas 3.0.5, pyarrow 26.0.0, holidays 0.107, pytest 9.1.1.

## Commands and results

| Command (from `backend/`) | Result |
|---|---|
| `python -m pytest tests -q` | **129 passed** in 62 s |
| `python -m pytest tests -q -m "not data"` | 86 passed (43 deselected) in 2.8 s |
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
- **Not tested:** anything outside the data pipeline (there is no API or UI yet).
