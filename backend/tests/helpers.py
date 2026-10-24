"""Builders for small deterministic raw-style fixtures (no real data involved)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.data.clean_demand import expected_periods_by_date
from app.data.demand_schema import POWER_COLUMNS

# Raw column order per schema era, exactly as described in the brief (Section 3.4).
_BASE_17 = [
    "settlement_date", "settlement_period", "nd", "tsd", "england_wales_demand",
    "embedded_wind_generation", "embedded_wind_capacity", "embedded_solar_generation",
    "embedded_solar_capacity", "non_bm_stor", "pump_storage_pumping", "ifa_flow", "ifa2_flow",
    "britned_flow", "moyle_flow", "east_west_flow", "nemo_flow",
]
ERAS: dict[str, dict] = {
    "2009-2018": {"columns": _BASE_17, "upper": True, "date_format": "dmy"},
    "2019-2021": {"columns": _BASE_17 + ["nsl_flow", "eleclink_flow"], "upper": True, "date_format": "dmy"},
    "2022": {"columns": _BASE_17 + ["nsl_flow", "eleclink_flow"], "upper": False, "date_format": "iso"},
    # 2023: scottish_transfer sits *before* ifa_flow
    "2023": {
        "columns": _BASE_17[:11] + ["scottish_transfer"] + _BASE_17[11:] + ["nsl_flow", "eleclink_flow", "viking_flow"],
        "upper": False, "date_format": "iso",
    },
    "2024": {
        "columns": _BASE_17[:11] + ["scottish_transfer"] + _BASE_17[11:]
        + ["nsl_flow", "eleclink_flow", "viking_flow", "greenlink_flow"],
        "upper": False, "date_format": "iso",
    },
}
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def base_value(column: str) -> int:
    """A distinct, recognisable base value per column so a mis-mapped column is caught."""
    return 1000 * (POWER_COLUMNS.index(column) + 1)


def default_value(column: str, period: int) -> int:
    """Clean, flag-free values: tsd > nd, wind generation < capacity, storage >= 0, no constants."""
    if column == "nd":
        return 30000 + period
    if column == "tsd":
        return 31000 + period
    if column == "england_wales_demand":
        return 27000 + period
    if column == "embedded_wind_generation":
        return 100 + period
    if column == "embedded_wind_capacity":
        return 6000 + period  # varies per row so the fixture has no accidental constant column
    return base_value(column) + period


def format_date(day: date, style: str) -> str:
    if style == "iso":
        return day.isoformat()
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def periods_in(day: date) -> int:
    return int(expected_periods_by_date(pd.Series(pd.to_datetime([day]))).iloc[0])


def write_year_csv(path: Path, era: str, days: list[date], *, reverse_columns: bool = False,
                   overrides: dict[tuple[date, int, str], int | str] | None = None,
                   drop_periods: set[tuple[date, int]] | None = None,
                   extra_rows: list[tuple[date, int]] | None = None,
                   crlf: bool | None = None) -> Path:
    """Write a raw-style yearly CSV. `overrides[(day, period, column)]` replaces a cell."""
    spec = ERAS[era]
    columns = list(spec["columns"])
    if reverse_columns:
        columns = columns[::-1]
    overrides = overrides or {}
    drop_periods = drop_periods or set()
    keys: list[tuple[date, int]] = []
    for day in days:
        keys += [(day, p) for p in range(1, periods_in(day) + 1) if (day, p) not in drop_periods]
    keys += extra_rows or []

    header = [c.upper() if spec["upper"] else c for c in columns]
    lines = [",".join(header)]
    for day, period in keys:
        cells = []
        for column in columns:
            if (day, period, column) in overrides:
                cells.append(str(overrides[(day, period, column)]))
            elif column == "settlement_date":
                cells.append(format_date(day, spec["date_format"]))
            elif column == "settlement_period":
                cells.append(str(period))
            else:
                cells.append(str(default_value(column, period)))
        lines.append(",".join(cells))
    eol = "\r\n" if (crlf if crlf is not None else spec["upper"]) else "\n"
    path.write_bytes(eol.join(lines).encode())  # no trailing newline, like the real files
    return path


def date_range(start: str, end: str) -> list[date]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]
