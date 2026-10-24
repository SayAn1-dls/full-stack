"""Clean the NESO "Historic Demand Data" yearly files into one validated dataset.

Run from `backend/`:

    python -m app.data.clean_demand

Reads only `data/raw/` (never modified) and writes only to `data/interim/` and `data/processed/`.
See docs/DATA_CLEANING_REPORT.md for the rules and docs/DATA_DICTIONARY.md for the output columns.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import holidays
import numpy as np
import pandas as pd
import pyarrow

from app.data import holiday_calendar
from app.data.demand_schema import (
    ALL_FLAG_NAMES,
    CANONICAL_COLUMNS,
    CONSTANT_COLUMN_FLAG,
    CONSTANT_COLUMN_MIN_ROWS,
    FIRST_YEAR,
    INVALID_FLAG_NAMES,
    INVALID_ZERO_RULES,
    KEY_COLUMNS,
    LAST_YEAR,
    POWER_COLUMNS,
    REASON_INVALID_ZERO,
    REASON_NOT_PUBLISHED,
    SUSPECT_FLAGS,
    YEARLY_FILE_TEMPLATE,
)

PIPELINE_VERSION = "1.0.0"
LOCAL_TZ = "Europe/London"
PERIOD = pd.Timedelta(minutes=30)
MAX_SETTLEMENT_PERIOD = 50

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_HASHES_PATH = Path(__file__).resolve().parent / "expected_hashes.json"

OUTPUT_CLEAN_PARQUET = "demand_clean.parquet"
OUTPUT_CLEAN_CSV = "demand_clean.csv"
OUTPUT_COMPLETENESS = "demand_daily_completeness.csv"
OUTPUT_NULL_REASONS = "demand_null_reasons.csv"
OUTPUT_MANIFEST = "run_manifest.json"
INTERIM_UNIFIED = "demand_unified_uncleaned.parquet"


class PipelineError(Exception):
    """Base class: every failure the pipeline raises on purpose."""


class HashMismatchError(PipelineError):
    pass


class SchemaError(PipelineError):
    pass


class DateParseError(PipelineError):
    pass


class DuplicateKeyError(PipelineError):
    pass


class TimeContinuityError(PipelineError):
    pass


class CompletenessError(PipelineError):
    pass


@dataclass
class PipelineConfig:
    raw_dir: Path
    interim_dir: Path
    processed_dir: Path
    years: tuple[int, ...] = tuple(range(FIRST_YEAR, LAST_YEAR + 1))
    # filename -> expected sha256. None disables the check (small test fixtures only).
    expected_hashes: dict[str, str] | None = None
    # Record mismatches in the manifest instead of failing. Section 4 of the audit no longer applies then.
    allow_hash_mismatch: bool = False
    # "auto": run if the combined files are present; "on": require them; "off": skip.
    reference_checks: str = "auto"
    constant_min_rows: int = CONSTANT_COLUMN_MIN_ROWS
    extras: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------- reading


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_expected_hashes() -> dict[str, str]:
    data = json.loads(EXPECTED_HASHES_PATH.read_text())
    return {name: entry["sha256"] for name, entry in data.items()}


def normalise_column_names(columns: list[str]) -> list[str]:
    """Lowercase + strip (also removes a UTF-8 BOM). Mapping is by name, never by position."""
    names = [str(c).replace("﻿", "").strip().lower() for c in columns]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise SchemaError(f"duplicate column names after normalisation: {duplicates}")
    return names


_DMY = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def date_formats_seen(values: pd.Series) -> list[str]:
    s = values.astype(str).str.strip()
    seen = []
    if s.str.match(_DMY).any():
        seen.append("DD-MON-YYYY")
    if s.str.match(_ISO).any():
        seen.append("YYYY-MM-DD")
    return seen


def parse_settlement_dates(values: pd.Series) -> pd.Series:
    """Parse `DD-MON-YYYY` and `YYYY-MM-DD` with fixed formats; anything else raises DateParseError."""
    s = values.astype(str).str.strip()
    dmy = s.str.extract(_DMY)
    iso = s.str.extract(_ISO)
    is_dmy = dmy[0].notna()
    is_iso = iso[0].notna()
    bad = ~(is_dmy | is_iso)
    if bad.any():
        raise DateParseError(
            f"{int(bad.sum())} unparseable settlement_date value(s), e.g. {s[bad].head(5).tolist()}; "
            "accepted formats are DD-MON-YYYY and YYYY-MM-DD"
        )
    year = pd.Series(np.zeros(len(s), dtype="int64"), index=s.index)
    month = year.copy()
    day = year.copy()
    year[is_dmy] = dmy.loc[is_dmy, 2].astype(int)
    day[is_dmy] = dmy.loc[is_dmy, 0].astype(int)
    unknown_month = is_dmy & ~dmy[1].str.upper().isin(_MONTHS)
    if unknown_month.any():
        raise DateParseError(f"unknown month abbreviation, e.g. {s[unknown_month].head(5).tolist()}")
    month[is_dmy] = dmy.loc[is_dmy, 1].str.upper().map(_MONTHS).astype(int)
    year[is_iso] = iso.loc[is_iso, 0].astype(int)
    month[is_iso] = iso.loc[is_iso, 1].astype(int)
    day[is_iso] = iso.loc[is_iso, 2].astype(int)
    try:
        parsed = pd.to_datetime(pd.DataFrame({"year": year, "month": month, "day": day}), errors="raise")
    except (ValueError, TypeError) as exc:
        raise DateParseError(f"impossible calendar date in settlement_date: {exc}") from exc
    return parsed.dt.as_unit("ns")


def _to_int64(series: pd.Series, column: str, source: str) -> pd.Series:
    try:
        numeric = pd.to_numeric(series, errors="raise")
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"{source}: column {column!r} has a non-numeric value ({exc})") from exc
    values = numeric.to_numpy(dtype="float64")
    if not np.isfinite(values).all() or not (values == np.round(values)).all():
        raise SchemaError(f"{source}: column {column!r} has non-finite or non-integer values")
    return numeric.astype("int64").astype("Int64")


def _line_endings(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    lf_only = raw.count(b"\n") - crlf
    if crlf and not lf_only:
        return "CRLF"
    if lf_only and not crlf:
        return "LF"
    if not crlf and not lf_only:
        return "none"
    return f"mixed (CRLF={crlf}, LF={lf_only})"


def read_year_file(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read one yearly CSV into the canonical (union) schema. Absent columns become all-NA."""
    source = path.name
    raw = path.read_bytes()
    frame = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    original_headers = [str(c).replace("﻿", "").strip() for c in frame.columns]
    frame.columns = normalise_column_names(list(frame.columns))

    unknown = [c for c in frame.columns if c not in CANONICAL_COLUMNS]
    if unknown:
        raise SchemaError(f"{source}: unknown column(s) {unknown}; update demand_schema.py deliberately")
    missing_keys = [c for c in KEY_COLUMNS if c not in frame.columns]
    if missing_keys:
        raise SchemaError(f"{source}: missing key column(s) {missing_keys}")
    frame = frame.apply(lambda col: col.str.strip())

    published = [c for c in POWER_COLUMNS if c in frame.columns]
    for column in list(KEY_COLUMNS) + published:
        if (frame[column] == "").any():
            raise SchemaError(f"{source}: blank cell(s) in column {column!r}")

    formats = date_formats_seen(frame["settlement_date"])
    periods = _to_int64(frame["settlement_period"], "settlement_period", source).astype("int64")
    if ((periods < 1) | (periods > MAX_SETTLEMENT_PERIOD)).any():
        raise SchemaError(f"{source}: settlement_period outside 1..{MAX_SETTLEMENT_PERIOD}")

    out = pd.DataFrame({
        "settlement_date": parse_settlement_dates(frame["settlement_date"]),
        "settlement_period": periods.astype("int16"),
    })
    for column in POWER_COLUMNS:
        if column in published:
            out[column] = _to_int64(frame[column], column, source)
        else:
            out[column] = pd.array([pd.NA] * len(out), dtype="Int64")
    out["source_file"] = source
    out["source_row"] = np.arange(1, len(out) + 1, dtype="int32")

    upper = all(h == h.upper() for h in original_headers)
    lower = all(h == h.lower() for h in original_headers)
    info = {
        "rows": int(len(out)),
        "size_bytes": len(raw),
        "header_style": "UPPERCASE" if upper else "lowercase" if lower else "mixed",
        "date_formats": formats,
        "line_endings": _line_endings(raw),
        "published_columns": published,
        "unpublished_columns": [c for c in POWER_COLUMNS if c not in published],
        "raw_column_order": [h.lower() for h in original_headers],
    }
    return out, info


