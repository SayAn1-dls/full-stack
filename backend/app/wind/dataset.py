"""In-memory view of the committed Elexon snapshot (data/elexon/wind_snapshot.json)."""

from __future__ import annotations

import hashlib
import json
import os
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

UTC = timezone.utc
HOUR = timedelta(hours=1)
HALF_HOUR = timedelta(minutes=30)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "elexon" / "wind_snapshot.json"


class SnapshotError(Exception):
    pass


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True)
class Publication:
    """One WINDFOR publication: hourly forecast values for consecutive target hours."""

    publish: datetime
    first: datetime
    values: tuple[float, ...]

    @property
    def last(self) -> datetime:
        return self.first + HOUR * (len(self.values) - 1)

    def value_at(self, target: datetime) -> float | None:
        offset = target - self.first
        if offset < timedelta(0) or offset % HOUR:
            return None
        index = offset // HOUR
        return self.values[index] if index < len(self.values) else None


@dataclass(frozen=True)
class Dataset:
    meta: dict[str, Any]
    actual: dict[datetime, float]  # half-hour start (UTC) -> MW
    publications: tuple[Publication, ...]  # ascending publish time
    sha256: str
    _publish_times: tuple[datetime, ...] = field(default=(), repr=False)

    def latest_forecast(self, target: datetime, cutoff: datetime) -> tuple[Publication, float] | None:
        """The most recent publication at or before `cutoff` that has a value for `target`."""
        index = bisect_right(self._publish_times, cutoff)
        for publication in reversed(self.publications[:index]):
            value = publication.value_at(target)
            if value is not None:
                return publication, value
        return None

    def last_actual_before(self, cutoff: datetime) -> tuple[datetime, float] | None:
        """Latest half-hour whose period had *ended* by `cutoff` (the newest outturn known at decision time)."""
        start = cutoff - HALF_HOUR
        start = start.replace(minute=(start.minute // 30) * 30, second=0, microsecond=0)
        for _ in range(48):
            if start in self.actual:
                return start, self.actual[start]
            start -= HALF_HOUR
        return None


def parse_snapshot(text: str) -> Dataset:
    raw = json.loads(text)
    actuals = raw["actuals"]
    first = parse_utc(actuals["first"])
    step = timedelta(minutes=actuals["step_minutes"])
    actual = {first + step * i: float(v) for i, v in enumerate(actuals["values"])}
    publications = tuple(
        Publication(parse_utc(p["publish"]), parse_utc(p["first"]), tuple(float(v) for v in p["values"]))
        for p in raw["forecasts"]
    )
    if not actual or not publications:
        raise SnapshotError("snapshot has no actuals or no forecasts")
    times = [p.publish for p in publications]
    if times != sorted(times) or len(set(times)) != len(times):
        raise SnapshotError("publications must be unique and ascending")
    return Dataset(raw["meta"], actual, publications, hashlib.sha256(text.encode()).hexdigest(), tuple(times))


@lru_cache(maxsize=1)
def load_dataset(path: str | None = None) -> Dataset:
    location = Path(path or os.environ.get("WIND_SNAPSHOT_PATH") or DEFAULT_SNAPSHOT)
    try:
        return parse_snapshot(location.read_text())
    except FileNotFoundError as exc:
        raise SnapshotError(f"snapshot not found at {location}; run `python -m app.wind.ingest`") from exc
