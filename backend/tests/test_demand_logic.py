"""Fast, deterministic logic tests on small fixtures (no real NESO files)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from helpers import (
    ERAS, base_value, date_range, default_value, periods_in, write_year_csv,
)

from app.data import holiday_calendar
from app.data.clean_demand import (
    CompletenessError, DateParseError, DuplicateKeyError, HashMismatchError, PipelineConfig, PipelineError,
    SchemaError, TimeContinuityError, add_timestamps, apply_cleaning, daily_completeness,
    normalise_column_names, parse_settlement_dates, read_year_file, run_pipeline, verify_time_axis,
)
from app.data.demand_schema import ALL_FLAG_NAMES, POWER_COLUMNS

# ----------------------------------------------------------------------------- dates


def test_both_date_formats_parse_to_the_same_day():
    out = parse_settlement_dates(pd.Series(["01-JAN-2009", "2022-01-01", "31-Dec-2012", "29-feb-2016", " 05-MAR-2010 "]))
    assert out.dt.strftime("%Y-%m-%d").tolist() == ["2009-01-01", "2022-01-01", "2012-12-31", "2016-02-29", "2010-03-05"]


@pytest.mark.parametrize("garbage", [
    "garbage", "", "2009/01/01", "1-JAN-2009", "01-JAN-09", "01-Jan-23", "Jan 1 2009", "01/01/2009",
    "2009-1-1", "20090101", "01-XYZ-2009",
])
def test_garbage_dates_raise(garbage):
    with pytest.raises(DateParseError):
        parse_settlement_dates(pd.Series(["01-JAN-2009", garbage]))


@pytest.mark.parametrize("impossible", ["31-FEB-2009", "2009-13-01", "29-FEB-2011", "2009-02-30", "00-JAN-2009"])
def test_impossible_calendar_dates_raise(impossible):
    with pytest.raises(DateParseError):
        parse_settlement_dates(pd.Series([impossible]))


# ----------------------------------------------------------------------------- schema eras


def test_header_normalisation_lowercases_strips_and_removes_bom():
    assert normalise_column_names(["﻿SETTLEMENT_DATE", " ND ", "Tsd"]) == ["settlement_date", "nd", "tsd"]


def test_duplicate_headers_after_normalisation_fail():
    with pytest.raises(SchemaError):
        normalise_column_names(["ND", "nd"])


@pytest.mark.parametrize("era", list(ERAS))
@pytest.mark.parametrize("reverse", [False, True])
def test_every_era_maps_to_one_schema_regardless_of_column_order(tmp_path, era, reverse):
    path = write_year_csv(tmp_path / "f.csv", era, [date(2022, 1, 5)], reverse_columns=reverse)
    frame, info = read_year_file(path)

    assert list(frame.columns)[:2 + len(POWER_COLUMNS)] == ["settlement_date", "settlement_period", *POWER_COLUMNS]
    assert len(frame) == 48
    published = [c for c in ERAS[era]["columns"] if c in POWER_COLUMNS]
    assert info["published_columns"] == [c for c in POWER_COLUMNS if c in published]
    for column in published:  # values land under the right name, whatever the position
        assert frame[column].tolist() == [default_value(column, p) for p in range(1, 49)], column


def test_scottish_transfer_before_ifa_flow_is_not_swapped(tmp_path):
    path = write_year_csv(tmp_path / "f.csv", "2023", [date(2023, 3, 1)])
    frame, _ = read_year_file(path)
    assert frame.loc[0, "scottish_transfer"] == base_value("scottish_transfer") + 1
    assert frame.loc[0, "ifa_flow"] == base_value("ifa_flow") + 1


def test_missing_column_eras_produce_na_never_zero(tmp_path):
    frame, info = read_year_file(write_year_csv(tmp_path / "f.csv", "2009-2018", [date(2010, 6, 1)]), )
    assert info["unpublished_columns"] == ["scottish_transfer", "nsl_flow", "eleclink_flow", "viking_flow", "greenlink_flow"]
    for column in info["unpublished_columns"]:
        assert frame[column].isna().all(), column
        assert not (frame[column] == 0).any(), column


def test_date_format_line_ending_and_header_style_are_recorded(tmp_path):
    _, info_old = read_year_file(write_year_csv(tmp_path / "a.csv", "2009-2018", [date(2010, 6, 1)]))
    _, info_new = read_year_file(write_year_csv(tmp_path / "b.csv", "2022", [date(2022, 6, 1)]))
    assert (info_old["header_style"], info_old["date_formats"], info_old["line_endings"]) == ("UPPERCASE", ["DD-MON-YYYY"], "CRLF")
    assert (info_new["header_style"], info_new["date_formats"], info_new["line_endings"]) == ("lowercase", ["YYYY-MM-DD"], "LF")


def test_unknown_column_fails_loudly(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("settlement_date,settlement_period,nd,surprise\n2022-01-01,1,5,6\n")
    with pytest.raises(SchemaError, match="surprise"):
        read_year_file(path)


@pytest.mark.parametrize("bad_row, message", [
    ("2022-01-01,1,,6", "blank"),
    ("2022-01-01,1,abc,6", "non-numeric"),
    ("2022-01-01,1,1.5,6", "non-integer"),
    ("2022-01-01,0,5,6", "settlement_period"),
    ("2022-01-01,51,5,6", "settlement_period"),
])
def test_bad_cells_fail_loudly(tmp_path, bad_row, message):
    path = tmp_path / "f.csv"
    path.write_text(f"settlement_date,settlement_period,nd,tsd\n{bad_row}\n")
    with pytest.raises(SchemaError, match=message):
        read_year_file(path)


# ----------------------------------------------------------------------------- timestamps


def _stamps(day: str, periods: list[int]) -> pd.DataFrame:
    frame = pd.DataFrame({"settlement_date": pd.to_datetime([day] * len(periods)).astype("datetime64[ns]"),
                          "settlement_period": pd.array(periods, dtype="int16")})
    return add_timestamps(frame).set_index("settlement_period")


def _utc(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts, tz="UTC")


def test_winter_day_utc_equals_local():
    out = _stamps("2023-01-15", list(range(1, 49)))
    assert out.loc[1, "period_start_utc"] == _utc("2023-01-15T00:00Z")
    assert out.loc[48, "period_start_utc"] == _utc("2023-01-15T23:30Z")
    assert out.loc[48, "period_end_utc"] == _utc("2023-01-16T00:00Z")
    assert (out["period_start_local"].dt.tz_localize(None) == out["period_start_utc"].dt.tz_localize(None)).all()
    assert out.loc[1, "period_start_local"].isoformat() == "2023-01-15T00:00:00+00:00"


def test_summer_day_utc_is_local_minus_one_hour():
    out = _stamps("2023-07-15", list(range(1, 49)))
    assert out.loc[1, "period_start_utc"] == _utc("2023-07-14T23:00Z")
    assert out.loc[48, "period_start_utc"] == _utc("2023-07-15T22:30Z")
    assert out.loc[1, "period_start_local"].isoformat() == "2023-07-15T00:00:00+01:00"
    assert out.loc[48, "period_start_local"].isoformat() == "2023-07-15T23:30:00+01:00"


def test_spring_day_has_46_periods_and_period_3_is_0100_utc_0200_bst():
    out = _stamps("2024-03-31", list(range(1, 47)))
    assert out.loc[2, "period_start_utc"] == _utc("2024-03-31T00:30Z")
    assert out.loc[3, "period_start_utc"] == _utc("2024-03-31T01:00Z")
    assert out.loc[3, "period_start_local"].isoformat() == "2024-03-31T02:00:00+01:00"  # 01:00 local never exists
    assert out.loc[46, "period_start_utc"] == _utc("2024-03-31T22:30Z")
    assert out.loc[46, "period_start_local"].isoformat() == "2024-03-31T23:30:00+01:00"
    assert periods_in(date(2024, 3, 31)) == 46


def test_spring_day_rejects_a_47th_period():
    with pytest.raises(CompletenessError, match="beyond"):
        _stamps("2024-03-31", list(range(1, 48)))


def test_autumn_day_has_50_periods_and_the_repeated_hour_has_distinct_utc_times():
    out = _stamps("2024-10-27", list(range(1, 51)))
    assert out.loc[1, "period_start_utc"] == _utc("2024-10-26T23:00Z")  # 00:00 BST
    assert out.loc[3, "period_start_utc"] == _utc("2024-10-27T00:00Z")  # 01:00 BST
    assert out.loc[4, "period_start_utc"] == _utc("2024-10-27T00:30Z")  # 01:30 BST
    assert out.loc[5, "period_start_utc"] == _utc("2024-10-27T01:00Z")  # 01:00 GMT (second pass)
    assert out.loc[6, "period_start_utc"] == _utc("2024-10-27T01:30Z")  # 01:30 GMT
    assert out.loc[50, "period_start_utc"] == _utc("2024-10-27T23:30Z")
    assert out.loc[3, "period_start_local"].isoformat() == "2024-10-27T01:00:00+01:00"
    assert out.loc[5, "period_start_local"].isoformat() == "2024-10-27T01:00:00+00:00"
    assert out["period_start_utc"].is_unique and periods_in(date(2024, 10, 27)) == 50


def test_autumn_day_rejects_a_51st_period():
    with pytest.raises(CompletenessError):
        _stamps("2024-10-27", list(range(1, 52)))


def test_time_axis_is_30_minute_strictly_increasing_across_both_clock_changes():
    for start, end in (("2024-03-29", "2024-04-02"), ("2024-10-25", "2024-10-29")):
        days = date_range(start, end)
        frame = pd.DataFrame(
            [(pd.Timestamp(d), p) for d in days for p in range(1, periods_in(d) + 1)],
            columns=["settlement_date", "settlement_period"])
        frame["settlement_date"] = frame["settlement_date"].astype("datetime64[ns]")
        frame["settlement_period"] = frame["settlement_period"].astype("int16")
        info = verify_time_axis(add_timestamps(frame))
        assert info == {"unique": True, "strictly_increasing": True, "step_minutes_min": 30.0, "step_minutes_max": 30.0}


def test_time_axis_gap_fails():
    frame = pd.DataFrame({"settlement_date": pd.to_datetime(["2023-01-15"] * 3).astype("datetime64[ns]"),
                          "settlement_period": pd.array([1, 2, 4], dtype="int16")})
    with pytest.raises(TimeContinuityError):
        verify_time_axis(add_timestamps(frame))


# ----------------------------------------------------------------------------- uniqueness


def test_duplicate_keys_fail_hard():
    frame = pd.DataFrame({"settlement_date": pd.to_datetime(["2023-01-15"] * 3).astype("datetime64[ns]"),
                          "settlement_period": pd.array([1, 2, 2], dtype="int16")})
    with pytest.raises(DuplicateKeyError, match="duplicate key"):
        add_timestamps(frame)


def test_duplicate_period_start_utc_fails_hard():
    ts = pd.Timestamp("2023-01-15T00:00Z")
    frame = pd.DataFrame({"period_start_utc": [ts, ts], "settlement_date": pd.to_datetime(["2023-01-15"] * 2),
                          "settlement_period": [1, 1]})
    with pytest.raises(DuplicateKeyError):
        verify_time_axis(frame)


def test_duplicate_row_in_a_raw_file_fails_the_whole_run(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2022.csv", "2022", [date(2022, 12, 31)], extra_rows=[(date(2022, 12, 31), 5)])
    config = PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2022,), reference_checks="off")
    with pytest.raises(DuplicateKeyError):
        run_pipeline(config)


# ----------------------------------------------------------------------------- cleaning


def _frame(rows: list[dict]) -> pd.DataFrame:
    """A unified-schema frame; each dict overrides the clean defaults for one row."""
    data = {c: [] for c in POWER_COLUMNS}
    for i, overrides in enumerate(rows):
        for column in POWER_COLUMNS:
            value = overrides.get(column, default_value(column, i + 1))
            data[column].append(value)
    return pd.DataFrame({c: pd.array(v, dtype="Int64") for c, v in data.items()})


def test_tsd_zero_becomes_na_flagged_and_the_rest_of_the_row_is_kept():
    before = _frame([{}, {"tsd": 0}, {}])
    after, stats = apply_cleaning(before, constant_min_rows=10**9)
    assert after["tsd"].isna().tolist() == [False, True, False]
    assert after["flag_tsd_zero"].tolist() == [False, True, False]
    assert after.loc[1, "quality_flags"] == "tsd_zero"
    other = [c for c in POWER_COLUMNS if c != "tsd"]
    pd.testing.assert_frame_equal(after[other], before[other])  # every other cell untouched
    assert len(after) == len(before)
    assert stats["nulled_cells"]["tsd"] == {"invalid_zero_reading": 1}


def test_england_wales_and_nd_zero_are_nulled_too():
    after, _ = apply_cleaning(_frame([{"england_wales_demand": 0}, {"nd": 0}]), constant_min_rows=10**9)
    assert after["england_wales_demand"].isna().tolist() == [True, False]
    assert after["nd"].isna().tolist() == [False, True]
    assert after["quality_flags"].tolist() == ["england_wales_demand_zero", "nd_zero"]


def test_zero_in_a_non_rule_column_is_a_real_value_and_is_kept():
    before = _frame([{"ifa_flow": 0, "non_bm_stor": 0, "embedded_solar_generation": 0, "nemo_flow": 0}])
    after, _ = apply_cleaning(before, constant_min_rows=10**9)
    for column in ("ifa_flow", "non_bm_stor", "embedded_solar_generation", "nemo_flow"):
        assert after.loc[0, column] == 0, column
    assert after.loc[0, "quality_flags"] == "ok"


def test_negative_interconnector_flows_are_kept_with_their_sign():
    before = _frame([{"ifa_flow": -1500, "scottish_transfer": -2000, "nsl_flow": -1}])
    after, _ = apply_cleaning(before, constant_min_rows=10**9)
    assert after.loc[0, "ifa_flow"] == -1500 and after.loc[0, "scottish_transfer"] == -2000
    assert after.loc[0, "quality_flags"] == "ok"


def test_suspect_flags_trigger_exactly_at_their_thresholds():
    rows = [
        {"nd": 30000, "tsd": 30000},          # tsd == nd -> not suspect
        {"nd": 30000, "tsd": 29999},          # tsd == nd - 1 -> suspect
        {"embedded_wind_generation": 6000, "embedded_wind_capacity": 6000},   # == capacity -> fine
        {"embedded_wind_generation": 6001, "embedded_wind_capacity": 6000},   # > capacity -> suspect
        {"non_bm_stor": 0},                   # zero -> fine
        {"non_bm_stor": -1},                  # negative -> suspect
    ]
    after, _ = apply_cleaning(_frame(rows), constant_min_rows=10**9)
    assert after["flag_tsd_below_nd"].tolist() == [False, True, False, False, False, False]
    assert after["flag_wind_gen_above_capacity"].tolist() == [False, False, False, True, False, False]
    assert after["flag_negative_stor"].tolist() == [False, False, False, False, False, True]
    assert after["quality_flags"].tolist() == [
        "ok", "tsd_below_nd", "ok", "wind_gen_above_capacity", "ok", "negative_stor"]


def test_a_nulled_tsd_is_not_also_reported_as_tsd_below_nd_but_the_raw_count_is_kept():
    after, stats = apply_cleaning(_frame([{"tsd": 0}, {"nd": 30000, "tsd": 29000}]), constant_min_rows=10**9)
    assert after["flag_tsd_below_nd"].tolist() == [False, True]
    assert stats["raw_tsd_below_nd"] == 2 and stats["tsd_below_nd_after_invalid_nulling"] == 1


def test_multiple_flags_are_joined_in_a_stable_order():
    after, _ = apply_cleaning(_frame([{"tsd": 0, "england_wales_demand": 0, "non_bm_stor": -3,
                                       "embedded_wind_generation": 7000}]), constant_min_rows=10**9)
    assert after.loc[0, "quality_flags"] == "tsd_zero;england_wales_demand_zero;wind_gen_above_capacity;negative_stor"


def test_constant_column_is_flagged_only_when_published_often_enough_and_single_valued():
    rows = [{"greenlink_flow": 0, "viking_flow": 5 + i % 2} for i in range(6)]
    after, stats = apply_cleaning(_frame(rows), constant_min_rows=5)
    assert set(stats["constant_columns"]) == {"greenlink_flow"}
    assert after["flag_constant_column"].all()
    assert (after["quality_flags"] == "constant_column:greenlink_flow").all()

    too_few, stats_few = apply_cleaning(_frame(rows), constant_min_rows=7)
    assert stats_few["constant_columns"] == {} and not too_few["flag_constant_column"].any()


def test_unpublished_values_do_not_count_as_a_constant_column():
    frame = _frame([{}, {}, {}])
    frame["nsl_flow"] = pd.array([pd.NA, pd.NA, pd.NA], dtype="Int64")
    _, stats = apply_cleaning(frame, constant_min_rows=1)
    assert "nsl_flow" not in stats["constant_columns"]


def test_cleaning_never_changes_the_row_count_or_imputes():
    before = _frame([{"tsd": 0}] * 5 + [{}] * 5)
    after, _ = apply_cleaning(before, constant_min_rows=10**9)
    assert len(after) == len(before)
    assert int(after["tsd"].isna().sum()) == 5 and int(after["tsd"].notna().sum()) == 5
    assert {f"flag_{f}" for f in ALL_FLAG_NAMES} <= set(after.columns)


# ----------------------------------------------------------------------------- completeness


def test_daily_completeness_counts_flagged_days_and_expected_lengths():
    days = date_range("2024-03-30", "2024-04-01")
    frame = pd.DataFrame([(pd.Timestamp(d), p) for d in days for p in range(1, periods_in(d) + 1)],
                         columns=["settlement_date", "settlement_period"])
    frame["settlement_date"] = frame["settlement_date"].astype("datetime64[ns]")
    frame["settlement_period"] = frame["settlement_period"].astype("int16")
    values = _frame([{}] * len(frame))
    cleaned, _ = apply_cleaning(pd.concat([frame, values], axis=1), constant_min_rows=10**9)
    table = daily_completeness(cleaned)
    assert table["expected_periods"].tolist() == [48, 46, 48]
    assert table["present_periods"].tolist() == [48, 46, 48]
    assert table["complete"].all() and table["flagged_periods"].sum() == 0


def test_truncated_final_day_is_reported_as_incomplete_not_ignored(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2022.csv", "2022", [date(2022, 12, 30), date(2022, 12, 31)],
                   drop_periods={(date(2022, 12, 31), 48)})
    config = PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2022,), reference_checks="off")
    with pytest.raises(CompletenessError, match="missing/unexpected"):
        run_pipeline(config)
    table = pd.read_csv(tmp_path / "p" / "demand_daily_completeness.csv")  # written before the failure
    assert table.loc[table["settlement_date"] == "2022-12-31", "missing_periods"].item() == 1


def test_a_missing_period_mid_day_fails_as_a_time_gap(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2022.csv", "2022", [date(2022, 12, 31)],
                   drop_periods={(date(2022, 12, 31), 10)})
    config = PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2022,), reference_checks="off")
    with pytest.raises(TimeContinuityError):
        run_pipeline(config)


# ----------------------------------------------------------------------------- hashes and safety


def _small_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2022.csv", "2022", [date(2022, 12, 30), date(2022, 12, 31)])
    return raw


def test_hash_mismatch_fails_by_default_and_can_be_recorded(tmp_path):
    raw = _small_raw(tmp_path)
    wrong = {"historic_demand_year_2022.csv": "0" * 64}
    with pytest.raises(HashMismatchError, match="2022"):
        run_pipeline(PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2022,),
                                    expected_hashes=wrong, reference_checks="off"))
    manifest = run_pipeline(PipelineConfig(raw, tmp_path / "i", tmp_path / "p2", years=(2022,),
                                           expected_hashes=wrong, allow_hash_mismatch=True, reference_checks="off"))
    assert manifest["hash_check"] == {"enabled": True, "all_match": False, "mismatches_allowed": True}
    assert manifest["inputs"]["historic_demand_year_2022.csv"]["hash_ok"] is False


def test_outputs_inside_the_raw_directory_are_refused(tmp_path):
    raw = _small_raw(tmp_path)
    with pytest.raises(PipelineError, match="overlaps"):
        run_pipeline(PipelineConfig(raw, tmp_path / "i", raw / "out", years=(2022,), reference_checks="off"))
    assert sorted(p.name for p in raw.iterdir()) == ["historic_demand_year_2022.csv"]


def test_missing_raw_file_names_the_file_and_the_fix(tmp_path):
    empty_raw = tmp_path / "raw"
    empty_raw.mkdir()
    with pytest.raises(PipelineError, match="historic_demand_year_2022.csv.*fetch_raw_data"):
        run_pipeline(PipelineConfig(empty_raw, tmp_path / "i", tmp_path / "p", years=(2022,), reference_checks="off"))


# ----------------------------------------------------------------------------- end to end on a fixture


def test_end_to_end_fixture_run_across_a_year_boundary_and_two_eras(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2022.csv", "2022", date_range("2022-12-24", "2022-12-31"),
                   overrides={(date(2022, 12, 25), 3, "tsd"): 0})
    write_year_csv(raw / "historic_demand_year_2023.csv", "2023", [date(2023, 1, 1)])
    config = PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2022, 2023), reference_checks="off")
    manifest = run_pipeline(config)

    assert manifest["rows_in"] == manifest["rows_out"] == 9 * 48 and manifest["rows_dropped"] == 0
    assert manifest["rows_flagged"]["flag_tsd_zero"] == 1 and manifest["rows_flagged"]["any_flag"] == 1
    df = pd.read_parquet(tmp_path / "p" / "demand_clean.parquet")
    assert df["period_start_utc"].is_monotonic_increasing and df["period_start_utc"].is_unique
    assert str(df["period_start_utc"].dt.tz) == "UTC" and "Europe/London" in str(df["period_start_local"].dt.tz)
    assert df["tsd"].isna().sum() == 1 and df["nsl_flow"].notna().sum() == 9 * 48
    # unpublished-in-2022 columns: NA, with the reason recorded
    reasons = pd.read_csv(tmp_path / "p" / "demand_null_reasons.csv")
    row = reasons[(reasons.source_file == "historic_demand_year_2022.csv") & (reasons["column"] == "viking_flow")]
    assert row["reason"].item() == "column_not_published" and row["rows"].item() == 8 * 48
    assert df.loc[df.source_file == "historic_demand_year_2022.csv", "viking_flow"].isna().all()
    assert df.loc[df.source_file == "historic_demand_year_2023.csv", "viking_flow"].notna().all()
    # holiday column: Christmas Day 2022 is a Sunday (not observed), Boxing Day Monday is
    flags = df.groupby("settlement_date")["is_bank_holiday_ew"].all()
    assert not flags[date(2022, 12, 25)] and flags[date(2022, 12, 26)] and not flags[date(2022, 12, 24)]
    # CSV round trip keeps blanks blank (never 0) and writes ISO timestamps
    csv = pd.read_csv(tmp_path / "p" / "demand_clean.csv")
    assert csv["tsd"].isna().sum() == 1 and csv["period_start_utc"].iloc[0] == "2022-12-24T00:00:00Z"
    assert csv["period_start_local"].iloc[0] == "2022-12-24T00:00:00+00:00"
    manifest_on_disk = json.loads((tmp_path / "p" / "run_manifest.json").read_text())
    assert manifest_on_disk["rows_out"] == 9 * 48 and manifest_on_disk["pipeline_version"]


@pytest.mark.parametrize("start, end, lengths, rows", [
    ("2024-03-30", "2024-04-01", {"46": 1, "48": 2}, 48 + 46 + 48),   # spring forward
    ("2024-10-26", "2024-10-28", {"48": 2, "50": 1}, 48 + 50 + 48),   # autumn back
])
def test_end_to_end_across_a_clock_change(tmp_path, start, end, lengths, rows):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_year_csv(raw / "historic_demand_year_2024.csv", "2024", date_range(start, end))
    manifest = run_pipeline(PipelineConfig(raw, tmp_path / "i", tmp_path / "p", years=(2024,), reference_checks="off"))
    assert manifest["days"]["by_length_periods"] == lengths
    assert manifest["rows_out"] == rows and manifest["days"]["complete"] == 3
    assert manifest["time_axis"]["step_minutes_min"] == manifest["time_axis"]["step_minutes_max"] == 30.0


# ----------------------------------------------------------------------------- holiday calendar


@pytest.mark.parametrize("day, expected", [
    ("2022-12-25", False),  # Sunday: the holiday itself is not observed...
    ("2022-12-26", True),   # ...Boxing Day (Mon) is
    ("2022-12-27", True),   # ...and so is the substitute for Christmas Day
    ("2021-12-27", True), ("2021-12-28", True), ("2021-12-25", False),
    ("2011-01-01", False), ("2011-01-03", True),   # New Year's Day on a Saturday -> Monday
    ("2011-04-29", True),   # royal wedding
    ("2012-06-05", True),   # Diamond Jubilee
    ("2022-06-02", True), ("2022-06-03", True), ("2022-05-30", False),  # Platinum Jubilee moved the spring holiday
    ("2022-09-19", True),   # state funeral
    ("2023-05-08", True),   # coronation
    ("2023-03-17", False),  # St Patrick's Day is a Northern Ireland holiday only
    ("2023-01-02", True),   # New Year's Day (Sun 1 Jan) substitute in England
])
def test_england_wales_observed_bank_holidays(day, expected):
    d = date.fromisoformat(day)
    assert (d in holiday_calendar.observed_bank_holidays_england_wales([d.year])) is expected


def test_observed_holidays_are_always_weekdays():
    observed = holiday_calendar.observed_bank_holidays_england_wales(range(2009, 2025))
    assert observed and all(d.weekday() < 5 for d in observed)
    nominal = holiday_calendar.nominal_holidays_england(range(2009, 2025))
    assert len(nominal) > len(observed)  # weekend nominal dates exist and are dropped
