"""Validation rules of the Elexon snapshot builder (no network)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.wind import elexon

UTC = timezone.utc
FIRST, LAST = date(2026, 1, 1), date(2026, 1, 2)
PUBLISH_FROM, PUBLISH_TO = datetime(2025, 12, 30, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)
FETCHED = datetime(2026, 10, 24, tzinfo=UTC)


def fuelhh_rows(first=FIRST, last=LAST, skip=()):
    rows, t = [], datetime.combine(first, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    while t < end:
        if t not in skip:
            rows.append({"dataset": "FUELHH", "startTime": elexon.iso_z(t), "fuelType": "WIND", "generation": 1000 + t.hour})
        t += timedelta(minutes=30)
    return rows


def windfor_rows(publishes=("2025-12-31T07:30:00Z", "2025-12-31T09:30:00Z"), hours=10, skip_hour=None):
    rows = []
    for publish in publishes:
        first = elexon.parse_utc(publish).replace(minute=0)
        for i in range(hours):
            if i == skip_hour:
                continue
            rows.append({"dataset": "WINDFOR", "publishTime": publish,
                         "startTime": elexon.iso_z(first + timedelta(hours=i)), "generation": 500 + i})
    return rows


def build(fuelhh=None, windfor=None):
    return elexon.build_snapshot(fuelhh if fuelhh is not None else fuelhh_rows(),
                                 windfor if windfor is not None else windfor_rows(),
                                 delivery_first=FIRST, delivery_last=LAST, publish_from=PUBLISH_FROM,
                                 publish_to=PUBLISH_TO, fetched_at=FETCHED)


def test_valid_input_builds_a_snapshot_that_keeps_every_row():
    snap = build()
    assert snap["meta"]["fuelh_rows_stored"] == 96 and snap["meta"]["windfor_rows_stored"] == 20
    assert snap["meta"]["windfor_rows_fetched"] == 20 and snap["meta"]["windfor_publications"] == 2
    assert len(snap["actuals"]["values"]) == 96 and snap["actuals"]["first"] == "2026-01-01T00:00:00Z"
    assert [len(p["values"]) for p in snap["forecasts"]] == [10, 10]
    assert snap["forecasts"][0]["first"] == "2025-12-31T07:00:00Z"


def test_identical_duplicates_are_collapsed_but_conflicting_ones_fail():
    rows = fuelhh_rows()
    assert build(fuelhh=rows + rows[:5])["meta"]["fuelh_rows_stored"] == 96
    conflicting = [dict(rows[0], generation=rows[0]["generation"] + 1)]
    with pytest.raises(elexon.IngestError, match="conflicting duplicate"):
        build(fuelhh=rows + conflicting)
    forecasts = windfor_rows()
    with pytest.raises(elexon.IngestError, match="conflicting duplicate"):
        build(windfor=forecasts + [dict(forecasts[0], generation=1)])


def test_a_missing_half_hour_of_outturn_fails_loudly():
    skip = {datetime(2026, 1, 1, 12, 30, tzinfo=UTC)}
    with pytest.raises(elexon.IngestError, match="gap"):
        build(fuelhh=fuelhh_rows(skip=skip))


def test_outturn_must_cover_exactly_the_requested_days():
    with pytest.raises(elexon.IngestError, match="expected"):
        build(fuelhh=fuelhh_rows(last=date(2026, 1, 1)))


def test_a_forecast_publication_with_a_missing_hour_fails():
    with pytest.raises(elexon.IngestError, match="hourly-contiguous"):
        build(windfor=windfor_rows(skip_hour=4))


def test_unexpected_datasets_are_rejected():
    bad = fuelhh_rows()
    bad[3] = dict(bad[3], fuelType="SOLAR")
    with pytest.raises(elexon.IngestError, match="unexpected FUELHH"):
        build(fuelhh=bad)
    with pytest.raises(elexon.IngestError, match="unexpected WINDFOR"):
        build(windfor=[dict(windfor_rows()[0], dataset="OTHER")])


def test_publications_outside_the_requested_window_fail():
    with pytest.raises(elexon.IngestError, match="outside the requested window"):
        build(windfor=windfor_rows(publishes=("2025-12-01T07:30:00Z",)))


def test_empty_responses_fail():
    with pytest.raises(elexon.IngestError):
        build(fuelhh=[])


def test_publication_clock_times_are_recorded_including_irregular_ones():
    snap = build(windfor=windfor_rows(publishes=("2025-12-31T07:30:00Z", "2025-12-31T12:25:00Z")))
    assert snap["meta"]["windfor_publish_clock_times_utc"] == {"07:30": 1, "12:25": 1}


def test_snapshot_serialisation_is_deterministic_and_round_trips():
    snap = build()
    text = elexon.dumps_snapshot(snap)
    assert json.loads(text) == snap and text == elexon.dumps_snapshot(json.loads(text))
    assert text.startswith('{"actuals":{"first":') and text.endswith("}\n")      # sorted keys, compact separators
