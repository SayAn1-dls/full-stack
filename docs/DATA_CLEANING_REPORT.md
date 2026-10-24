# Data cleaning report: NESO historic GB demand, 2009-2024

All numbers in this report were produced by running the pipeline (`run_manifest.json`, `reference_checks.json`) or the
test suite on 2026-10-24. Where a number is a hand-check from the audit stage it says so.

## 1. Scope limits (read first)

- **This is NESO demand data, not Elexon data.** It is *not* FUELHH (actual generation by fuel) or WINDFOR (wind
  forecasts), which the Wind Intelligence app evaluates. `embedded_wind_generation` is NESO's *model estimate* of
  distribution-connected wind only, not transmission-metered national wind output.
- **Coverage ends 2024-12-05** in the audited files this pipeline processes. It does not cover January 2026, the
  Wind Intelligence target period.
- **Purpose:** supporting context only (demand level, seasonality, long-run embedded wind/solar trends). It is not
  merged with Elexon data, not shown as forecast or actual national wind, and not wired into any app. The product PRD
  limits the application to Elexon wind actuals and forecasts ("no other data beyond this"), so the optional
  "hook into Wind Intelligence" step was deliberately not built (DECISIONS.md D-18).
- **Newer NESO data exists, outside this audit.** NESO's portal today also serves 2025 and a 2026 file that does
  contain January 2026 (31 days, 1,488 periods) in a newer schema (extra `forecast_actual_indicator` column). The
  pipeline would stop on that file with a `SchemaError`; ingesting it would be a separate, deliberate piece of work
  and is out of the PRD's scope.

## 2. Inputs and vintage

All 18 files were located in `data/raw/` and verified against the SHA-256 fingerprints in the brief: **18 of 18 match**
(test: `test_raw_file_sha256_matches_the_audited_fingerprint`, 18 cases).

| Where the bytes came from | Files |
|---|---|
| Kaggle bundle "Electricity Consumption UK 2009-2024" (albertovidalrod, ODbL 1.0), fetched with `python -m app.data.fetch_raw_data`; every file verified before install | all 16 yearly files and both combined files |
| NESO Data Portal, https://www.neso.energy/data-portal/historic-demand-data | 2009-2018 yearly files are **byte-identical** to the Kaggle copies (same SHA-256). NESO serves them as `demanddata_YYYY.csv`; they are stored under the brief's names `historic_demand_year_YYYY.csv`. |

**NESO has re-published 2019-2024 since the audit.** Downloading those years straight from NESO today gives different
bytes (hashes below) than the audited files, so the pipeline would refuse them (`HashMismatchError`). The audited
vintage is kept on purpose; `python -m app.data.compare_neso_current` quantifies the difference (run on 2026-10-24):

| Year | Rows audited / NESO now | Cells that differ (audited vs NESO now) |
|---|---|---|
| 2019 | 17,520 / 17,520 | `embedded_wind_generation` 16,794; `embedded_solar_generation` 9,257; `embedded_solar_capacity` 17,520; `nd`/`tsd`/`england_wales_demand` 10-11 each; a few flows 6-25 each |
| 2020 | 17,568 / 17,568 | `embedded_wind_generation` 17,532; `embedded_solar_generation` 9,046; `embedded_solar_capacity` 17,424; a handful of demand/flow cells (2 each) |
| 2021 | 17,520 / 17,520 | `embedded_wind_generation` 17,458; `embedded_solar_generation` 9,441; `embedded_solar_capacity` 17,520 |
| 2022 | 17,520 / 17,520 | `embedded_wind_generation` 15,444; `embedded_solar_generation` 8,775; `embedded_solar_capacity` 17,520; a handful of demand/flow cells (1-5 each) |
| 2023 | 17,520 / 17,520 | `embedded_solar_generation` 8,800; `embedded_solar_capacity` 17,520; `scottish_transfer` 1,340; `tsd` 66; a few others (1-4 each) |
| 2024 | 16,320 / **17,568** | `embedded_solar_generation` 8,236; `embedded_solar_capacity` 16,320; `tsd` 276; `greenlink_flow` 275; **1,248 extra periods, 2024-12-06 to 2024-12-31** |

Notes on reading that table:

