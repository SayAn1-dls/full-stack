"""Checks against the third-party combined files (never used as a data source).

* cross-validate `historic_demand_2009_2024.csv` against the yearly files (all shared columns)
* demonstrate why `historic_demand_2009_2024_noNaN.csv` must not be used (Section 4.3 of the audit brief)
* recompute `is_holiday` and report every disagreement (Section 4.4)

Results go to `data/processed/reference_checks.json` and `data/processed/is_holiday_disagreements.csv`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.data import holiday_calendar
from app.data.demand_schema import COMBINED_FILE, KEY_COLUMNS, NONAN_FILE, POWER_COLUMNS

GOVUK_SNAPSHOT = Path(__file__).resolve().parent / "reference" / "bank_holidays_gov_uk.json"
GOVUK_URL = "https://www.gov.uk/bank-holidays.json"
OUTPUT_REPORT = "reference_checks.json"
OUTPUT_HOLIDAY_CSV = "is_holiday_disagreements.csv"

HOLIDAY_DEFINITION = (
    "England & Wales bank holidays *observed* on that date (substitute days included, nominal weekend dates "
    "excluded). Python `holidays` package, UnitedKingdom(subdiv='England'), weekdays only; cross-checked "
    "against a frozen gov.uk snapshot for 2019+."
)


def _read_combined(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], format="%Y-%m-%d").astype("datetime64[ns]")
    return frame


def _float(series: pd.Series) -> np.ndarray:
    return series.to_numpy(dtype="float64", na_value=np.nan)


def _equal_with_nan(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a == b) | (np.isnan(a) & np.isnan(b))


# ----------------------------------------------------------------------------- combined file


def cross_validate_combined(unified: pd.DataFrame, combined: pd.DataFrame) -> dict[str, Any]:
    keys = list(KEY_COLUMNS)
    left = unified[keys + list(POWER_COLUMNS)]
    right = combined[keys + [c for c in POWER_COLUMNS if c in combined.columns]]
    merged = left.merge(right, on=keys, how="outer", suffixes=("_yearly", "_combined"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    shared = [c for c in POWER_COLUMNS if c in combined.columns]
    per_column = {}
    for column in shared:
        equal = _equal_with_nan(_float(both[f"{column}_yearly"]), _float(both[f"{column}_combined"]))
        per_column[column] = int((~equal).sum())
    return {
        "yearly_rows": int(len(unified)),
        "combined_rows": int(len(combined)),
        "keys_in_both": int(len(both)),
        "keys_only_in_yearly": int((merged["_merge"] == "left_only").sum()),
        "keys_only_in_combined": int((merged["_merge"] == "right_only").sum()),
        "columns_compared": shared,
        "columns_only_in_yearly": [c for c in POWER_COLUMNS if c not in combined.columns],
        "mismatching_cells_by_column": per_column,
        "mismatching_cells_total": int(sum(per_column.values())),
    }


# ----------------------------------------------------------------------------- noNaN file


def critique_nonan(unified: pd.DataFrame, nonan: pd.DataFrame) -> dict[str, Any]:
    """Reproduce the Section 4.3 defects from the file itself."""
    nn = nonan.copy()
    nn["stamp"] = pd.to_datetime(nn["settlement_date"], format="%Y-%m-%d %H:%M:%S").astype("datetime64[ns]")
    nn["settlement_date"] = nn["stamp"].dt.normalize()
    keys = list(KEY_COLUMNS)

    tsd_zero_dates = set(unified.loc[unified["tsd"] == 0, "settlement_date"].unique())
    merged = unified.merge(nn[keys + ["stamp"]], on=keys, how="left", indicator=True)
    dropped = merged[merged["_merge"] == "left_only"].copy()
    only_in_nonan = int(len(nn.merge(unified[keys], on=keys, how="left", indicator=True).query("_merge == 'right_only'")))

    dropped["reason"] = np.where(
        dropped["settlement_period"] > 48, "period_49_or_50_on_autumn_clock_change_day",
        np.where(dropped["settlement_date"].isin(tsd_zero_dates), "whole_day_deleted_because_tsd_equals_0",
                 "other"))
    reasons = dropped["reason"].value_counts().to_dict()
    on_zero_days = dropped[dropped["reason"] == "whole_day_deleted_because_tsd_equals_0"]
    valid_tsd_lost = int((on_zero_days["tsd"] != 0).sum())

    kept = merged[merged["_merge"] == "both"].copy()
    kept["correct_local_naive"] = kept["period_start_local"].dt.tz_localize(None)
    wrong_clock = kept["stamp"] != kept["correct_local_naive"]
    # A stamp is "nonexistent" if that wall-clock time never happened (spring forward) and "ambiguous" if it
    # happened twice (autumn back). Count each separately; both are labelling errors for a UTC-based dataset.
    stamps = kept["stamp"]
    nonexistent = int(stamps.dt.tz_localize("Europe/London", ambiguous=np.zeros(len(stamps), dtype=bool),
                                            nonexistent="NaT").isna().sum())
    ambiguous_probe = stamps.dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="shift_forward")
    ambiguous = int(ambiguous_probe.isna().sum())

    def day_example(day: str, period: int) -> dict[str, Any]:
        row = kept[(kept["settlement_date"] == pd.Timestamp(day)) & (kept["settlement_period"] == period)]
        day_rows = kept[kept["settlement_date"] == pd.Timestamp(day)]
        unified_day = unified[unified["settlement_date"] == pd.Timestamp(day)]
        return {
            "date": day,
            "rows_in_noNaN_file": int(len(day_rows)),
            "rows_in_yearly_files": int(len(unified_day)),
            "last_stamp_in_noNaN_file": day_rows["stamp"].max().strftime("%H:%M:%S") if len(day_rows) else None,
            "last_correct_local_start": unified_day["period_start_local"].max().strftime("%H:%M:%S%z"),
            f"period_{period}_stamp_in_noNaN_file": None if row.empty else row["stamp"].iloc[0].strftime("%H:%M:%S"),
            f"period_{period}_correct_local_start": None if row.empty
            else row["period_start_local"].iloc[0].strftime("%H:%M:%S%z"),
        }

    shared = [c for c in POWER_COLUMNS if c in nn.columns]
    value_mismatch = {}
    both = unified.merge(nn[keys + shared], on=keys, how="inner", suffixes=("_yearly", "_nonan"))
    for column in shared:
        equal = _equal_with_nan(_float(both[f"{column}_yearly"]), _float(both[f"{column}_nonan"]))
        value_mismatch[column] = int((~equal).sum())

    return {
        "rows_in_noNaN_file": int(len(nn)),
        "rows_in_yearly_files": int(len(unified)),
        "rows_dropped": int(len(dropped)),
        "rows_only_in_noNaN_file": only_in_nonan,
        "dropped_rows_by_reason": {k: int(v) for k, v in sorted(reasons.items())},
        "tsd_zero_days": len(tsd_zero_dates),
        "tsd_zero_rows": int((unified["tsd"] == 0).sum()),
        "rows_on_tsd_zero_days_deleted": int(len(on_zero_days)),
        "rows_with_valid_tsd_deleted_on_those_days": valid_tsd_lost,
        "columns_dropped": [c for c in POWER_COLUMNS if c not in nn.columns],
        "extra_columns": [c for c in nn.columns if c not in POWER_COLUMNS and c not in ("stamp",)
                          and c not in KEY_COLUMNS],
        "settlement_date_column_holds_naive_timestamp": True,
        "kept_rows_with_wrong_local_clock_time": int(wrong_clock.sum()),
        "kept_rows_stamped_with_nonexistent_local_time": nonexistent,
        "kept_rows_stamped_with_ambiguous_local_time": ambiguous,
        "value_mismatches_on_kept_rows_by_column": value_mismatch,
        "examples": {
            "spring_2024-03-31": day_example("2024-03-31", 3),
            "autumn_2024-10-27": day_example("2024-10-27", 5),
        },
        "verdict": "REJECTED as a source: deletes whole days to remove one bad column and mislabels time across "
                   "clock changes.",
    }


# ----------------------------------------------------------------------------- is_holiday


def _govuk_dates() -> tuple[set[pd.Timestamp], str]:
    raw = GOVUK_SNAPSHOT.read_bytes()
    import hashlib

    data = json.loads(raw)
    dates = {pd.Timestamp(e["date"]) for e in data["england-and-wales"]["events"]}
    return dates, hashlib.sha256(raw).hexdigest()


def compare_is_holiday(combined: pd.DataFrame, days: pd.DatetimeIndex) -> tuple[dict[str, Any], pd.DataFrame]:
    per_day = combined.groupby("settlement_date")["is_holiday"].agg(["min", "max", "size"])
    file_days = set(per_day.index[per_day["max"] == 1])
    years = sorted({d.year for d in days})
    day_set = set(days)

    def candidate(name: str, subdiv: str | None) -> dict[str, Any]:
        import holidays as pkg

        cal = pkg.UnitedKingdom(subdiv=subdiv, years=years) if subdiv else pkg.UnitedKingdom(years=years)
        nominal = {pd.Timestamp(d) for d in cal if pd.Timestamp(d) in day_set}
        observed = {d for d in nominal if d.weekday() < 5}
        return {
            "candidate": name,
            "nominal_days": len(nominal), "nominal_only_in_file": len(file_days - nominal),
            "nominal_only_in_package": len(nominal - file_days),
            "observed_days": len(observed), "observed_only_in_file": len(file_days - observed),
            "observed_only_in_package": len(observed - file_days),
        }

    candidates = [candidate("England", "England"), candidate("Wales", "Wales"),
                  candidate("Scotland", "Scotland"), candidate("Northern Ireland", "Northern Ireland"),
                  candidate("UK default (no subdivision)", None)]

    names = holiday_calendar.observed_bank_holidays_england_wales(years)
    recomputed = {pd.Timestamp(d) for d in names if pd.Timestamp(d) in day_set}
    nominal_all = holiday_calendar.nominal_holidays_england(years)
    nominal_weekend = sorted(pd.Timestamp(d) for d in nominal_all if pd.Timestamp(d) in day_set and d.weekday() >= 5)

    govuk, govuk_sha = _govuk_dates()
    last_day = days.max()
    in_gov_range = lambda d: pd.Timestamp("2019-01-01") <= d <= last_day  # noqa: E731
    gov_in_range = {d for d in govuk if in_gov_range(d)}
    rec_in_range = {d for d in recomputed if in_gov_range(d)}
    file_in_range = {d for d in file_days if in_gov_range(d)}

    disagree_dates = sorted(file_days ^ recomputed)
    rows = []
    for d in disagree_dates:
        rows.append({
            "settlement_date": d.strftime("%Y-%m-%d"),
            "weekday": d.day_name(),
            "is_holiday_in_combined_file": int(d in file_days),
            "is_bank_holiday_ew_recomputed": int(d in recomputed),
            "holiday_name": names.get(d.date(), ""),
            "listed_by_govuk": (d in govuk) if d.year >= 2019 else None,
            "govuk_snapshot_covers_date": d.year >= 2019,
            "finding": "missing_in_combined_file" if d in recomputed
            else "flagged_in_combined_file_but_falls_on_weekend",
        })
    table = pd.DataFrame(rows, columns=["settlement_date", "weekday", "is_holiday_in_combined_file",
                                        "is_bank_holiday_ew_recomputed", "holiday_name", "listed_by_govuk",
                                        "govuk_snapshot_covers_date", "finding"])
    summary = {
        "combined_file_is_holiday_rows": int(combined["is_holiday"].sum()),
        "combined_file_holiday_days": len(file_days),
        "days_where_flag_varies_within_the_day": int((per_day["min"] != per_day["max"]).sum()),
        "definition_used": HOLIDAY_DEFINITION,
        "package_candidates": candidates,
        "recomputed_holiday_days": len(recomputed),
        "disagreeing_days": len(disagree_dates),
        "disagreements": table.assign(listed_by_govuk=table["listed_by_govuk"].astype(object))
        .to_dict(orient="records"),
        "nominal_weekend_dates": [
            {"date": d.strftime("%Y-%m-%d"), "weekday": d.day_name(), "flagged_in_combined_file": d in file_days}
            for d in nominal_weekend
        ],
        "govuk_cross_check": {
            "snapshot": "backend/app/data/reference/bank_holidays_gov_uk.json",
            "source_url": GOVUK_URL, "retrieved": "2026-10-24", "sha256": govuk_sha,
            "range": f"2019-01-01..{last_day.strftime('%Y-%m-%d')}",
            "govuk_days": len(gov_in_range), "recomputed_days": len(rec_in_range),
            "only_in_govuk": sorted(d.strftime("%Y-%m-%d") for d in gov_in_range - rec_in_range),
            "only_in_recomputed": sorted(d.strftime("%Y-%m-%d") for d in rec_in_range - gov_in_range),
            "combined_file_vs_govuk_only_in_file": sorted(d.strftime("%Y-%m-%d") for d in file_in_range - gov_in_range),
            "combined_file_vs_govuk_only_in_govuk": sorted(d.strftime("%Y-%m-%d") for d in gov_in_range - file_in_range),
            "note": "gov.uk's JSON no longer carries years before 2019; 2009-2018 rely on the holidays package.",
        },
    }
    return summary, table


# ----------------------------------------------------------------------------- orchestration


def run(raw_dir: Path, processed_dir: Path, unified: pd.DataFrame, cleaned: pd.DataFrame,
        require: bool = False) -> dict[str, Any]:
    from app.data.clean_demand import PipelineError, sha256_file

    combined_path, nonan_path = raw_dir / COMBINED_FILE, raw_dir / NONAN_FILE
    missing = [p.name for p in (combined_path, nonan_path) if not p.exists()]
    if missing:
        if require:
            raise PipelineError(f"reference check inputs missing in {raw_dir}: {missing}")
        return {"status": "skipped", "reason": f"input file(s) not present: {missing}"}

    combined = _read_combined(combined_path)
    nonan = pd.read_csv(nonan_path)
    holiday_summary, holiday_table = compare_is_holiday(combined, pd.DatetimeIndex(sorted(unified["settlement_date"].unique())))
    report = {
        "inputs": {COMBINED_FILE: sha256_file(combined_path), NONAN_FILE: sha256_file(nonan_path)},
        "combined_file_cross_validation": cross_validate_combined(unified, combined),
        "nonan_file_critique": critique_nonan(unified, nonan),
        "is_holiday": holiday_summary,
    }
    report_path = processed_dir / OUTPUT_REPORT
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    holiday_table.to_csv(processed_dir / OUTPUT_HOLIDAY_CSV, index=False, lineterminator="\n")
    return {
        "status": "ran",
        "report_file": OUTPUT_REPORT,
        "report_sha256": sha256_file(report_path),
        "combined_file_mismatching_cells": report["combined_file_cross_validation"]["mismatching_cells_total"],
        "nonan_rows_dropped": report["nonan_file_critique"]["rows_dropped"],
        "is_holiday_disagreeing_days": holiday_summary["disagreeing_days"],
    }
