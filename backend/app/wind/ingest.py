"""CLI: fetch the January 2026 scope from Elexon and write data/elexon/wind_snapshot.json."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.wind import elexon, scope

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "data" / "elexon" / "wind_snapshot.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Elexon FUELHH (WIND) and WINDFOR for the Jan 2026 scope.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        print("fetching FUELHH WIND ...", flush=True)
        fuelhh = elexon.fetch_fuelhh_wind(scope.DELIVERY_FIRST, scope.DELIVERY_LAST)
        print(f"  {len(fuelhh)} rows\nfetching WINDFOR ...", flush=True)
        windfor = elexon.fetch_windfor(scope.FORECAST_PUBLISH_FROM, scope.FORECAST_PUBLISH_TO)
        print(f"  {len(windfor)} rows", flush=True)
        snapshot = elexon.build_snapshot(
            fuelhh, windfor, delivery_first=scope.DELIVERY_FIRST, delivery_last=scope.DELIVERY_LAST,
            publish_from=scope.FORECAST_PUBLISH_FROM, publish_to=scope.FORECAST_PUBLISH_TO,
            fetched_at=datetime.now(timezone.utc).replace(microsecond=0))
    except elexon.IngestError as exc:
        print(f"INGEST FAILED: {exc}", file=sys.stderr)
        return 1
    text = elexon.dumps_snapshot(snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    meta = snapshot["meta"]
    print(f"wrote {args.out} ({len(text):,} bytes, sha256 {hashlib.sha256(text.encode()).hexdigest()[:16]}...)")
    print(f"actuals {meta['fuelh_rows_stored']} half-hours; forecasts {meta['windfor_publications']} publications, "
          f"{meta['windfor_rows_stored']} hourly values; publish times (UTC): {meta['windfor_publish_clock_times_utc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
