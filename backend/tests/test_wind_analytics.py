"""Logic tests for decision-time selection and error analytics, on synthetic data."""

from __future__ import annotations

import statistics
from datetime import date, datetime, time, timedelta, timezone

import pytest
from wind_helpers import make_dataset, utc

from app.wind import analytics as A
from app.wind.dataset import Dataset, Publication

UTC = timezone.utc
DAYS = A.days_between(date(2026, 1, 5), date(2026, 1, 10))
T0920 = time(9, 20)


# ----------------------------------------------------------------------------- time helpers


def test_winter_day_has_24_hours_and_utc_equals_local():
    targets = A.hourly_targets(date(2026, 1, 15))
    assert len(targets) == 24 and targets[0] == utc("2026-01-15T00:00Z") and targets[-1] == utc("2026-01-15T23:00Z")


def test_summer_day_is_shifted_one_hour_to_utc():
    targets = A.hourly_targets(date(2026, 7, 15))
    assert len(targets) == 24 and targets[0] == utc("2026-07-14T23:00Z")


def test_clock_change_days_have_23_and_25_hours():
    assert len(A.hourly_targets(date(2026, 3, 29))) == 23   # spring forward (last Sunday of March)
    assert len(A.hourly_targets(date(2025, 10, 26))) == 25  # autumn back


def test_decision_cutoff_is_previous_day_local_time():
    assert A.decision_cutoff(date(2026, 1, 15), T0920) == utc("2026-01-14T09:20Z")
    assert A.decision_cutoff(date(2026, 7, 15), T0920) == utc("2026-07-14T08:20Z")  # BST = UTC+1


@pytest.mark.parametrize("bad", ["", "9", "0920", "ab:cd", "25:00", "09:61", "9:5:3"])
def test_bad_decision_time_is_rejected(bad):
    with pytest.raises(A.AnalyticsError):
        A.parse_decision_time(bad)


def test_decision_time_parses():
    assert A.parse_decision_time("09:50") == time(9, 50)


# ----------------------------------------------------------------------------- statistics


def test_quantile_matches_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0]
    assert A.quantile(values, 0.5) == 2.5 and A.quantile(values, 0.0) == 1.0 and A.quantile(values, 1.0) == 4.0
    assert A.quantile(values, 0.1) == pytest.approx(1.3)
    sample = sorted([5.0, 1.0, 9.0, 3.0, 7.0, 11.0, 2.0])
    assert A.quantile(sample, 0.9) == pytest.approx(statistics.quantiles(sample, n=10, method="inclusive")[-1])
    with pytest.raises(A.AnalyticsError):
        A.quantile([], 0.5)


def test_error_stats_known_values():
    stats = A.error_stats([100.0, -100.0, 300.0], [1000.0, 1000.0, 1000.0])
    assert stats["n"] == 3 and stats["bias_mw"] == pytest.approx(100.0)
    assert stats["mae_mw"] == pytest.approx(500 / 3)
    assert stats["rmse_mw"] == pytest.approx(((100**2 + 100**2 + 300**2) / 3) ** 0.5)
    assert stats["wape_pct"] == pytest.approx(100 * (500 / 3) / 1000)
    assert stats["over_forecast_share_pct"] == pytest.approx(200 / 3)
    assert stats["mean_forecast_mw"] == pytest.approx(1100.0)
    assert stats["mae_after_bias_removal_mw"] == pytest.approx((0 + 200 + 200) / 3)
    assert stats["large_error_share_pct"] == 0


def test_error_stats_large_error_threshold_is_inclusive():
    assert A.error_stats([2000.0, -2000.0, 1999.0], [5000.0] * 3)["large_error_share_pct"] == pytest.approx(200 / 3)


def test_error_stats_rejects_empty():
    with pytest.raises(A.AnalyticsError):
        A.error_stats([], [])


# ----------------------------------------------------------------------------- publications and selection


def _pub(publish: str, first: str, values) -> Publication:
    return Publication(utc(publish), utc(first), tuple(float(v) for v in values))


def _dataset(pubs, actual=None) -> Dataset:
    pubs = sorted(pubs, key=lambda p: p.publish)
    return Dataset({}, actual or {}, tuple(pubs), "0" * 64, tuple(p.publish for p in pubs))


