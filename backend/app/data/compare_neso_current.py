"""Diff the audited yearly files against NESO's *current* official downloads (comparison only).

    python -m app.data.compare_neso_current [--years 2019 2020 ...]

NESO re-published 2019-2024 on 2025-04-08 (retrospective corrections, see the dataset description on the
portal). The pipeline deliberately refuses those files (different SHA-256); this script quantifies how they
differ so the audit stays honest about vintage. Nothing is written to data/: downloads go to a temp dir.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request

import numpy as np
import pandas as pd

from app.data.clean_demand import REPO_ROOT, read_year_file
from app.data.demand_schema import POWER_COLUMNS, YEARLY_FILE_TEMPLATE

PACKAGE_URL = "https://api.neso.energy/api/3/action/datapackage_show?id=historic-demand-data"


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def _resource_urls() -> dict[int, str]:
    package = json.loads(_download(PACKAGE_URL))["result"]
    urls = {}
    for resource in package["resources"]:
        name = resource["name"]
        if name.startswith("historic_demand_data_"):
            urls[int(name.rsplit("_", 1)[1])] = resource["path"]
    return urls


def _parse_current(raw: bytes) -> pd.DataFrame:
    """Tolerant reader for comparison only: also accepts DD-Mon-YY, which the pipeline rejects on purpose."""
    frame = pd.read_csv(io.BytesIO(raw), dtype=str)
    frame.columns = [c.strip().lower() for c in frame.columns]
    text = frame["settlement_date"].str.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y"):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if parsed.notna().all():
            break
    else:
        raise SystemExit("could not parse NESO dates")
    out = pd.DataFrame({"settlement_date": parsed.astype("datetime64[ns]"),
                        "settlement_period": frame["settlement_period"].astype(int).astype("int16")})
    for column in POWER_COLUMNS:
        out[column] = pd.to_numeric(frame[column]).astype("float64") if column in frame else np.nan
    return out


def compare(year: int, url: str) -> dict:
    audited, _ = read_year_file(REPO_ROOT / "data" / "raw" / YEARLY_FILE_TEMPLATE.format(year=year))
    current = _parse_current(_download(url))
    keys = ["settlement_date", "settlement_period"]
    merged = audited.merge(current, on=keys, how="outer", suffixes=("_audited", "_current"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    changed = {}
    for column in POWER_COLUMNS:
        a = both[f"{column}_audited"].to_numpy(dtype="float64", na_value=np.nan)
        c = both[f"{column}_current"].to_numpy(dtype="float64", na_value=np.nan)
        n = int((~((a == c) | (np.isnan(a) & np.isnan(c)))).sum())
        if n:
            changed[column] = n
    new = merged[merged["_merge"] == "right_only"]
    return {
        "year": year, "rows_audited": len(audited), "rows_current": len(current),
        "periods_only_in_current": len(new),
        "new_periods_span": None if new.empty else [str(new["settlement_date"].min().date()),
                                                    str(new["settlement_date"].max().date())],
        "changed_cells_by_column": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="+", default=list(range(2019, 2025)))
    args = parser.parse_args(argv)
    urls = _resource_urls()
    print(json.dumps([compare(y, urls[y]) for y in args.years], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