- `viking_flow` and `greenlink_flow` also show "changes" of 17,520 cells in 2019-2022 (and `greenlink_flow` in 2023): the
  re-published files now *publish those columns* (as 0) for years where the audited files had no such column. That is a schema
  addition, not a value revision.
- NESO says on the portal that it applies retrospective corrections to solar and demand data months after first
  publication. The re-modelled embedded wind/solar estimates mean **embedded wind/solar values here are a vintage, not
  the latest NESO estimate.** Any comparison with a newer NESO download must account for that.
- 275 `greenlink_flow` cells in NESO's current 2024 file are non-zero where the audited file has 0 - evidence that the
  audited zeros were a placeholder, not measured zero flow (section 5.6).
- NESO's current 2023 file writes dates as `DD-Mon-YY` (two-digit year). The pipeline rejects that format by design
  (only `DD-MON-YYYY` and `YYYY-MM-DD` are accepted), which is another reason a hash mismatch must stop the run.

SHA-256 of NESO's current files (2026-10-24), for the record: 2019 `0084d546...`, 2020 `7121b6fb...`, 2021 `b9f7285f...`,
2022 `fc6bd5d5...`, 2023 `cb6f7b91...`, 2024 `fa7895b6...`.

## 3. Schema eras

Mapped by normalised name (lowercase, stripped), never by position. Observed in the files (`run_manifest.json`):

| Files | Header | Date format | Line endings | Power columns published (of 20) |
|---|---|---|---|---|
| 2009-2018 | UPPERCASE | `DD-MON-YYYY` | CRLF | 15 |
| 2019-2021 | UPPERCASE | `DD-MON-YYYY` | CRLF | 17 (+`nsl_flow`, `eleclink_flow`) |
| 2022 | lowercase | `YYYY-MM-DD` | LF | 17 |
| 2023 | lowercase | `YYYY-MM-DD` | LF | 19 (+`scottish_transfer`, `viking_flow`; `scottish_transfer` sits before `ifa_flow`) |
| 2024 | lowercase | `YYYY-MM-DD` | LF | 20 (+`greenlink_flow`) |

CRLF is present in 2009-2021, not just 2009 as the brief noted. The output schema is the union (20 power columns plus keys).
Tests build all five eras with the columns in normal and reversed order and check every value lands under the right name.

## 4. Before / after

| | Rows | Notes |
|---|---|---|
| Sum of the 16 yearly files (in) | **279,264** | 12 x 17,520 + 3 x 17,568 (leap years 2012, 2016, 2020) + 16,320 (2024, partial); per-file counts match the brief |
| `demand_clean` (out) | **279,264** | **0 rows dropped**, 0 days dropped |
| Combined file `historic_demand_2009_2024.csv` | 279,264 | same keys, 0 mismatching cells in all 20 columns |
| `historic_demand_2009_2024_noNaN.csv` | 278,512 | 752 rows lost (section 8) |

Cells changed by cleaning: **500 nulled** (479 `tsd` + 21 `england_wales_demand`); nothing else altered, nothing imputed.
Structural nulls (column not published that year): `nsl_flow` 175,296, `eleclink_flow` 175,296, `scottish_transfer` 245,424,
`viking_flow` 245,424, `greenlink_flow` 262,944 cells - kept as null, never 0.
Rows carrying at least one quality flag: **17,162** (16,320 of them only because of the `greenlink_flow` constant flag).

## 5. Anomalies: counts, dates, decisions

Each anomaly from the pre-audit was reproduced from the raw files (test `test_section_4_2_counts_reproduce_from_the_raw_files`)
and then from the pipeline output (`test_pipeline_flags_match_section_4_2`).

### 5.1 Structure (no anomaly)

- No duplicate `(settlement_date, settlement_period)` keys in any file; 5,818 calendar days.
- 5,786 days have 48 periods, **16 have 46** (the last Sunday of March, 2009-2024) and **16 have 50** (the last Sunday of
  October). Verified against an independently computed calendar. This is correct GB settlement behaviour.
- Periods are contiguous 1..N on every day. 2024 is partial: last row is 2024-12-05, period 48.

### 5.2 `tsd == 0`: invalid, nulled

