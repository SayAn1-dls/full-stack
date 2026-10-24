"""API tests against the committed real snapshot (data/elexon/wind_snapshot.json).

Expected numbers are recomputed here from the raw JSON with a small independent implementation, so they do not
simply echo the application code.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.wind.dataset import DEFAULT_SNAPSHOT

client = TestClient(app)
UTC = timezone.utc
RAW = json.loads(Path(DEFAULT_SNAPSHOT).read_text())


def P(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


ACTUAL = {P(RAW["actuals"]["first"]) + timedelta(minutes=30 * i): v for i, v in enumerate(RAW["actuals"]["values"])}
PUBS = [(P(p["publish"]), P(p["first"]), p["values"]) for p in RAW["forecasts"]]
ALL_DAYS = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(32)]


def independent_pairs(hour: int, minute: int):
    """(day, hour, forecast, actual) for the forecast available at D-1 hh:mm (January: UK local == UTC)."""
    out = []
    for day in ALL_DAYS:
        cutoff = day - timedelta(days=1) + timedelta(hours=hour, minutes=minute)
        eligible = [p for p in PUBS if p[0] <= cutoff]
        publish, first, values = max(eligible, key=lambda p: p[0])
        for h in range(24):
            target = day + timedelta(hours=h)
            index = int((target - first).total_seconds() // 3600)
            out.append((day.date().isoformat(), h, values[index], ACTUAL[target], publish))
    return out


# ----------------------------------------------------------------------------- snapshot integrity


def test_snapshot_is_complete_and_regular():
    assert len(ACTUAL) == 1536 == 32 * 48
    times = sorted(ACTUAL)
    assert times[0] == P("2026-01-01T00:00:00Z") and times[-1] == P("2026-02-01T23:30:00Z")
    assert all(b - a == timedelta(minutes=30) for a, b in zip(times, times[1:]))
    assert len(PUBS) == 280 and all(len(v) == 73 for _, _, v in PUBS)
    assert RAW["meta"]["windfor_rows_stored"] == 20440 == RAW["meta"]["windfor_rows_fetched"]
    assert RAW["meta"]["windfor_publish_clock_times_utc"] == {
        "02:30": 35, "04:30": 35, "07:30": 35, "09:30": 35, "11:30": 34, "12:25": 1, "15:30": 35, "18:30": 35, "22:30": 35}
    # every publication starts a few hours to a day before it was published and runs hourly to ~66 h ahead
    lead = [(publish - first).total_seconds() / 3600 for publish, first, _ in PUBS]
    assert 5 <= min(lead) and max(lead) <= 26
    reach = [(first + timedelta(hours=72) - publish).total_seconds() / 3600 for publish, first, _ in PUBS]
    assert 46 <= min(reach) and max(reach) <= 67      # how far ahead a publication looks: 46.5-66.5 h


def test_meta_reports_the_scope_the_pr_asks_for_and_the_snapshot_hash():
    body = client.get("/api/meta").json()
    days = body["delivery_days"]
    assert [d["date"] for d in days][0] == "2026-01-01" and days[-1]["date"] == "2026-02-01" and len(days) == 32
    assert days[0]["decision_date"] == "2025-12-31" and days[0]["decision_in_january_2026"] is False
    assert all(d["decision_in_january_2026"] for d in days[1:])      # 2 Jan .. 1 Feb: decided 1..31 January
    assert body["default_decision_time"] == "09:20"
    assert [p["time"] for p in body["decision_presets"]] == ["09:20", "09:50"]
    assert body["data"]["snapshot_sha256"] == hashlib.sha256(Path(DEFAULT_SNAPSHOT).read_bytes()).hexdigest()
    assert (body["data"]["actual_half_hours"], body["data"]["forecast_publications"]) == (1536, 280)
    assert any("Elexon only" in a for a in body["assumptions"])


def test_health_exposes_the_snapshot_hash_for_deployment_verification():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["snapshot_sha256"] == client.get("/api/meta").json()["data"]["snapshot_sha256"]


# ----------------------------------------------------------------------------- decision endpoint


@pytest.mark.parametrize("decision_time", ["09:20", "09:50", "04:00", "16:00"])
def test_decision_forecast_equals_an_independent_selection_for_every_day(decision_time):
    hour, minute = map(int, decision_time.split(":"))
    expected = {(d, h): (f, a, pub) for d, h, f, a, pub in independent_pairs(hour, minute)}
    for day in ALL_DAYS:
        body = client.get("/api/decision", params={"delivery_date": day.date().isoformat(), "decision_time": decision_time}).json()
        assert len(body["hours"]) == 24
        cutoff = P(body["cutoff_utc"])
        for i, point in enumerate(body["hours"]):
            f, a, pub = expected[(body["delivery_date"], i)]
            assert point["forecast_mw"] == f and point["actual_mw"] == a and point["error_mw"] == f - a
            assert P(point["publish_utc"]) == pub and pub <= cutoff
            assert point["p10_mw"] <= point["p50_mw"] <= point["p90_mw"]


def test_the_09_20_decision_uses_the_07_30_publication_and_09_50_the_09_30_one():
    a = client.get("/api/decision", params={"delivery_date": "2026-01-15", "decision_time": "09:20"}).json()
    b = client.get("/api/decision", params={"delivery_date": "2026-01-15", "decision_time": "09:50"}).json()
    assert a["used_publication"]["publish_utc"] == "2026-01-14T07:30:00Z" and a["used_publication"]["age_at_cutoff_minutes"] == 110
    assert b["used_publication"]["publish_utc"] == "2026-01-14T09:30:00Z" and b["used_publication"]["age_at_cutoff_minutes"] == 20
    statuses = {e["publish_utc"]: e["status"] for e in a["evolution"]}
    assert statuses["2026-01-14T07:30:00Z"] == "used" and statuses["2026-01-14T09:30:00Z"] == "after_cutoff"
    assert statuses["2026-01-13T22:30:00Z"] == "earlier"
    assert len(a["actual_half_hourly"]) == 48


def test_irregular_12_25_publication_is_handled():
    # 2026-01-15 has a 12:25 publication instead of 11:30; a 12:30 cutoff must include it, 12:20 must not
    inc = client.get("/api/decision", params={"delivery_date": "2026-01-16", "decision_time": "12:30"}).json()
    exc = client.get("/api/decision", params={"delivery_date": "2026-01-16", "decision_time": "12:20"}).json()
    assert inc["used_publication"]["publish_utc"] == "2026-01-15T12:25:00Z"
    assert exc["used_publication"]["publish_utc"] == "2026-01-15T09:30:00Z"


def test_decision_summary_matches_its_hours():
    body = client.get("/api/decision", params={"delivery_date": "2026-01-20"}).json()
    hours, summary = body["hours"], body["summary"]
    assert summary["mean_forecast_mw"] == pytest.approx(statistics.mean(h["forecast_mw"] for h in hours))
    assert summary["mean_error_mw"] == pytest.approx(statistics.mean(h["error_mw"] for h in hours))
    assert summary["mae_mw"] == pytest.approx(statistics.mean(abs(h["error_mw"]) for h in hours))
    assert summary["hours_over_forecast"] == sum(h["error_mw"] > 0 for h in hours)
    assert summary["mean_buffer_mw"] == pytest.approx(statistics.mean(h["forecast_mw"] - h["p10_mw"] for h in hours))
    assert body["error_model"]["built_from_days"] == 31 and len(body["error_model"]["buckets"]) == 4


# ----------------------------------------------------------------------------- accuracy endpoint


def test_headline_accuracy_matches_an_independent_calculation():
    pairs = independent_pairs(9, 20)
    errors = [f - a for _, _, f, a, _ in pairs]
    body = client.get("/api/accuracy", params={"decision_time": "09:20"}).json()
    h = body["headline"]
    assert h["n"] == 768 and h["days"] == 32
    assert h["bias_mw"] == pytest.approx(statistics.mean(errors))
    assert h["mae_mw"] == pytest.approx(statistics.mean(abs(e) for e in errors))
    assert h["rmse_mw"] == pytest.approx(statistics.mean(e * e for e in errors) ** 0.5)
    assert h["mean_actual_mw"] == pytest.approx(statistics.mean(a for *_, a, _ in pairs))
    assert h["over_forecast_share_pct"] == pytest.approx(100 * sum(e > 0 for e in errors) / len(errors))
    by_day = {}
    for d, _, f, a, _ in pairs:
        by_day.setdefault(d, []).append(f - a)
    assert h["over_forecast_days"] == sum(statistics.mean(v) > 0 for v in by_day.values())
    assert [row["date"] for row in body["by_day"]] == sorted(by_day)
    for row in body["by_day"]:
        assert row["bias_mw"] == pytest.approx(statistics.mean(by_day[row["date"]]))


def test_the_january_2026_finding_the_forecast_is_systematically_high():
    h = client.get("/api/accuracy").json()["headline"]
    assert 1700 < h["bias_mw"] < 1950 and 1950 < h["mae_mw"] < 2250
    assert h["over_forecast_days"] >= 26 and h["over_forecast_share_pct"] > 80
    assert h["mae_after_bias_removal_mw"] < 0.75 * h["mae_mw"]     # removing the offset alone cuts the typical miss by a third


def test_accuracy_sections_are_consistent_with_each_other():
    body = client.get("/api/accuracy").json()
    n = body["headline"]["n"]
    assert sum(r["n"] for r in body["by_hour"]) == n == sum(r["n"] for r in body["by_level"]) == sum(r["n"] for r in body["by_day"])
    assert sum(b["count"] for b in body["histogram"]) == n and len(body["scatter"]) == n
    assert [r["hour"] for r in body["by_hour"]] == list(range(24))
    assert len(body["by_level"]) == 4 and body["by_level"][-1]["bias_mw"] > body["by_level"][0]["bias_mw"]
    assert [r["label"] for r in body["by_horizon"]][0] == "0-6 h" and all(r["n"] > 0 for r in body["by_horizon"])
    assert body["persistence"]["n"] == 744 and body["persistence"]["skill_vs_persistence_pct"] > 0
    assert len(body["worst_hours"]) == 10
    worst = [abs(w["error_mw"]) for w in body["worst_hours"]]
    assert worst == sorted(worst, reverse=True)


def test_accuracy_can_be_restricted_to_a_date_range_and_decision_time():
    a = client.get("/api/accuracy", params={"start": "2026-01-10", "end": "2026-01-12"}).json()
    assert a["headline"]["n"] == 72 and a["headline"]["days"] == 3
    b = client.get("/api/accuracy", params={"decision_time": "09:50"}).json()
    c = client.get("/api/accuracy", params={"decision_time": "09:20"}).json()
    assert b["headline"]["mae_mw"] != c["headline"]["mae_mw"]


def test_the_p10_p90_band_is_calibrated_on_the_real_data():
    """An 80% band built from the other days should contain roughly 80% of outturns (it is leave-one-day-out)."""
    inside = total = 0
    for day in ALL_DAYS:
        summary = client.get("/api/decision", params={"delivery_date": day.date().isoformat()}).json()["summary"]
        inside += summary["outturn_inside_band_hours"]
        total += summary["hours_with_actual"]
    assert total == 768 and 0.72 <= inside / total <= 0.88, f"coverage {inside / total:.2%}"


# ----------------------------------------------------------------------------- errors and caching


@pytest.mark.parametrize("path, params, status", [
    ("/api/decision", {"delivery_date": "2026-03-01"}, 404),
    ("/api/decision", {"delivery_date": "2025-12-31"}, 404),
    ("/api/decision", {"delivery_date": "2026-02-02"}, 404),
    ("/api/decision", {"delivery_date": "nope"}, 422),
    ("/api/decision", {"delivery_date": "2026-01-15", "decision_time": "25:99"}, 422),
    ("/api/decision", {"delivery_date": "2026-01-15", "decision_time": "9:20"}, 422),
    ("/api/decision", {}, 422),
    ("/api/accuracy", {"start": "2026-01-20", "end": "2026-01-10"}, 422),
    ("/api/accuracy", {"start": "2025-12-01"}, 404),
    ("/api/accuracy", {"end": "2026-06-01"}, 404),
])
def test_bad_requests_are_rejected_with_the_right_status(path, params, status):
    assert client.get(path, params=params).status_code == status


def test_out_of_scope_message_names_the_valid_range_and_never_claims_coverage():
    detail = client.get("/api/decision", params={"delivery_date": "2026-03-01"}).json()["detail"]
    assert "out of scope" in detail and "2026-01-01" in detail and "2026-02-01" in detail


def test_an_early_cutoff_reports_the_hours_no_forecast_had_reached_instead_of_hiding_them():
    """A 22:30 publication only looks ~46.5 h ahead, so at a 00:00 cutoff the last hours of the day have no forecast."""
    for day in ALL_DAYS:
        body = client.get("/api/decision", params={"delivery_date": day.date().isoformat(), "decision_time": "00:00"}).json()
        assert len(body["hours"]) + len(body["hours_without_forecast"]) == 24
        assert body["hours_without_forecast"] == ["22:00", "23:00"] or day.date().isoformat() == "2026-01-01"
    normal = client.get("/api/decision", params={"delivery_date": "2026-01-20", "decision_time": "09:20"}).json()
    assert normal["hours_without_forecast"] == [] and len(normal["hours"]) == 24


def test_responses_are_cacheable_and_health_is_not():
    assert "s-maxage" in client.get("/api/accuracy").headers["cache-control"]
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_openapi_documents_the_three_data_endpoints():
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {"/api/meta", "/api/decision", "/api/accuracy", "/api/health"} <= set(paths)