def test_publication_value_at_requires_an_aligned_covered_hour():
    pub = _pub("2026-01-10T07:30Z", "2026-01-10T00:00Z", [10, 11, 12])
    assert pub.value_at(utc("2026-01-10T01:00Z")) == 11
    assert pub.value_at(utc("2026-01-10T01:30Z")) is None      # half hour: WINDFOR is hourly
    assert pub.value_at(utc("2026-01-09T23:00Z")) is None      # before first
    assert pub.value_at(utc("2026-01-10T03:00Z")) is None      # after last
    assert pub.last == utc("2026-01-10T02:00Z")


def test_latest_forecast_is_the_latest_publication_at_or_before_the_cutoff():
    early = _pub("2026-01-14T02:30Z", "2026-01-14T00:00Z", [1] * 48)
    mid = _pub("2026-01-14T07:30Z", "2026-01-14T00:00Z", [2] * 48)
    late = _pub("2026-01-14T09:30Z", "2026-01-14T00:00Z", [3] * 48)
    ds = _dataset([early, mid, late])
    target = utc("2026-01-15T00:00Z")
    assert ds.latest_forecast(target, utc("2026-01-14T09:20Z"))[1] == 2
    assert ds.latest_forecast(target, utc("2026-01-14T09:30Z"))[1] == 3   # published exactly at cutoff counts
    assert ds.latest_forecast(target, utc("2026-01-14T09:29Z"))[1] == 2
    assert ds.latest_forecast(target, utc("2026-01-14T02:29Z")) is None   # nothing published yet


def test_latest_forecast_falls_back_to_an_earlier_publication_that_covers_the_target():
    covers = _pub("2026-01-14T02:30Z", "2026-01-14T00:00Z", [5] * 48)
    short = _pub("2026-01-14T07:30Z", "2026-01-14T00:00Z", [9] * 10)  # does not reach 15 Jan
    ds = _dataset([covers, short])
    publication, value = ds.latest_forecast(utc("2026-01-15T00:00Z"), utc("2026-01-14T09:20Z"))
    assert value == 5 and publication.publish == utc("2026-01-14T02:30Z")


def test_last_actual_before_uses_only_finished_half_hours():
    actual = {utc("2026-01-14T08:00Z") + timedelta(minutes=30) * i: float(i) for i in range(6)}
    ds = _dataset([_pub("2026-01-14T02:30Z", "2026-01-14T00:00Z", [1])], actual)
    assert ds.last_actual_before(utc("2026-01-14T09:20Z"))[0] == utc("2026-01-14T08:30Z")  # 09:00 period still open
    assert ds.last_actual_before(utc("2026-01-14T09:30Z"))[0] == utc("2026-01-14T09:00Z")
    assert ds.last_actual_before(utc("2026-01-14T09:00Z"))[0] == utc("2026-01-14T08:30Z")
    assert ds.last_actual_before(utc("2026-01-13T09:00Z")) is None


# ----------------------------------------------------------------------------- pairs


def test_decision_pairs_use_the_publication_available_at_the_cutoff_not_a_later_one():
    # 07:30 publication says 1000, the 09:30 one says 2000: a 09:20 decision must see 1000
    ds = make_dataset(date(2026, 1, 9), date(2026, 1, 11),
                      forecast=lambda publish, target: 2000 if publish.strftime("%H:%M") == "09:30" else 1000,
                      actual=lambda t: 900)
    pairs = A.decision_pairs(ds, [date(2026, 1, 10)], T0920)
    assert len(pairs) == 24 and {p.forecast for p in pairs} == {1000.0}
    assert {p.publish for p in pairs} == {utc("2026-01-09T07:30Z")}
    later = A.decision_pairs(ds, [date(2026, 1, 10)], time(9, 40))
    assert {p.forecast for p in later} == {2000.0}


def test_decision_pairs_skip_hours_without_outturn_unless_asked():
    ds = make_dataset(date(2026, 1, 9), date(2026, 1, 10), forecast=lambda p, t: 100, actual=lambda t: 90)
    assert len(A.decision_pairs(ds, [date(2026, 1, 11)], T0920)) == 0
    assert len(A.decision_pairs(ds, [date(2026, 1, 11)], T0920, require_actual=False)) == 24


def test_pair_error_and_horizon():
    pair = A.Pair(date(2026, 1, 15), utc("2026-01-15T12:00Z"), 1500.0, 1200.0, utc("2026-01-14T07:30Z"))
    assert pair.error == 300.0 and pair.horizon_hours == pytest.approx(28.5)


# ----------------------------------------------------------------------------- error model