479 rows on 15 days: 2009-08-29, 2009-08-30, 2010-07-09, 2010-07-10, 2010-07-13, 2010-07-14, 2012-05-29 to 2012-06-04
(7 days), 2012-06-11, 2012-10-14. Per year: 2009: 48, 2010: 96, 2012: 335. Those 15 days hold 720 periods; only 479 had `tsd == 0`,
so **241 periods on those days have valid TSD and are kept**. Decision: null the zero cell, flag `tsd_zero`, keep the row and the rest of the row.

### 5.3 `england_wales_demand == 0`: invalid, nulled

21 rows on 18 days: 2011-04-28, 2014-05-30, 2014-07-01, 2015-07-04, 2015-11-02, 2016-09-11, 2016-09-22, 2017-10-28,
2018-04-22, 2018-06-09, 2018-10-02, 2019-02-12 (2 periods), 2019-06-20 (2), 2019-08-04, 2019-10-01, 2019-10-20,
2020-01-06 (2), 2022-10-21. Same treatment (flag `england_wales_demand_zero`). `nd == 0` has no rows; the rule exists anyway.

### 5.4 `tsd < nd`: suspect, flagged (22 rows), not 501

The pre-audit's 501 reproduces from the raw data, but **479 of the 501 are the `tsd == 0` rows** just nulled; a nulled value is not a
"TSD below ND" reading. After nulling, **22 rows** remain and are flagged `tsd_below_nd` (value kept). All 22 are in 2016-2018:
2016-09-12 p37-38, 2016-09-26 p39, 2017-07-15 p25, 2017-07-16 p25, 2018-05-27 p23, 2018-06-10 p40-43, 2018-06-15 p15,
2018-08-13 p17, 2018-08-17 p35-41, 2018-09-22 p38-39, 2018-10-14 p22. Differences are small (1-137 MW). The identity
501 = 479 + 22 is asserted by a test.

### 5.5 Embedded wind above capacity: suspect, flagged (308 rows)

All 308 are in 2009-2011 (2009: 38, 2010: 32, 2011: 238) on 19 days; the largest excess is 380 MW. NESO describes capacity as "not
the definitive view", so this reads as a too-low early capacity estimate, not bad generation. Flag `wind_gen_above_capacity`, values kept.

### 5.6 `greenlink_flow` constant 0: flagged (16,320 rows)

