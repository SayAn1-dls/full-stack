"""Synthetic Elexon-shaped datasets for the wind tests (no network, no real data)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone

from app.wind.dataset import Dataset, Publication

UTC = timezone.utc
HOUR = timedelta(hours=1)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def make_dataset(first_day: date, last_day: date, forecast: Callable[[datetime, datetime], float],
                 actual: Callable[[datetime], float], publish_times=("02:30", "07:30", "09:30", "15:30"),
                 pre_days: int = 3, back_hours: int = 25, fwd_hours: int = 66) -> Dataset:
    """Half-hourly actuals for [first_day, last_day] (UTC days); hourly publications like WINDFOR."""
    start = datetime.combine(first_day, time(0), tzinfo=UTC)
    end = datetime.combine(last_day + timedelta(days=1), time(0), tzinfo=UTC)
    actuals = {}
    t = start
    while t < end:
        actuals[t] = float(actual(t))
        t += timedelta(minutes=30)
    publications = []
    day = first_day - timedelta(days=pre_days)
    while day <= last_day:
        for clock in publish_times:
            hour, minute = map(int, clock.split(":"))
            publish = datetime.combine(day, time(hour, minute), tzinfo=UTC)
            first_target = publish.replace(minute=0) - HOUR * back_hours
            values = tuple(float(forecast(publish, first_target + HOUR * i)) for i in range(back_hours + fwd_hours + 1))
            publications.append(Publication(publish, first_target, values))
        day += timedelta(days=1)
    publications.sort(key=lambda p: p.publish)
    return Dataset({"windfor_rows_stored": 0, "windfor_publish_clock_times_utc": {}, "source": "synthetic",
                    "fetched_at": "x", "units": "MW"}, actuals, tuple(publications), "0" * 64,
                   tuple(p.publish for p in publications))