def _pairs(forecasts, errors):
    return [A.Pair(date(2026, 1, 5), utc("2026-01-05T00:00Z") + timedelta(hours=i), float(f), float(f - e),
                   utc("2026-01-04T07:30Z")) for i, (f, e) in enumerate(zip(forecasts, errors))]


def test_error_model_bands_are_conditional_on_forecast_level():
    low = list(range(1000, 1060))     # 60 low forecasts, error always +100 (over-forecast)
    high = list(range(9000, 9060))    # 60 high forecasts, error always +1000
    model = A.build_error_model(_pairs(low + high, [100] * 60 + [1000] * 60), buckets=2)
    assert len(model.bands) == 2 and model.bands[0].n == 60 and model.bands[1].n == 60
    assert model.bands[0].center == pytest.approx(1029.5) and model.bands[1].center == pytest.approx(9029.5)
    assert model.interval(1029.5)["p50_mw"] == pytest.approx(1029.5 - 100)          # at a centre: that bucket's error
    assert model.interval(9029.5)["p50_mw"] == pytest.approx(9029.5 - 1000)
    assert model.interval(500)["p50_mw"] == pytest.approx(500 - 100)                # flat beyond the outer centres
    assert model.interval(9900)["p50_mw"] == pytest.approx(9900 - 1000)
    assert model.interval(9500)["p10_mw"] == pytest.approx(9500 - 1000) and model.interval(9500)["p90_mw"] == pytest.approx(9500 - 1000)


def test_interval_changes_smoothly_across_a_bucket_edge():
    """The plotted band must not jump when the forecast crosses a quartile boundary (the notch seen in the UI)."""
    forecasts = list(range(1000, 1060)) + list(range(9000, 9060))
    model = A.build_error_model(_pairs(forecasts, [100] * 60 + [1000] * 60), buckets=2)
    edge = model.edges[0]
    below, above = model.interval(edge - 1e-6), model.interval(edge + 1e-6)
    assert abs(below["p50_mw"] - above["p50_mw"]) < 1e-3
    midpoint = (model.bands[0].center + model.bands[1].center) / 2
    assert model.interval(midpoint)["p50_mw"] == pytest.approx(midpoint - 550)       # halfway between 100 and 1000
    sampled = [model.interval(f)["p10_mw"] for f in range(1000, 9100, 100)]
    assert all(b > a for a, b in zip(sampled, sampled[1:]))   # errors grow slower than forecasts: floor keeps rising
    assert all(value >= 0 for value in sampled)


def test_error_model_interval_orders_floor_median_ceiling_and_clamps_at_zero():
    errors = [-500, -100, 0, 100, 400, 900] * 10
    model = A.build_error_model(_pairs([2000] * 60, errors), buckets=1)
    band = model.interval(2000)
    assert band["p10_mw"] <= band["p50_mw"] <= band["p90_mw"]
    assert model.interval(300)["p10_mw"] == 0.0  # error p90 (~700) exceeds the forecast: wind cannot be negative


def test_error_model_collapses_to_one_bucket_when_samples_are_scarce():
    assert len(A.build_error_model(_pairs([1000, 2000, 3000], [1, 2, 3])).bands) == 1
    with pytest.raises(A.AnalyticsError):
        A.build_error_model([])


# ----------------------------------------------------------------------------- views


def _biased_dataset(bias=500.0):
    return make_dataset(date(2026, 1, 4), date(2026, 1, 12),
                        forecast=lambda p, t: 5000 + 100 * (t.hour % 6) + bias,
                        actual=lambda t: 5000 + 100 * (t.hour % 6))


def test_accuracy_view_recovers_a_constant_bias():
    view = A.accuracy_view(_biased_dataset(), A.days_between(date(2026, 1, 6), date(2026, 1, 11)), T0920)
    h = view["headline"]
    assert h["n"] == 6 * 24 and h["days"] == 6
    assert h["bias_mw"] == pytest.approx(500) and h["mae_mw"] == pytest.approx(500) and h["rmse_mw"] == pytest.approx(500)
    assert h["mae_after_bias_removal_mw"] == pytest.approx(0)
    assert h["over_forecast_share_pct"] == 100 and h["over_forecast_days"] == 6
    assert h["error_quantiles_mw"]["p5"] == pytest.approx(500) == pytest.approx(h["error_quantiles_mw"]["p95"])
    assert sum(b["count"] for b in view["histogram"]) == h["n"]
    assert len(view["scatter"]) == h["n"] and len(view["by_hour"]) == 24 and len(view["by_day"]) == 6
    assert all(row["bias_mw"] == pytest.approx(500) for row in view["by_horizon"])
    assert len(view["worst_hours"]) == 10


