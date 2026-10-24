"""Slow suite against the real NESO files in data/raw (run with `pytest -m data`).

The expected numbers come from the audit brief (Sections 3.3, 4.1, 4.2). The raw files are re-read here
with a deliberately independent reader so cleaned-vs-raw comparisons are not circular.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import pytest
from conftest import RAW_DIR, REPO_ROOT, require_raw_files, raw_hashes

from app.data.clean_demand import load_expected_hashes, sha256_file
from app.data.demand_schema import POWER_COLUMNS

pytestmark = pytest.mark.data

EXPECTED_ROWS = 279_264
TSD_ZERO_DATES = [
    "2009-08-29", "2009-08-30", "2010-07-09", "2010-07-10", "2010-07-13", "2010-07-14",
    "2012-05-29", "2012-05-30", "2012-05-31", "2012-06-01", "2012-06-02", "2012-06-03", "2012-06-04",
    "2012-06-11", "2012-10-14",
]


@lru_cache(maxsize=1)
def independent_raw() -> pd.DataFrame:
    """Read the 16 yearly files without any pipeline code: names lowercased, dates parsed per file."""
    require_raw_files()
    frames = []
    for year in range(2009, 2025):
        frame = pd.read_csv(RAW_DIR / f"historic_demand_year_{year}.csv", dtype=str)
        frame.columns = [c.strip().lower() for c in frame.columns]
        text = frame["settlement_date"].str.strip()
        fmt = "%Y-%m-%d" if text.str.match(r"^\d{4}-\d{2}-\d{2}$").all() else "%d-%b-%Y"
        frame["date"] = pd.to_datetime(text, format=fmt)
        frame["sp"] = frame["settlement_period"].astype(int)
        for column in frame.columns:
            if column in POWER_COLUMNS:
                frame[column] = pd.to_numeric(frame[column]).astype("float64")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def last_sunday(year: int, month: int) -> date:
    day = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


# ----------------------------------------------------------------------------- inputs


@pytest.mark.parametrize("name", list(load_expected_hashes()))
def test_raw_file_sha256_matches_the_audited_fingerprint(name):
    require_raw_files()
    expected = load_expected_hashes()[name]
    actual = sha256_file(RAW_DIR / name)
    assert actual == expected, (
        f"{name} differs from the audited file (expected {expected}, got {actual}). "
        "Re-run the audit for this file instead of trusting Section 4."
    )


def test_all_18_raw_files_are_present():
    assert len(list(RAW_DIR.glob("*.csv"))) == 18


def test_raw_files_are_byte_identical_before_and_after_the_pipeline_runs(real_run):
    assert real_run.hashes_before == real_run.hashes_after == raw_hashes()


# ----------------------------------------------------------------------------- rows and time axis


def test_no_rows_dropped(real_run):
    expected_rows = sum(e["rows"] for n, e in json.loads(
        (REPO_ROOT / "backend/app/data/expected_hashes.json").read_text()).items() if "year" in n)
    assert expected_rows == EXPECTED_ROWS
    assert len(real_run.df) == EXPECTED_ROWS
    assert real_run.manifest["rows_in"] == real_run.manifest["rows_out"] == EXPECTED_ROWS
    assert real_run.manifest["rows_dropped"] == 0
    assert real_run.manifest["inputs"]["historic_demand_year_2012.csv"]["rows"] == 17_568


def test_period_start_utc_is_unique_monotonic_with_exact_30_minute_steps(real_run):
    start = real_run.df["period_start_utc"]
    assert start.is_unique and start.is_monotonic_increasing
    assert (start.diff().dropna() == pd.Timedelta(minutes=30)).all()
    assert start.iloc[0] == pd.Timestamp("2009-01-01T00:00Z")
    assert start.iloc[-1] == pd.Timestamp("2024-12-05T23:30Z")
    # Independent construction of the whole axis must match row for row.
    pd.testing.assert_index_equal(
        pd.DatetimeIndex(start), pd.date_range("2009-01-01T00:00Z", "2024-12-05T23:30Z", freq="30min", unit="ns"),
        check_names=False)
    assert (real_run.df["period_end_utc"] - start == pd.Timedelta(minutes=30)).all()


def test_local_timestamps_are_dst_correct_on_every_row(real_run):
    df = real_run.df
    local = df["period_start_local"]
    assert str(local.dt.tz) == "Europe/London"
    assert (local.dt.tz_convert("UTC") == df["period_start_utc"]).all()
    # the Europe/London calendar date of every period is its settlement date ...
    assert (local.dt.date == df["settlement_date"]).all()
    # ... and on ordinary 48-period days the wall clock is exactly (period - 1) x 30 minutes
    length = df.groupby("settlement_date")["settlement_period"].transform("size")
    minutes = local.dt.hour * 60 + local.dt.minute
    normal = length == 48
    assert (minutes[normal] == (df.loc[normal, "settlement_period"] - 1) * 30).all()


def test_exactly_16_days_with_46_periods_and_16_with_50(real_run):
    sizes = real_run.df.groupby("settlement_date").size()
    assert sizes.value_counts().to_dict() == {48: 5786, 46: 16, 50: 16}
    short = {d for d in sizes.index[sizes == 46]}
    long = {d for d in sizes.index[sizes == 50]}
    assert short == {last_sunday(y, 3) for y in range(2009, 2025)}   # last Sunday of March
    assert long == {last_sunday(y, 10) for y in range(2009, 2025)}   # last Sunday of October
    assert real_run.manifest["days"]["by_length_periods"] == {"46": 16, "48": 5786, "50": 16}


def test_periods_are_contiguous_1_to_n_and_keys_unique(real_run):
    df = real_run.df
    grouped = df.groupby("settlement_date")["settlement_period"].agg(["min", "max", "size"])
    assert (grouped["min"] == 1).all() and (grouped["max"] == grouped["size"]).all()
    assert not df.duplicated(["settlement_date", "settlement_period"]).any()


def test_coverage_ends_2024_12_05_and_nothing_is_invented_after(real_run):
    df = real_run.df
    assert df["settlement_date"].max() == date(2024, 12, 5)
    assert (df["settlement_date"] > date(2024, 12, 5)).sum() == 0 and (df["period_start_utc"].dt.year >= 2026).sum() == 0
    assert df.loc[df["settlement_date"] == date(2024, 12, 5), "settlement_period"].max() == 48
    assert "out of coverage" in real_run.manifest["coverage"]["note"]


def test_daily_completeness_report_covers_every_day_and_all_are_complete(real_run):
    table = pd.read_csv(real_run.processed / "demand_daily_completeness.csv")
    assert len(table) == 5818 and table["complete"].all()
    assert table["expected_periods"].sum() == table["present_periods"].sum() == EXPECTED_ROWS
    assert table["missing_periods"].sum() == 0 and table["unexpected_periods"].sum() == 0
    assert table["settlement_date"].iloc[-1] == "2024-12-05"
    assert table["flagged_periods"].sum() == real_run.manifest["rows_flagged"]["any_flag"]


# ----------------------------------------------------------------------------- Section 4.2 anomalies


def test_section_4_2_counts_reproduce_from_the_raw_files():
    raw = independent_raw()
    assert (raw["tsd"] == 0).sum() == 479
    assert raw.loc[raw["tsd"] == 0, "date"].nunique() == 15
    assert sorted(raw.loc[raw["tsd"] == 0, "date"].dt.strftime("%Y-%m-%d").unique()) == TSD_ZERO_DATES
    assert (raw["england_wales_demand"] == 0).sum() == 21
    assert (raw["tsd"] < raw["nd"]).sum() == 501
    assert (raw["embedded_wind_generation"] > raw["embedded_wind_capacity"]).sum() == 308
    assert (raw["non_bm_stor"] < 0).sum() == 13 and raw["non_bm_stor"].min() == -24
    assert (raw["nd"] == 0).sum() == 0


def test_pipeline_flags_match_section_4_2(real_run):
    flagged = real_run.manifest["rows_flagged"]
    assert flagged["flag_tsd_zero"] == 479
    assert flagged["flag_england_wales_demand_zero"] == 21
    assert flagged["flag_nd_zero"] == 0
    assert flagged["flag_wind_gen_above_capacity"] == 308
    assert flagged["flag_negative_stor"] == 13
    # 501 raw "tsd < nd" rows = 479 invalid zeros (nulled) + 22 genuine suspects (flagged)
    tsd = real_run.manifest["tsd_below_nd"]
    assert tsd["raw_rows"] == 501 and tsd["after_invalid_nulling"] == 22 == flagged["flag_tsd_below_nd"]
    assert tsd["raw_rows"] == flagged["flag_tsd_zero"] + flagged["flag_tsd_below_nd"]
    assert real_run.df["flag_tsd_zero"].sum() == 479 and real_run.df["flag_negative_stor"].sum() == 13


def test_greenlink_is_the_only_constant_column_and_is_flagged_not_nulled(real_run):
    df = real_run.df
    assert list(real_run.manifest["constant_columns"]) == ["greenlink_flow"]
    assert df["flag_constant_column"].sum() == 16_320
    published = df[df["greenlink_flow"].notna()]
    assert len(published) == 16_320 and (published["greenlink_flow"] == 0).all()  # kept as published
    assert set(published["source_file"]) == {"historic_demand_year_2024.csv"}
    assert published["quality_flags"].str.contains("constant_column:greenlink_flow").all()


def test_invalid_zero_dates_are_nulled_for_the_whole_day_only_where_the_reading_was_zero(real_run):
    df = real_run.df
    nulled = df[df["tsd"].isna()]
    assert len(nulled) == 479 and sorted(nulled["settlement_date"].astype(str).unique()) == TSD_ZERO_DATES
    # the 241 other periods on those 15 days keep valid TSD, so the day was not dropped
    on_zero_days = df[df["settlement_date"].astype(str).isin(TSD_ZERO_DATES)]
    assert len(on_zero_days) == 720 and on_zero_days["tsd"].notna().sum() == 241


# ----------------------------------------------------------------------------- cleaned == raw except nulled cells


def test_cleaned_values_equal_raw_values_except_cells_nulled_by_a_rule(real_run):
    raw, clean = independent_raw(), real_run.df.copy()
    clean["date"] = pd.to_datetime(clean["settlement_date"])
    merged = clean.merge(raw, left_on=["date", "settlement_period"], right_on=["date", "sp"],
                         suffixes=("", "_raw"), validate="one_to_one")
    assert len(merged) == EXPECTED_ROWS
    rule_columns = {"nd", "tsd", "england_wales_demand"}
    nulled_total = 0
    for column in POWER_COLUMNS:
        cleaned = merged[column].astype("float64")
        original = merged[f"{column}_raw"]
        both = cleaned.notna() & original.notna()
        assert (cleaned[both] == original[both]).all(), f"{column}: a cleaned value differs from raw"
        became_null = cleaned.isna() & original.notna()
        if column in rule_columns:
            assert (original[became_null] == 0).all(), f"{column}: only exact zeros may be nulled"
        else:
            assert not became_null.any(), f"{column}: no cell may be nulled by a rule"
        assert not (cleaned.notna() & original.isna()).any(), f"{column}: a value appeared from nowhere"
        nulled_total += int(became_null.sum())
    assert nulled_total == 479 + 21


def test_structurally_missing_columns_are_na_with_a_reason_never_zero(real_run):
    df = real_run.df
    expected_absent = {  # first period start (UTC) at which a column is published
        "nsl_flow": "2019-01-01", "eleclink_flow": "2019-01-01", "scottish_transfer": "2023-01-01",
        "viking_flow": "2023-01-01", "greenlink_flow": "2024-01-01",
    }
    for column, first in expected_absent.items():
        before = df[df["settlement_date"] < date.fromisoformat(first)]
        assert before[column].isna().all(), column
        assert not (before[column] == 0).any(), column
        after = df[df["settlement_date"] >= date.fromisoformat(first)]
        assert after[column].notna().all(), column
    profile = real_run.manifest["column_profile"]
    assert profile["nsl_flow"]["null_rows"] == 175_296 and profile["scottish_transfer"]["null_rows"] == 245_424
    assert profile["greenlink_flow"]["null_rows"] == 262_944
    reasons = pd.read_csv(real_run.processed / "demand_null_reasons.csv")
    structural = reasons[reasons["reason"] == "column_not_published"]
    assert set(structural["column"]) == set(expected_absent)
    assert structural.groupby("column")["rows"].sum().to_dict() == {
        "nsl_flow": 175_296, "eleclink_flow": 175_296, "scottish_transfer": 245_424,
        "viking_flow": 245_424, "greenlink_flow": 262_944}
    invalid = reasons[reasons["reason"] == "invalid_zero_reading"].groupby("column")["rows"].sum().to_dict()
    assert invalid == {"tsd": 479, "england_wales_demand": 21}


def test_negative_flows_keep_their_sign(real_run):
    df = real_run.df
    signed = [c for c in POWER_COLUMNS if c.endswith("_flow") and c != "greenlink_flow"] + ["scottish_transfer"]
    for column in signed:
        assert (df[column] < 0).sum() > 0, column
    assert not (df["greenlink_flow"].dropna() != 0).any()   # the constant-zero placeholder column
    assert real_run.manifest["column_profile"]["ifa_flow"]["min"] == -2056
    assert (df["pump_storage_pumping"].dropna() >= 0).all()   # documented: values are magnitudes


def test_output_schema_types_and_flags(real_run):
    df = real_run.df
    assert df.columns[:5].tolist() == ["period_start_utc", "period_end_utc", "period_start_local",
                                       "settlement_date", "settlement_period"]
    assert str(df["period_start_utc"].dt.tz) == "UTC"
    assert all(str(df[c].dtype) == "Int64" for c in POWER_COLUMNS)
    assert all(df[c].dtype == bool for c in df.columns if c.startswith("flag_"))
    assert (df["quality_flags"] == "ok").sum() == len(df) - real_run.manifest["rows_flagged"]["any_flag"]
    assert df["source_file"].nunique() == 16 and df["quality_flags"].notna().all()
    csv_head = pd.read_csv(real_run.processed / "demand_clean.csv", nrows=3)
    assert csv_head.columns.tolist() == df.columns.tolist()


# ----------------------------------------------------------------------------- idempotency and committed outputs


def test_pipeline_is_idempotent(real_run, real_run_again):
    assert (real_run.processed / "demand_clean.csv").read_bytes() == (real_run_again.processed / "demand_clean.csv").read_bytes()
    pd.testing.assert_frame_equal(real_run.df, real_run_again.df)
    for name in ("demand_daily_completeness.csv", "demand_null_reasons.csv", "reference_checks.json",
                 "is_holiday_disagreements.csv"):
        assert (real_run.processed / name).read_bytes() == (real_run_again.processed / name).read_bytes(), name
    strip = lambda m: {k: v for k, v in m.items() if k != "run"}  # noqa: E731  (timing/versions differ by run)
    assert strip(real_run.manifest) == strip(real_run_again.manifest)


def test_committed_processed_outputs_are_up_to_date():
    committed = REPO_ROOT / "data" / "processed"
    for name in ("demand_clean.parquet", "demand_daily_completeness.csv", "run_manifest.json"):
        if not (committed / name).exists():
            pytest.fail(f"{committed / name} is missing: run `cd backend && python -m app.data.clean_demand`", pytrace=False)


def test_committed_outputs_equal_a_fresh_run(real_run):
    committed = REPO_ROOT / "data" / "processed"
    pd.testing.assert_frame_equal(pd.read_parquet(committed / "demand_clean.parquet"), real_run.df)
    for name in ("demand_daily_completeness.csv", "demand_null_reasons.csv", "reference_checks.json",
                 "is_holiday_disagreements.csv"):
        assert (committed / name).read_bytes() == (real_run.processed / name).read_bytes(), name
    on_disk = json.loads((committed / "run_manifest.json").read_text())
    strip = lambda m: {k: v for k, v in m.items() if k != "run"}  # noqa: E731
    assert strip(on_disk) == strip(json.loads((real_run.processed / "run_manifest.json").read_text()))
    if (committed / "demand_clean.csv").exists():
        assert sha256_file(committed / "demand_clean.csv") == sha256_file(real_run.processed / "demand_clean.csv")


# ----------------------------------------------------------------------------- combined files and is_holiday


@pytest.fixture(scope="module")
def reference(real_run):
    assert real_run.manifest["reference_checks"]["status"] == "ran"
    return json.loads((real_run.processed / "reference_checks.json").read_text())


def test_combined_file_matches_the_yearly_files_on_every_key_and_column(reference):
    cv = reference["combined_file_cross_validation"]
    assert cv["keys_in_both"] == EXPECTED_ROWS and cv["keys_only_in_yearly"] == cv["keys_only_in_combined"] == 0
    assert cv["mismatching_cells_total"] == 0 and len(cv["columns_compared"]) == 20
    for column in ("nd", "tsd", "embedded_wind_generation", "ifa_flow", "scottish_transfer"):  # pre-audit set
        assert cv["mismatching_cells_by_column"][column] == 0


def test_nonan_file_defects_reproduce(reference):
    n = reference["nonan_file_critique"]
    assert n["rows_in_noNaN_file"] == 278_512 and n["rows_dropped"] == 752 and n["rows_only_in_noNaN_file"] == 0
    assert n["dropped_rows_by_reason"] == {
        "period_49_or_50_on_autumn_clock_change_day": 32, "whole_day_deleted_because_tsd_equals_0": 720}
    assert n["rows_with_valid_tsd_deleted_on_those_days"] == 241     # valid readings thrown away
    assert n["columns_dropped"] == ["scottish_transfer", "nsl_flow", "eleclink_flow", "viking_flow", "greenlink_flow"]
    spring, autumn = n["examples"]["spring_2024-03-31"], n["examples"]["autumn_2024-10-27"]
    assert spring["period_3_stamp_in_noNaN_file"] == "01:00:00"            # a local time that does not exist
    assert spring["period_3_correct_local_start"] == "02:00:00+0100"
    assert spring["last_stamp_in_noNaN_file"] == "22:30:00" and spring["last_correct_local_start"] == "23:30:00+0100"
    assert (autumn["rows_in_noNaN_file"], autumn["rows_in_yearly_files"]) == (48, 50)
    assert n["kept_rows_with_wrong_local_clock_time"] == 1408
    assert n["kept_rows_stamped_with_nonexistent_local_time"] == 32 == n["kept_rows_stamped_with_ambiguous_local_time"]
    assert sum(n["value_mismatches_on_kept_rows_by_column"].values()) == 0   # its values are fine; its labels are not
    assert n["verdict"].startswith("REJECTED")


def test_is_holiday_recomputed_and_every_disagreement_reported(reference, real_run):
    h = reference["is_holiday"]
    assert h["combined_file_is_holiday_rows"] == 6_288 and h["combined_file_holiday_days"] == 131
    assert h["days_where_flag_varies_within_the_day"] == 0
    england = next(c for c in h["package_candidates"] if c["candidate"] == "England")
    assert england["nominal_only_in_file"] == 0     # the file is a subset of England's nominal list
    assert h["recomputed_holiday_days"] == 131
    missing = {d["settlement_date"] for d in h["disagreements"] if d["finding"] == "missing_in_combined_file"}
    extra = {d["settlement_date"] for d in h["disagreements"]
             if d["finding"] == "flagged_in_combined_file_but_falls_on_weekend"}
    assert missing == {"2010-12-27", "2011-12-26", "2016-12-26", "2021-12-27", "2022-12-26"}
    assert extra == {"2010-12-25", "2011-12-25", "2016-12-25", "2021-12-25", "2022-12-25"}
    assert h["disagreeing_days"] == 10 == len(h["disagreements"])
    gov = h["govuk_cross_check"]       # independent source agrees with the recomputation for 2019+
    assert gov["only_in_govuk"] == [] and gov["only_in_recomputed"] == [] and gov["govuk_days"] == 49
    table = pd.read_csv(real_run.processed / "is_holiday_disagreements.csv")
    assert len(table) == 10 and set(table["settlement_date"]) == missing | extra
    assert set(table["weekday"][table["finding"] == "missing_in_combined_file"]) == {"Monday"}
    assert set(table["weekday"][table["finding"] != "missing_in_combined_file"]) <= {"Saturday", "Sunday"}


def test_recomputed_holiday_column_has_the_expected_shape(real_run):
    df = real_run.df
    days = df.groupby("settlement_date")["is_bank_holiday_ew"].agg(["min", "max"])
    assert (days["min"] == days["max"]).all()           # constant within each day
    assert int(days["max"].sum()) == 131 and int(df["is_bank_holiday_ew"].sum()) == 6_288
    assert not df.loc[df["settlement_date"].map(lambda d: d.weekday() >= 5), "is_bank_holiday_ew"].any()


def test_data_dictionary_is_in_sync_with_the_data(real_run):
    from app.data.build_docs import render_data_dictionary

    committed = (REPO_ROOT / "docs" / "DATA_DICTIONARY.md").read_text()
    assert committed == render_data_dictionary(real_run.manifest), (
        "docs/DATA_DICTIONARY.md is stale: run `cd backend && python -m app.data.build_docs`")
