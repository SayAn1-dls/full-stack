"""Elexon BMRS client and snapshot builder for FUELHH (WIND outturn) and WINDFOR (wind forecast).

    python -m app.wind.ingest        # fetch from the live API and rewrite data/elexon/wind_snapshot.json

Only these two datasets are used (PRD: "elexon alone, no other data beyond this"). Every fetched row must land in the
snapshot or the build fails: duplicates are deduplicated only when identical, gaps and non-hourly forecasts raise.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
UTC = timezone.utc
ACTUAL_STEP = timedelta(minutes=30)
FORECAST_STEP = timedelta(hours=1)


class IngestError(Exception):
    """The fetched data violates an expectation (gap, conflict, unexpected shape)."""


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_json(path: str, params: dict[str, str], retries: int = 5, timeout: int = 90) -> list[dict[str, Any]]:
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, list):
                raise IngestError(f"unexpected payload from {url}: {str(payload)[:200]}")
            return payload
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise IngestError(f"giving up on {url}: {last}")


def fetch_fuelhh_wind(first: date, last: date, chunk_days: int = 7) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = first
    while day <= last:
        end = min(day + timedelta(days=chunk_days - 1), last)
        rows += get_json("/datasets/FUELHH/stream", {
            "settlementDateFrom": day.isoformat(), "settlementDateTo": end.isoformat(), "fuelType": "WIND"})
        day = end + timedelta(days=1)
    return rows


def fetch_windfor(first: datetime, last: datetime, chunk_hours: int = 48) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = first
    while start < last:
        end = min(start + timedelta(hours=chunk_hours), last)
        rows += get_json("/datasets/WINDFOR/stream", {
            "publishDateTimeFrom": start.strftime("%Y-%m-%dT%H:%MZ"),
            "publishDateTimeTo": end.strftime("%Y-%m-%dT%H:%MZ")})
        start = end
    return rows


def _dedupe(rows: list[dict[str, Any]], key: tuple[str, ...], label: str) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        k = tuple(row[name] for name in key)
        if k in seen:
            if seen[k]["generation"] != row["generation"]:
                raise IngestError(f"{label}: conflicting duplicate for {k}: {seen[k]['generation']} vs {row['generation']}")
            continue
        seen[k] = row
    return list(seen.values())


def build_snapshot(fuelhh: list[dict[str, Any]], windfor: list[dict[str, Any]], *, delivery_first: date,
                   delivery_last: date, publish_from: datetime, publish_to: datetime,
                   fetched_at: datetime) -> dict[str, Any]:
    raw_counts = {"fuelhh_rows_fetched": len(fuelhh), "windfor_rows_fetched": len(windfor)}

    # ---- actuals: FUELHH WIND, one value per half hour, contiguous
    for row in fuelhh:
        if row.get("dataset") != "FUELHH" or row.get("fuelType") != "WIND":
            raise IngestError(f"unexpected FUELHH row: {row}")
    fuelhh = sorted(_dedupe(fuelhh, ("startTime",), "FUELHH"), key=lambda r: r["startTime"])
    if not fuelhh:
        raise IngestError("no FUELHH rows")
    starts = [parse_utc(r["startTime"]) for r in fuelhh]
    for earlier, later in zip(starts, starts[1:]):
        if later - earlier != ACTUAL_STEP:
            raise IngestError(f"FUELHH gap between {earlier} and {later}")
    expected_first = datetime.combine(delivery_first, datetime.min.time(), tzinfo=UTC)
    expected_last = datetime.combine(delivery_last + timedelta(days=1), datetime.min.time(), tzinfo=UTC) - ACTUAL_STEP
    if starts[0] != expected_first or starts[-1] != expected_last:
        raise IngestError(f"FUELHH covers {starts[0]}..{starts[-1]}, expected {expected_first}..{expected_last}")

    # ---- forecasts: WINDFOR, hourly, contiguous within each publication
    for row in windfor:
        if row.get("dataset") != "WINDFOR":
            raise IngestError(f"unexpected WINDFOR row: {row}")
    windfor = _dedupe(windfor, ("publishTime", "startTime"), "WINDFOR")
    by_publication: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in windfor:
        by_publication[row["publishTime"]].append(row)
    publications = []
    for publish in sorted(by_publication):
        rows = sorted(by_publication[publish], key=lambda r: r["startTime"])
        targets = [parse_utc(r["startTime"]) for r in rows]
        for earlier, later in zip(targets, targets[1:]):
            if later - earlier != FORECAST_STEP:
                raise IngestError(f"WINDFOR publication {publish} is not hourly-contiguous ({earlier} -> {later})")
        publications.append({"publish": publish, "first": rows[0]["startTime"],
                             "values": [r["generation"] for r in rows]})
    stored = sum(len(p["values"]) for p in publications)
    if stored != len(windfor):
        raise IngestError(f"snapshot would drop WINDFOR rows: {stored} stored vs {len(windfor)} fetched")
    if not (publish_from <= parse_utc(publications[0]["publish"]) and
            parse_utc(publications[-1]["publish"]) <= publish_to):
        raise IngestError("WINDFOR publication outside the requested window")

    per_day = Counter(p["publish"][:10] for p in publications)
    clock_times = Counter(p["publish"][11:16] for p in publications)
    return {
        "meta": {
            "source": "Elexon BMRS Insights API",
            "datasets": {
                "FUELHH": f"{BASE_URL}/datasets/FUELHH/stream?settlementDateFrom=..&settlementDateTo=..&fuelType=WIND",
                "WINDFOR": f"{BASE_URL}/datasets/WINDFOR/stream?publishDateTimeFrom=..&publishDateTimeTo=..",
            },
            "fetched_at": iso_z(fetched_at),
            "delivery_first": delivery_first.isoformat(),
            "delivery_last": delivery_last.isoformat(),
            "publish_from": iso_z(publish_from),
            "publish_to": iso_z(publish_to),
            **raw_counts,
            "fuelh_rows_stored": len(fuelhh),
            "windfor_rows_stored": stored,
            "windfor_publications": len(publications),
            "windfor_publications_per_day_min": min(per_day.values()),
            "windfor_publications_per_day_max": max(per_day.values()),
            "windfor_publish_clock_times_utc": dict(sorted(clock_times.items())),
            "units": "MW (half-hour average for FUELHH; hourly forecast value for WINDFOR)",
        },
        "actuals": {"first": fuelhh[0]["startTime"], "step_minutes": 30,
                    "values": [r["generation"] for r in fuelhh]},
        "forecasts": publications,
    }


def dumps_snapshot(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, separators=(",", ":"), sort_keys=True) + "\n"