def test_accuracy_view_horizon_buckets_cover_lead_times_and_exclude_negative_horizons():
    view = A.accuracy_view(_biased_dataset(), A.days_between(date(2026, 1, 6), date(2026, 1, 11)), T0920)
    assert [row["label"] for row in view["by_horizon"]][0] == "0-6 h"
    assert sum(row["n"] for row in view["by_horizon"]) > 0
    # forecasts for hours already elapsed (publication after the target) are not lead-time forecasts
    ds = _biased_dataset()
    counted = sum(row["n"] for row in A.horizon_table(ds, A.days_between(date(2026, 1, 6), date(2026, 1, 6))))
    assert counted == sum(
        1 for pub in ds.publications for i in range(len(pub.values))
        if (t := pub.first + timedelta(hours=i)).date() == date(2026, 1, 6) and (t - pub.publish) >= timedelta(0))


def test_horizon_bucket_boundaries_are_lower_inclusive():
    pub = Publication(utc("2026-01-10T00:00Z"), utc("2026-01-10T06:00Z"), (100.0,))   # horizon exactly 6 h
    ds = Dataset({}, {utc("2026-01-10T06:00Z"): 90.0}, (pub,), "0" * 64, (pub.publish,))
    rows = A.horizon_table(ds, [date(2026, 1, 10)])
    assert [r["label"] for r in rows] == ["6-12 h"] and rows[0]["bias_mw"] == 10.0


def test_persistence_benchmark_scores_a_perfect_forecast_against_a_naive_one():
    # outturn ramps up 100 MW per hour; forecast is perfect; persistence is stuck at the cutoff value
    ds = make_dataset(date(2026, 1, 4), date(2026, 1, 10), forecast=lambda p, t: 1000 + 100 * ((t - utc("2026-01-01T00:00Z")) / timedelta(hours=1)),
                      actual=lambda t: 1000 + 100 * ((t - utc("2026-01-01T00:00Z")) / timedelta(hours=1)))
    view = A.accuracy_view(ds, A.days_between(date(2026, 1, 6), date(2026, 1, 9)), T0920)
    assert view["headline"]["mae_mw"] == pytest.approx(0)
    assert view["persistence"]["skill_vs_persistence_pct"] == pytest.approx(100.0)
    assert view["persistence"]["persistence_mae_mw"] > 0


def test_persistence_is_absent_when_no_outturn_precedes_the_cutoff():
    ds = make_dataset(date(2026, 1, 10), date(2026, 1, 10), forecast=lambda p, t: 100, actual=lambda t: 90)
    view = A.accuracy_view(ds, [date(2026, 1, 10)], T0920)   # cutoff 9 Jan 09:20; actuals start 10 Jan
    assert view["persistence"] is None


def test_accuracy_view_errors_when_nothing_can_be_evaluated():
    ds = make_dataset(date(2026, 1, 5), date(2026, 1, 6), forecast=lambda p, t: 1, actual=lambda t: 1)
    with pytest.raises(A.AnalyticsError):
        A.accuracy_view(ds, [date(2026, 2, 20)], T0920)


def test_decision_view_marks_each_publication_and_computes_revisions():
    ds = make_dataset(date(2026, 1, 4), date(2026, 1, 12),
                      forecast=lambda p, t: 5000 + {"02:30": -100, "07:30": 0, "09:30": 250, "15:30": 900}[p.strftime("%H:%M")],
                      actual=lambda t: 4800)
    days = A.days_between(date(2026, 1, 5), date(2026, 1, 11))
    view = A.decision_view(ds, date(2026, 1, 8), T0920, days)
    assert view["decision_date"] == "2026-01-07" and view["cutoff_utc"] == "2026-01-07T09:20:00Z"
    assert view["used_publication"]["publish_utc"] == "2026-01-07T07:30:00Z"
    assert view["used_publication"]["age_at_cutoff_minutes"] == 110 and view["used_publication"]["hours_covered"] == 24
    by_time = {e["publish_utc"]: e for e in view["evolution"]}
    assert by_time["2026-01-07T07:30:00Z"]["status"] == "used" and by_time["2026-01-07T07:30:00Z"]["delta_vs_decision_mw"] == 0
    assert by_time["2026-01-07T02:30:00Z"]["status"] == "earlier" and by_time["2026-01-07T02:30:00Z"]["delta_vs_decision_mw"] == pytest.approx(-100)
    assert by_time["2026-01-07T09:30:00Z"]["status"] == "after_cutoff" and by_time["2026-01-07T09:30:00Z"]["delta_vs_decision_mw"] == pytest.approx(250)
    assert by_time["2026-01-07T15:30:00Z"]["delta_vs_decision_mw"] == pytest.approx(900)
    assert len(view["hours"]) == 24 and all(h["forecast_mw"] == 5000 for h in view["hours"])
    assert view["summary"]["mean_error_mw"] == pytest.approx(200) and view["summary"]["hours_over_forecast"] == 24
    assert len(view["actual_half_hourly"]) == 48