Every 2024 row is 0. Flagged `constant_column:greenlink_flow` and kept as published - **not** read as measured zero flow. NESO's current
2024 file has 275 non-zero values for periods where the audited file has 0, which supports the placeholder reading. "Constant" is
defined at column level (one distinct value across the column's whole published history, at least 1,000 values), so only
`greenlink_flow` qualifies.

### 5.7 `non_bm_stor < 0`: suspect, flagged (13 rows, minimum -24)

2009-06-23 p32 (-24), 2010-04-13 p30, 2010-12-04 p3, 2011-02-02 p25, 2011-06-22 p33, 2011-06-30 p32-33, 2011-11-04 p33,
2011-11-17 p32, 2012-02-28 p36, 2012-04-03 p31, 2012-09-14 p33, 2012-09-27 p34. NESO's definition allows "generation or demand reduction", so small negatives may be genuine; flagged, not altered. One of the
13 rows (2011-02-02 period 25, -6 MW) also carries `wind_gen_above_capacity`; it is the only row with two flags.

### 5.8 Interconnector signs

Negative flows are valid and kept. NESO's schema: **negative = export out of GB, positive = import into GB**;
`scottish_transfer` positive = Scotland to England & Wales. All flow columns except the constant `greenlink_flow` contain negatives.

### 5.9 Findings beyond the brief

1. **`pump_storage_pumping` is never negative** (0 to 2,019) although NESO's schema says "the -ve signifies pumping load". Values are
   pumping-load magnitudes; kept as published and documented.
2. **Pre-commissioning zeros.** Several columns exist in the earliest files filled with 0 long before the asset existed. First
   non-zero reading (UTC), from the data: `britned_flow` 2011-01-27, `east_west_flow` 2012-07-26, `nemo_flow` 2019-02-01,
   `ifa2_flow` 2020-11-18, `embedded_solar_capacity` 2010-03-31; for the columns that are null before they are published,
   `nsl_flow` 2021-06-14, `eleclink_flow` 2021-09-17, `viking_flow` 2023-11-28. These zeros are not measured zero flow. They are *not*
   flagged row by row (it would mark most of the dataset); they are documented per column in the data dictionary.
3. **Six non-zero `england_wales_demand` readings look wrong against `nd`** (E&W/ND ratio is normally 0.86-0.98; median 0.909):

   | Date | Period | `nd` | `england_wales_demand` | Ratio |
   |---|---|---|---|---|
   | 2010-10-11 | 23 | 40,330 | 7,654 | 0.190 |
   | 2012-01-30 | 31 | 47,610 | 35,975 | 0.756 |
   | 2012-01-30 | 32 | 48,390 | 51,254 | 1.059 |
   | 2017-11-08 | 8 | 24,790 | 27,456 | 1.108 |
   | 2017-11-08 | 21 | 37,720 | 27,457 | 0.728 |
   | 2018-07-10 | 40 | 32,490 | 19,408 | 0.597 |

   **Not flagged and not altered.** The ratio has a continuous tail with no natural gap, so any cut-off would be arbitrary and would
   mislabel genuine readings; the brief's rule covers exact zeros only. Listed here for a human to review (DECISIONS.md D-16).

## 6. Timestamps

`period_start_utc` = local midnight of the settlement date (Europe/London) converted to UTC, plus `(settlement_period - 1) x 30` minutes;
`period_end_utc` = start + 30 min; `period_start_local` = the same instant on the UK wall clock with its offset. Midnight local is never
ambiguous or non-existent in the UK, and the conversion raises if that ever changed.

Verified on the full data (tests `test_period_start_utc_is_unique_monotonic_with_exact_30_minute_steps`,
`test_local_timestamps_are_dst_correct_on_every_row`):

- unique, strictly increasing, every step exactly 30 minutes, from 2009-01-01T00:00Z to 2024-12-05T23:30Z, and equal row-for-row to an
  independently built `date_range(..., freq="30min")`;
- the Europe/London calendar date of every period equals its settlement date, and on every ordinary 48-period day the wall clock is
  exactly `(period - 1) x 30` minutes.

Worked examples (unit tests): spring day 2024-03-31 has 46 periods and period 3 is 01:00 UTC = 02:00 BST (local 01:00 does not exist);
autumn day 2024-10-27 has 50 periods, periods 3-4 are 00:00/00:30 UTC (01:00/01:30 BST) and periods 5-6 are 01:00/01:30 UTC (01:00/01:30 GMT), so
the repeated local hour has distinct UTC times.

## 7. Completeness

`demand_daily_completeness.csv` has one row per Europe/London day from 2009-01-01 to 2024-12-05: 5,818 days, **all complete**, 0 missing and
0 unexpected periods, expected periods summing to 279,264. 2024-12-06 onward is out of coverage and is not reported as missing.

## 8. Why `historic_demand_2009_2024_noNaN.csv` must not be used

Reproduced from the file itself (`reference_checks.json`):

- It has 278,512 rows, **752 fewer** than the yearly files: 32 rows are periods 49-50 on the 16 autumn clock-change days, and 720 rows are
  *every* period of the 15 days that contain `tsd == 0` - **241 of those deleted rows had valid TSD**. Whole days were deleted to remove one bad column.
- It stamps `settlement_date` with a naive timestamp that ignores daylight saving. On 2024-03-31 period 3 is stamped 01:00 (a local time
  that does not exist; correct local start 02:00 BST) and the day ends at 22:30 (correct: 23:30 BST). On 2024-10-27 it has 48 rows where the
  day has 50, so the repeated hour is lost. In total 1,408 kept rows carry a wrong local clock time (32 are stamped with a non-existent time and 32 with an ambiguous one).
- It drops five columns (`scottish_transfer`, `nsl_flow`, `eleclink_flow`, `viking_flow`, `greenlink_flow`) and adds `period_hour`.
- Its *values* on the rows it keeps equal the yearly files exactly (0 mismatching cells) - the defect is in what it deleted and how it labels time.

Verdict: rejected as a source; used only to produce this section.

## 9. `is_holiday` recomputed and compared

The combined file's `is_holiday` is undocumented. It is constant within each day, 131 days / 6,288 rows. Tested against the `holidays` package
for each UK nation, it is a **subset of England's nominal list** (Wales's list is identical here; Northern Ireland's is a superset; Scotland's and the UK default's are not,
with 32 file days each that they do not list). Counting disagreements on observed (weekday) holidays, England and Wales tie as the closest match with 10; Northern Ireland and the UK default have 42, Scotland 90.
Definition used for the recomputed column `is_bank_holiday_ew`: an England & Wales bank holiday *observed* on that date (substitute days included, nominal
weekend dates excluded), from `holidays.UnitedKingdom(subdiv="England")` (package 0.107, weekdays only). That yields 131 days / 6,288 rows.
Cross-check against a frozen gov.uk snapshot (`backend/app/data/reference/bank_holidays_gov_uk.json`, retrieved 2026-10-24; gov.uk no longer carries years
before 2019): for 2019-01-01 to 2024-12-05, 49 days on each side and **0 differences**. 2009-2018 rely on the package alone.