def verify_input_hashes(config: PipelineConfig, files: list[Path]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    mismatches = []
    for path in files:
        actual = sha256_file(path)
        expected = None if config.expected_hashes is None else config.expected_hashes.get(path.name)
        ok = None if config.expected_hashes is None else actual == expected
        results[path.name] = {"sha256": actual, "expected_sha256": expected, "hash_ok": ok}
        if ok is False:
            mismatches.append(path.name)
    if mismatches and not config.allow_hash_mismatch:
        raise HashMismatchError(
            f"SHA-256 differs from the audited files for {mismatches}. These are not the files Section 4 "
            "of the audit describes: re-run the audit, or pass --allow-hash-mismatch to proceed and "
            "record the mismatch in run_manifest.json."
        )
    return results


# ----------------------------------------------------------------------------- timestamps


def _midnights(dates: pd.Series) -> pd.DataFrame:
    unique = pd.Series(np.sort(dates.unique())).astype("datetime64[ns]")
    start_local = unique.dt.tz_localize(LOCAL_TZ, ambiguous="raise", nonexistent="raise")
    end_local = (unique + pd.Timedelta(days=1)).dt.tz_localize(LOCAL_TZ, ambiguous="raise", nonexistent="raise")
    midnight_utc = start_local.dt.tz_convert("UTC")
    next_utc = end_local.dt.tz_convert("UTC")
    return pd.DataFrame({
        "settlement_date": unique,
        "midnight_utc": midnight_utc,
        "expected_periods": ((next_utc - midnight_utc) / PERIOD).round().astype("int64"),
    })


def expected_periods_by_date(dates: pd.Series) -> pd.Series:
    """Settlement periods in each Europe/London calendar day: 46, 48 or 50."""
    table = _midnights(dates)
    return pd.Series(table["expected_periods"].to_numpy(), index=table["settlement_date"])


def add_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Period start = local midnight (Europe/London) as UTC + (period - 1) x 30 minutes."""
    duplicated = df.duplicated(list(KEY_COLUMNS), keep=False)
    if duplicated.any():
        raise DuplicateKeyError(_describe_duplicates(df[duplicated], "(settlement_date, settlement_period)"))
    table = _midnights(df["settlement_date"])
    merged = df.merge(table, on="settlement_date", how="left", validate="many_to_one")
    too_long = merged["settlement_period"] > merged["expected_periods"]
    if too_long.any():
        sample = merged.loc[too_long, ["settlement_date", "settlement_period", "expected_periods"]].head(5)
        raise CompletenessError(
            f"{int(too_long.sum())} row(s) have a period beyond that day's length, e.g.\n{sample.to_string()}"
        )
    offset = pd.to_timedelta((merged["settlement_period"].astype("int64") - 1) * 30, unit="min")
    start_utc = (merged["midnight_utc"] + offset).dt.as_unit("ns")
    merged["period_start_utc"] = start_utc
    merged["period_end_utc"] = start_utc + PERIOD
    merged["period_start_local"] = start_utc.dt.tz_convert(LOCAL_TZ)
    merged = merged.drop(columns=["midnight_utc"])
    return merged.sort_values("period_start_utc", kind="stable").reset_index(drop=True)


def _describe_duplicates(rows: pd.DataFrame, key: str) -> str:
    cols = [c for c in ("settlement_date", "settlement_period", "period_start_utc", "source_file", "source_row")
            if c in rows.columns]
    return f"{len(rows)} row(s) share a duplicate key {key}; first rows:\n{rows[cols].head(20).to_string()}"


def verify_time_axis(df: pd.DataFrame) -> dict[str, Any]:
    """Hard checks: unique, strictly increasing, exactly 30-minute steps."""
    start = df["period_start_utc"]
    duplicated = start.duplicated(keep=False)
    if duplicated.any():
        raise DuplicateKeyError(_describe_duplicates(df[duplicated], "period_start_utc"))
    if not start.is_monotonic_increasing:
        raise TimeContinuityError("period_start_utc is not strictly increasing")
    steps = start.diff().dropna()
    bad = steps != PERIOD
    if bad.any():
        places = df.loc[bad[bad].index, ["period_start_utc", "settlement_date", "settlement_period"]].head(10)
        raise TimeContinuityError(
            f"{int(bad.sum())} step(s) are not exactly 30 minutes (gaps or overlaps), first ones:\n"
            f"{places.to_string()}"
        )
    return {
        "unique": True,
        "strictly_increasing": True,
        "step_minutes_min": float(steps.min() / pd.Timedelta(minutes=1)) if len(steps) else None,
        "step_minutes_max": float(steps.max() / pd.Timedelta(minutes=1)) if len(steps) else None,
    }


# ----------------------------------------------------------------------------- cleaning


def _true(mask: pd.Series) -> pd.Series:
    return mask.fillna(False).astype(bool)


def apply_cleaning(df: pd.DataFrame, constant_min_rows: int = CONSTANT_COLUMN_MIN_ROWS) -> tuple[pd.DataFrame, dict]:
    """Null invalid readings, flag suspect ones. Never drops rows, never imputes.

    Suspect flags are evaluated on the *cleaned* values: a nulled TSD cannot also be "TSD below ND".
    """
    out = df.copy()
    stats: dict[str, Any] = {"nulled_cells": {}}

    # Raw-value counts, kept for the audit trail (Section 4.2 numbers are raw-data counts).
    stats["raw_tsd_below_nd"] = int(_true(df["tsd"] < df["nd"]).sum())

    for column, flag in INVALID_ZERO_RULES:
        mask = _true(out[column].eq(0))
        out[f"flag_{flag}"] = mask
        out.loc[mask, column] = pd.NA
        stats["nulled_cells"][column] = {REASON_INVALID_ZERO: int(mask.sum())}

    out["flag_tsd_below_nd"] = _true(out["tsd"] < out["nd"])
    out["flag_wind_gen_above_capacity"] = _true(out["embedded_wind_generation"] > out["embedded_wind_capacity"])
    out["flag_negative_stor"] = _true(out["non_bm_stor"] < 0)

    constant_columns: dict[str, dict[str, Any]] = {}
    constant_mask = pd.Series(False, index=out.index)
    constant_tokens = pd.Series("", index=out.index, dtype="object")
    for column in POWER_COLUMNS:
        published = out[column].notna()
        if published.sum() >= constant_min_rows and out.loc[published, column].nunique() == 1:
            constant_columns[column] = {
                "value": int(out.loc[published, column].iloc[0]),
                "published_rows": int(published.sum()),
            }
            constant_mask |= published
            constant_tokens = constant_tokens.where(~published, constant_tokens + f"{CONSTANT_COLUMN_FLAG}:{column};")
    out[f"flag_{CONSTANT_COLUMN_FLAG}"] = constant_mask
    stats["constant_columns"] = constant_columns

    out["quality_flags"] = _quality_flag_strings(out, constant_tokens)
    stats["tsd_below_nd_after_invalid_nulling"] = int(out["flag_tsd_below_nd"].sum())
    return out, stats


def _quality_flag_strings(df: pd.DataFrame, constant_tokens: pd.Series) -> pd.Series:
    parts = pd.Series("", index=df.index, dtype="object")
    for flag in INVALID_FLAG_NAMES + SUSPECT_FLAGS:
        mask = df[f"flag_{flag}"]
        parts = parts.where(~mask, parts + f"{flag};")
    parts = parts + constant_tokens
    parts = parts.str.rstrip(";")
    return parts.where(parts != "", "ok")


def add_holiday_column(df: pd.DataFrame) -> pd.DataFrame:
    years = sorted(df["settlement_date"].dt.year.unique())
    observed = {pd.Timestamp(d) for d in holiday_calendar.observed_bank_holidays_england_wales(years)}
    out = df.copy()
    out["is_bank_holiday_ew"] = out["settlement_date"].isin(observed)
    return out


# ----------------------------------------------------------------------------- reports


def daily_completeness(df: pd.DataFrame) -> pd.DataFrame:
    """One row per Europe/London day from first to last date present. Later dates are out of coverage."""
    all_days = pd.date_range(df["settlement_date"].min(), df["settlement_date"].max(), freq="D").as_unit("ns")
    expected = expected_periods_by_date(pd.Series(all_days)).reindex(all_days)
    grouped = df.groupby("settlement_date")
    invalid_any = df[[f"flag_{f}" for f in INVALID_FLAG_NAMES]].any(axis=1)
    suspect_any = df[[f"flag_{f}" for f in SUSPECT_FLAGS + (CONSTANT_COLUMN_FLAG,)]].any(axis=1)
    table = pd.DataFrame({
        "settlement_date": all_days,
        "expected_periods": expected.to_numpy(),
        "present_periods": grouped.size().reindex(all_days, fill_value=0).to_numpy(),
        "min_period": grouped["settlement_period"].min().reindex(all_days).to_numpy(),
        "max_period": grouped["settlement_period"].max().reindex(all_days).to_numpy(),
        "invalid_periods": invalid_any.groupby(df["settlement_date"]).sum().reindex(all_days, fill_value=0).to_numpy(),
        "suspect_periods": suspect_any.groupby(df["settlement_date"]).sum().reindex(all_days, fill_value=0).to_numpy(),
        "flagged_periods": (df["quality_flags"] != "ok").groupby(df["settlement_date"]).sum()
        .reindex(all_days, fill_value=0).to_numpy(),
    })
    table["missing_periods"] = (table["expected_periods"] - table["present_periods"]).clip(lower=0)
    table["unexpected_periods"] = (table["present_periods"] - table["expected_periods"]).clip(lower=0)
    contiguous = (table["min_period"] == 1) & (table["max_period"] == table["expected_periods"])
    table["complete"] = (table["present_periods"] == table["expected_periods"]) & contiguous
    table["settlement_date"] = table["settlement_date"].dt.strftime("%Y-%m-%d")
    for column in ("min_period", "max_period"):
        table[column] = table[column].astype("Int64")
    return table


def null_reason_table(df: pd.DataFrame, file_info: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for source_file, info in file_info.items():
        part = df[df["source_file"] == source_file]
        for column in info["unpublished_columns"]:
            rows.append({
                "source_file": source_file, "column": column, "reason": REASON_NOT_PUBLISHED,
                "rows": len(part),
                "first_period_start_utc": part["period_start_utc"].min(),
                "last_period_start_utc": part["period_start_utc"].max(),
            })
    for column, flag in INVALID_ZERO_RULES:
        flagged = df[df[f"flag_{flag}"]]
        for source_file, part in flagged.groupby("source_file", sort=True):
            rows.append({
                "source_file": source_file, "column": column, "reason": REASON_INVALID_ZERO,
                "rows": len(part),
                "first_period_start_utc": part["period_start_utc"].min(),
                "last_period_start_utc": part["period_start_utc"].max(),
            })
    table = pd.DataFrame(rows, columns=["source_file", "column", "reason", "rows",
                                        "first_period_start_utc", "last_period_start_utc"])
    for column in ("first_period_start_utc", "last_period_start_utc"):
        table[column] = table[column].map(_utc_iso)
    return table.sort_values(["source_file", "column", "reason"]).reset_index(drop=True)


def column_profile(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    profile = {}
    for column in POWER_COLUMNS:
        published = df[df[column].notna()]
        nonzero = published[published[column] != 0]
        profile[column] = {
            "published_rows": int(len(published)),
            "null_rows": int(df[column].isna().sum()),
            "min": None if published.empty else int(published[column].min()),
            "max": None if published.empty else int(published[column].max()),
            "first_published_utc": _utc_iso(published["period_start_utc"].min()) if len(published) else None,
            "first_nonzero_utc": _utc_iso(nonzero["period_start_utc"].min()) if len(nonzero) else None,
            "zero_rows": int((published[column] == 0).sum()),
        }
    return profile


# ----------------------------------------------------------------------------- output


def _utc_iso(ts: Any) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _output_columns() -> list[str]:
    return (
        ["period_start_utc", "period_end_utc", "period_start_local", "settlement_date", "settlement_period"]
        + list(POWER_COLUMNS)
        + ["is_bank_holiday_ew"]
        + [f"flag_{f}" for f in ALL_FLAG_NAMES]
        + ["quality_flags", "source_file", "source_row"]
    )


def _to_parquet_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[_output_columns()].copy()
    out["settlement_date"] = out["settlement_date"].dt.date
    return out


def _to_csv_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[_output_columns()].copy()
    out["period_start_utc"] = out["period_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["period_end_utc"] = out["period_end_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["period_start_local"] = out["period_start_local"].map(lambda t: t.isoformat())
    out["settlement_date"] = out["settlement_date"].dt.strftime("%Y-%m-%d")
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _assert_outputs_outside_raw(config: PipelineConfig) -> None:
    raw = config.raw_dir.resolve()
    for target in (config.interim_dir, config.processed_dir):
        resolved = target.resolve()
        if resolved == raw or raw in resolved.parents or resolved in raw.parents:
            raise PipelineError(f"output directory {target} overlaps the read-only raw directory {config.raw_dir}")


# ----------------------------------------------------------------------------- orchestration


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    started = time.time()
    started_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _assert_outputs_outside_raw(config)
    config.interim_dir.mkdir(parents=True, exist_ok=True)
    config.processed_dir.mkdir(parents=True, exist_ok=True)

    files = [config.raw_dir / YEARLY_FILE_TEMPLATE.format(year=y) for y in config.years]
    missing = [p.name for p in files if not p.exists()]
    if missing:
        raise PipelineError(
            f"missing raw file(s) in {config.raw_dir}: {missing}. Run `python -m app.data.fetch_raw_data`."
        )
    hash_results = verify_input_hashes(config, files)

    frames, file_info = [], {}
    for path in files:
        frame, info = read_year_file(path)
        frames.append(frame)
        file_info[path.name] = {**hash_results[path.name], **info}
    rows_in = int(sum(len(f) for f in frames))
    unified = pd.concat(frames, ignore_index=True)

    unified = add_timestamps(unified)
    time_axis = verify_time_axis(unified)
    unified_parquet = _to_parquet_frame_for_interim(unified)
    unified_parquet.to_parquet(config.interim_dir / INTERIM_UNIFIED, engine="pyarrow", compression="zstd", index=False)

    cleaned, stats = apply_cleaning(unified, config.constant_min_rows)
    cleaned = add_holiday_column(cleaned)
    if len(cleaned) != rows_in:
        raise PipelineError(f"row count changed during cleaning: {rows_in} in, {len(cleaned)} out")

    completeness = daily_completeness(cleaned)
    day_lengths = completeness["expected_periods"].value_counts().sort_index()
    incomplete = completeness[~completeness["complete"]]
    completeness.to_csv(config.processed_dir / OUTPUT_COMPLETENESS, index=False, lineterminator="\n")
    if len(incomplete):
        raise CompletenessError(
            f"{len(incomplete)} day(s) have missing/unexpected periods (see {OUTPUT_COMPLETENESS}):\n"
            f"{incomplete.head(10).to_string()}"
        )

    reasons = null_reason_table(cleaned, file_info)
    reasons.to_csv(config.processed_dir / OUTPUT_NULL_REASONS, index=False, lineterminator="\n")
    _to_parquet_frame(cleaned).to_parquet(
        config.processed_dir / OUTPUT_CLEAN_PARQUET, engine="pyarrow", compression="zstd", index=False)
    _to_csv_frame(cleaned).to_csv(config.processed_dir / OUTPUT_CLEAN_CSV, index=False, lineterminator="\n")

    reference_summary = _run_reference_checks(config, unified, cleaned)

    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "run": {
            "started_utc": started_utc,
            "duration_seconds": round(time.time() - started, 2),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "pyarrow": pyarrow.__version__,
            "holidays": holidays.__version__,
        },
        "inputs": file_info,
        "hash_check": {
            "enabled": config.expected_hashes is not None,
            "all_match": None if config.expected_hashes is None
            else all(v["hash_ok"] for v in hash_results.values()),
            "mismatches_allowed": config.allow_hash_mismatch,
        },
        "rows_in": rows_in,
        "rows_out": int(len(cleaned)),
        "rows_dropped": rows_in - int(len(cleaned)),
        "coverage": {
            "first_period_start_utc": _utc_iso(cleaned["period_start_utc"].min()),
            "last_period_start_utc": _utc_iso(cleaned["period_start_utc"].max()),
            "first_settlement_date": cleaned["settlement_date"].min().strftime("%Y-%m-%d"),
            "last_settlement_date": cleaned["settlement_date"].max().strftime("%Y-%m-%d"),
            "note": "Dates after last_settlement_date are out of coverage (not missing).",
        },
        "time_axis": time_axis,
        "days": {
            "total": int(len(completeness)),
            "by_length_periods": {str(int(k)): int(v) for k, v in day_lengths.items()},
            "complete": int(completeness["complete"].sum()),
        },
        "rows_flagged": {f"flag_{f}": int(cleaned[f"flag_{f}"].sum()) for f in ALL_FLAG_NAMES}
        | {"any_flag": int((cleaned["quality_flags"] != "ok").sum())},
        "nulled_cells": stats["nulled_cells"],
        "tsd_below_nd": {
            "raw_rows": stats["raw_tsd_below_nd"],
            "after_invalid_nulling": stats["tsd_below_nd_after_invalid_nulling"],
            "note": "raw_rows includes every tsd == 0 row (nulled as invalid); only the remainder is flagged",
        },
        "constant_columns": stats["constant_columns"],
        "column_profile": column_profile(cleaned),
        "is_bank_holiday_ew_rows": int(cleaned["is_bank_holiday_ew"].sum()),
        "reference_checks": reference_summary,
    }
    outputs = {}
    for name in (OUTPUT_CLEAN_PARQUET, OUTPUT_CLEAN_CSV, OUTPUT_COMPLETENESS, OUTPUT_NULL_REASONS):
        path = config.processed_dir / name
        outputs[name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest["outputs"] = outputs
    (config.processed_dir / OUTPUT_MANIFEST).write_text(
        json.dumps(_jsonable(manifest), indent=2, sort_keys=True) + "\n")
    return manifest


def _to_parquet_frame_for_interim(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["period_start_utc", "period_end_utc", "period_start_local", "settlement_date",
              "settlement_period", *POWER_COLUMNS, "source_file", "source_row"]].copy()
    out["settlement_date"] = out["settlement_date"].dt.date
    return out


def _run_reference_checks(config: PipelineConfig, unified: pd.DataFrame, cleaned: pd.DataFrame) -> dict[str, Any]:
    if config.reference_checks == "off":
        return {"status": "skipped", "reason": "disabled"}
    from app.data import reference_checks  # local import: optional stage

    return reference_checks.run(config.raw_dir, config.processed_dir, unified, cleaned,
                                require=config.reference_checks == "on")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean NESO historic GB demand data (2009-2024).")
    parser.add_argument("--raw-dir", type=Path, default=REPO_ROOT / "data" / "raw")
    parser.add_argument("--interim-dir", type=Path, default=REPO_ROOT / "data" / "interim")
    parser.add_argument("--processed-dir", type=Path, default=REPO_ROOT / "data" / "processed")
    parser.add_argument("--allow-hash-mismatch", action="store_true",
                        help="record SHA-256 mismatches in the manifest instead of failing")
    parser.add_argument("--reference-checks", choices=["auto", "on", "off"], default="auto",
                        help="cross-validate against the combined files and recompute is_holiday")
    args = parser.parse_args(argv)
    config = PipelineConfig(
        raw_dir=args.raw_dir, interim_dir=args.interim_dir, processed_dir=args.processed_dir,
        expected_hashes=load_expected_hashes(), allow_hash_mismatch=args.allow_hash_mismatch,
        reference_checks=args.reference_checks,
    )
    try:
        manifest = run_pipeline(config)
    except PipelineError as exc:
        print(f"PIPELINE FAILED ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    print(f"OK: {manifest['rows_in']} rows in, {manifest['rows_out']} rows out, "
          f"{manifest['rows_flagged']['any_flag']} rows carry a quality flag -> {config.processed_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