def test_decision_view_error_model_excludes_the_day_being_viewed():
    # every day has bias +100 except 8 Jan, which has +5000: the band for 8 Jan must not learn from 8 Jan itself
    ds = make_dataset(date(2026, 1, 4), date(2026, 1, 12),
                      forecast=lambda p, t: 10000 + (5000 if t.date() == date(2026, 1, 8) else 100),
                      actual=lambda t: 10000)
    days = A.days_between(date(2026, 1, 5), date(2026, 1, 11))
    view = A.decision_view(ds, date(2026, 1, 8), T0920, days)
    assert view["error_model"]["built_from_days"] == len(days) - 1
    assert all(b["error_p50_mw"] == pytest.approx(100) for b in view["error_model"]["buckets"])
    assert view["summary"]["mean_error_mw"] == pytest.approx(5000)
    assert view["summary"]["outturn_inside_band_hours"] == 0   # the band says ~+100, reality was +5000


def test_decision_view_without_any_published_forecast_is_an_error():
    ds = make_dataset(date(2026, 1, 8), date(2026, 1, 9), forecast=lambda p, t: 1, actual=lambda t: 1, pre_days=0)
    with pytest.raises(A.AnalyticsError, match="no WINDFOR forecast"):
        A.decision_view(ds, date(2026, 1, 8), time(1, 0), [date(2026, 1, 8), date(2026, 1, 9)])


def test_decision_view_on_a_clock_change_day_has_the_right_number_of_hours():
    ds = make_dataset(date(2026, 3, 26), date(2026, 3, 31), forecast=lambda p, t: 100, actual=lambda t: 90)
    days = A.days_between(date(2026, 3, 27), date(2026, 3, 31))
    view = A.decision_view(ds, date(2026, 3, 29), T0920, days)
    assert len(view["hours"]) == 23 and view["hours"][0]["start_utc"] == "2026-03-29T00:00:00Z"
    assert view["hours"][-1]["start_local"] == "23:00" and view["hours"][-1]["start_utc"] == "2026-03-29T22:00:00Z"


# ----------------------------------------------------------------------------- regressions (see BUG_LOG.md)


def test_regression_tied_forecasts_do_not_leave_empty_buckets():
    """BUG-010: a constant forecast made every quartile edge equal, leaving three empty buckets and a crash."""
    model = A.build_error_model(_pairs([100] * 200, [10] * 200))
    assert len(model.bands) == 1 and model.bands[0].n == 200 and model.edges == ()
    partly_tied = A.build_error_model(_pairs([100] * 150 + list(range(1000, 1050)), [5] * 150 + [50] * 50))
    assert all(band.n > 0 for band in partly_tied.bands) and sum(band.n for band in partly_tied.bands) == 200


def test_regression_single_bucket_has_a_label_and_a_view():
    """BUG-011: with too few samples the model has one open-ended bucket; its label formatting crashed."""
    assert A._bucket_label(None, None) == "all forecast levels"
    ds = make_dataset(date(2026, 1, 10), date(2026, 1, 10), forecast=lambda p, t: 100, actual=lambda t: 90)
    view = A.accuracy_view(ds, [date(2026, 1, 10)], T0920)
    assert [row["label"] for row in view["by_level"]] == ["all forecast levels"]


def test_regression_band_edges_are_exactly_the_stated_percentiles():
    """Found by mutation testing: nothing pinned which percentiles the planning band uses."""
    errors = list(range(0, 101))                                    # uniform 0..100, so p10=10, p50=50, p90=90
    model = A.build_error_model(_pairs([2000] * 101, errors), buckets=1)
    band = model.bands[0]
    assert (band.err_p10, band.err_p50, band.err_p90) == (pytest.approx(10), pytest.approx(50), pytest.approx(90))
    assert model.interval(2000) == {"p10_mw": pytest.approx(1910), "p50_mw": pytest.approx(1950), "p90_mw": pytest.approx(1990)}