**Every disagreement between the combined file and the recomputation (10 days, `is_holiday_disagreements.csv`):**

| Date | Weekday | In combined file | Recomputed | Finding |
|---|---|---|---|---|
| 2010-12-25 | Saturday | 1 | 0 | file flags Christmas Day on a weekend |
| 2010-12-27 | Monday | 0 | 1 | file misses the Christmas Day substitute holiday |
| 2011-12-25 | Sunday | 1 | 0 | file flags Christmas Day on a weekend |
| 2011-12-26 | Monday | 0 | 1 | file misses Boxing Day |
| 2016-12-25 | Sunday | 1 | 0 | file flags Christmas Day on a weekend |
| 2016-12-26 | Monday | 0 | 1 | file misses Boxing Day |
| 2021-12-25 | Saturday | 1 | 0 | file flags Christmas Day on a weekend (gov.uk: not a bank holiday that day) |
| 2021-12-27 | Monday | 0 | 1 | file misses the Christmas Day substitute (gov.uk lists it) |
| 2022-12-25 | Sunday | 1 | 0 | file flags Christmas Day on a weekend (gov.uk: not a bank holiday that day) |
| 2022-12-26 | Monday | 0 | 1 | file misses Boxing Day (gov.uk lists it) |

Interpretation: 5 days are a definitional difference (the file flags Christmas Day even when it falls on a weekend, which may be useful
for demand modelling but is not a bank holiday); **5 are genuine omissions** of weekday bank holidays. gov.uk confirms 2021-12-27 and 2022-12-26; for
2010, 2011 and 2016 only the `holidays` package confirms. The clean dataset does **not** carry the original `is_holiday`; it carries `is_bank_holiday_ew`.
Scotland-only and Northern Ireland-only holidays are not included.

## 10. Cross-validation against the combined file

`historic_demand_2009_2024.csv` was compared with the unified yearly data on `(settlement_date, settlement_period)` for **all 20 power columns**
(the pre-audit checked 5): 279,264 keys on both sides, 0 only in either, **0 mismatching cells**. Ground truth remains the yearly files.

## 11. Decisions and limitations

All decisions with justification are in `DECISIONS.md`. Known limitations:

- Embedded wind/solar values are the audited vintage, not NESO's latest re-modelled estimates (section 2).
- The six `england_wales_demand` outliers are listed but unflagged (section 5.9).
- 2009-2018 holiday definitions rest on one community-maintained package; only 2019+ has a second source.
- No imputed variant was produced (the brief makes this optional); `demand_clean` has gaps where readings were invalid.
- Two things were not built: the optional backend/UI hook (excluded by the PRD's Elexon-only scope) and anything outside the data pipeline
  (the dashboard, Docker packaging and deployment described in the PRD).

## 12. Reproduce

```
cd backend
pip install -r requirements-dev.txt
python -m app.data.fetch_raw_data      # only if data/raw is empty; verifies SHA-256 before installing
python -m app.data.clean_demand        # ~30 s; idempotent; writes data/interim and data/processed only
python -m app.data.build_docs          # regenerates docs/DATA_DICTIONARY.md
python -m pytest tests -q              # 129 tests (add -m "not data" for the 3-second logic suite)
```
