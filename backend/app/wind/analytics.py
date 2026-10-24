"""Decision-time forecast selection and forecast-error analytics (pure Python, no numpy/pandas).

Conventions used everywhere:
  * error = forecast - actual, in MW. Positive = over-forecast = wind came in BELOW the forecast (the costly side
    for a buyer who relied on it).
  * A WINDFOR value for target T (hourly) is compared with the FUELHH WIND outturn whose startTime is T, i.e. the
    half-hour starting at T. Other alignments change the MAE by under 2% on the January 2026 data (see the method page).
  * "Forecast available at the decision" = for each target hour, the latest WINDFOR publication published at or before
    the cutoff (D-1 at the chosen UK local time) that has a value for that hour.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.wind.dataset import Dataset, Publication
from app.wind.scope import LOCAL_TZ

UTC = timezone.utc
LOCAL = ZoneInfo(LOCAL_TZ)
HOUR = timedelta(hours=1)

HORIZON_BUCKETS = ((0, 6), (6, 12), (12, 18), (18, 24), (24, 36), (36, 48), (48, 67))
LARGE_ERROR_MW = 2000.0
HISTOGRAM_BIN_MW = 500


class AnalyticsError(ValueError):
    """The request cannot be answered from the data (out of scope, no forecast available, ...)."""


# ----------------------------------------------------------------------------- time helpers


def parse_decision_time(text: str) -> time:
    try:
        hour, minute = text.split(":")
        return time(int(hour), int(minute))
    except ValueError as exc:
        raise AnalyticsError(f"decision_time must be HH:MM, got {text!r}") from exc


def iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_local(ts: datetime) -> str:
    return ts.astimezone(LOCAL).isoformat(timespec="minutes")


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=LOCAL).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=LOCAL).astimezone(UTC)
    return start, end


def hourly_targets(day: date) -> list[datetime]:
    """Hour starts (UTC) of a UK local day: 24 normally, 23 or 25 on clock-change days."""
    start, end = day_bounds_utc(day)
    return [start + HOUR * i for i in range(int((end - start) / HOUR))]


def decision_cutoff(delivery_day: date, decision_time: time) -> datetime:
    """The moment of the day-ahead decision: D-1 at `decision_time`, UK local time."""
    return datetime.combine(delivery_day - timedelta(days=1), decision_time, tzinfo=LOCAL).astimezone(UTC)


def days_between(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


# ----------------------------------------------------------------------------- statistics


def quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile (same as numpy's default) of an ascending list."""
    if not sorted_values:
        raise AnalyticsError("quantile of an empty sample")
    position = (len(sorted_values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def error_stats(errors: list[float], actuals: list[float]) -> dict[str, float | None]:
    """Standard error metrics for paired errors (forecast - actual) and the matching outturn values."""
    n = len(errors)
    if n == 0:
        raise AnalyticsError("no forecast/actual pairs to evaluate")
    abs_errors = sorted(abs(e) for e in errors)
    mean_actual = mean(actuals)
    bias = mean(errors)
    mae = mean(abs_errors)
    return {
        "n": n,
        "mean_actual_mw": mean_actual,
        "mean_forecast_mw": mean_actual + bias,
        "bias_mw": bias,
        "bias_pct_of_actual": 100 * bias / mean_actual if mean_actual else None,
        "mae_mw": mae,
        "rmse_mw": math.sqrt(mean([e * e for e in errors])),
        "wape_pct": 100 * mae / mean_actual if mean_actual else None,
        "median_abs_error_mw": quantile(abs_errors, 0.5),
        "p90_abs_error_mw": quantile(abs_errors, 0.9),
        "p95_abs_error_mw": quantile(abs_errors, 0.95),
        "over_forecast_share_pct": 100 * sum(e > 0 for e in errors) / n,
        "large_error_share_pct": 100 * sum(abs(e) >= LARGE_ERROR_MW for e in errors) / n,
        "mae_after_bias_removal_mw": mean([abs(e - bias) for e in errors]),
    }


# ----------------------------------------------------------------------------- decision-time pairs


@dataclass(frozen=True)
class Pair:
    day: date
    target: datetime
    forecast: float
    actual: float | None
    publish: datetime

    @property
    def error(self) -> float:
        assert self.actual is not None
        return self.forecast - self.actual

    @property
    def horizon_hours(self) -> float:
        return (self.target - self.publish) / HOUR


def decision_pairs(ds: Dataset, days: list[date], decision_time: time, *, require_actual: bool = True) -> list[Pair]:
    """For every hour of every delivery day: the forecast available at the cutoff, with the outturn if known."""
    pairs: list[Pair] = []
    for day in days:
        cutoff = decision_cutoff(day, decision_time)
        for target in hourly_targets(day):
            found = ds.latest_forecast(target, cutoff)
            if found is None:
                continue
            publication, value = found
            actual = ds.actual.get(target)
            if actual is None and require_actual:
                continue
            pairs.append(Pair(day, target, value, actual, publication.publish))
    return pairs


# ----------------------------------------------------------------------------- level-conditional error band


@dataclass(frozen=True)
class LevelBand:
    lo: float | None  # forecast level range (MW) the band applies to; None = open ended
    hi: float | None
    center: float     # median forecast level of the pairs in this bucket
    n: int
    err_p10: float
    err_p50: float
    err_p90: float


@dataclass(frozen=True)
class ErrorModel:
    """Empirical distribution of (forecast - actual), conditional on the forecast level (data-driven quartiles)."""

    edges: tuple[float, ...]
    bands: tuple[LevelBand, ...]

    def band_for(self, forecast: float) -> LevelBand:
        """The discrete quartile bucket a forecast level falls in (used for tables)."""
        return self.bands[bisect_right(self.edges, forecast)]

    def _smooth(self, forecast: float, pick) -> float:
        """Error quantile at `forecast`, interpolated linearly between bucket centres (flat beyond the outer ones).

        Hard quartile steps would make the plotted band jump whenever the forecast crosses a bucket edge.
        """
        bands = self.bands
        if len(bands) == 1 or forecast <= bands[0].center:
            return pick(bands[0])
        if forecast >= bands[-1].center:
            return pick(bands[-1])
        upper = next(i for i, band in enumerate(bands) if band.center > forecast)
        low, high = bands[upper - 1], bands[upper]
        weight = (forecast - low.center) / (high.center - low.center)
        return pick(low) + (pick(high) - pick(low)) * weight

    def interval(self, forecast: float) -> dict[str, float]:
        """Plausible outturn for `forecast`: p10 floor, median, p90 ceiling. Wind cannot be negative."""
        return {
            "p10_mw": max(0.0, forecast - self._smooth(forecast, lambda b: b.err_p90)),  # 9 in 10 hours at or above
            "p50_mw": max(0.0, forecast - self._smooth(forecast, lambda b: b.err_p50)),
            "p90_mw": max(0.0, forecast - self._smooth(forecast, lambda b: b.err_p10)),
        }


def build_error_model(pairs: list[Pair], buckets: int = 4, min_per_bucket: int = 30) -> ErrorModel:
    """Quartile-of-forecast buckets. Tied forecasts can make edges coincide or leave a bucket empty; such buckets
    are merged into a neighbour so every band is estimated from real samples."""
    if not pairs:
        raise AnalyticsError("cannot build an error model without pairs")
    buckets = max(1, min(buckets, len(pairs) // min_per_bucket))
    forecasts = sorted(p.forecast for p in pairs)
    edges = sorted({quantile(forecasts, k / buckets) for k in range(1, buckets)})

    def assign() -> list[list[Pair]]:
        grouped: list[list[Pair]] = [[] for _ in range(len(edges) + 1)]
        for pair in pairs:
            grouped[bisect_right(edges, pair.forecast)].append(pair)
        return grouped

    grouped = assign()
    while (empty := next((i for i, g in enumerate(grouped) if not g), None)) is not None:
        del edges[max(empty - 1, 0)]
        grouped = assign()
    bands = []
    for i, group in enumerate(grouped):
        errors = sorted(p.error for p in group)
        bands.append(LevelBand(
            lo=None if i == 0 else edges[i - 1], hi=None if i == len(grouped) - 1 else edges[i],
            center=quantile(sorted(p.forecast for p in group), 0.5), n=len(group),
            err_p10=quantile(errors, 0.10), err_p50=quantile(errors, 0.50), err_p90=quantile(errors, 0.90)))
    return ErrorModel(tuple(edges), tuple(bands))


# ----------------------------------------------------------------------------- decision view


def _publication_status(publication: Publication, used: Publication | None, cutoff: datetime) -> str:
    if used is not None and publication.publish == used.publish:
        return "used"
    return "after_cutoff" if publication.publish > cutoff else "earlier"


def decision_view(ds: Dataset, delivery_day: date, decision_time: time, scope_days: list[date]) -> dict:
    """What the buyer holds at the day-ahead cutoff for `delivery_day`, and how it turned out."""
    cutoff = decision_cutoff(delivery_day, decision_time)
    targets = hourly_targets(delivery_day)
    chosen = [ds.latest_forecast(t, cutoff) for t in targets]
    if all(c is None for c in chosen):
        raise AnalyticsError(f"no WINDFOR forecast had been published by {iso_local(cutoff)}")

    # Error model from every OTHER delivery day: the day shown never informs its own band.
    others = [d for d in scope_days if d != delivery_day]
    model = build_error_model(decision_pairs(ds, others, decision_time))

    hours = []
    uncovered = []
    for target, found in zip(targets, chosen):
        if found is None:
            uncovered.append(target.astimezone(LOCAL).strftime("%H:%M"))
            continue
        publication, value = found
        actual = ds.actual.get(target)
        interval = model.interval(value)
        hours.append({
            "start_utc": iso_z(target), "start_local": target.astimezone(LOCAL).strftime("%H:%M"),
            "forecast_mw": value, "publish_utc": iso_z(publication.publish),
            "horizon_hours": (target - publication.publish) / HOUR,
            "actual_mw": actual, "error_mw": None if actual is None else value - actual,
            **interval,
        })

    used_counter: dict[datetime, int] = {}
    for found in chosen:
        if found is not None:
            used_counter[found[0].publish] = used_counter.get(found[0].publish, 0) + 1
    main_publish = max(used_counter, key=lambda p: used_counter[p])
    used = next(p for p in ds.publications if p.publish == main_publish)

    forecasts = [h["forecast_mw"] for h in hours]
    actuals = [h["actual_mw"] for h in hours if h["actual_mw"] is not None]
    errors = [h["error_mw"] for h in hours if h["error_mw"] is not None]
    peak = max(hours, key=lambda h: h["forecast_mw"])
    low = min(hours, key=lambda h: h["forecast_mw"])
    summary = {
        "mean_forecast_mw": mean(forecasts),
        "peak_forecast_mw": peak["forecast_mw"], "peak_forecast_hour": peak["start_local"],
        "min_forecast_mw": low["forecast_mw"], "min_forecast_hour": low["start_local"],
        "mean_p10_floor_mw": mean([h["p10_mw"] for h in hours]),
        "mean_p50_expected_mw": mean([h["p50_mw"] for h in hours]),
        "mean_p90_ceiling_mw": mean([h["p90_mw"] for h in hours]),
        "mean_buffer_mw": mean([h["forecast_mw"] - h["p10_mw"] for h in hours]),
        "mean_actual_mw": mean(actuals) if actuals else None,
        "mean_error_mw": mean(errors) if errors else None,
        "mae_mw": mean([abs(e) for e in errors]) if errors else None,
        "hours_over_forecast": sum(e > 0 for e in errors),
        "hours_with_actual": len(errors),
        "outturn_inside_band_hours": sum(
            1 for h in hours if h["actual_mw"] is not None and h["p10_mw"] <= h["actual_mw"] <= h["p90_mw"]),
    }

    day_start, day_end = day_bounds_utc(delivery_day)
    window_start = day_start - timedelta(days=3)
    evolution = []
    for publication in ds.publications:
        if not (window_start <= publication.publish < day_end):
            continue
        values = [publication.value_at(t) for t in targets]
        if all(v is None for v in values):
            continue
        covered = [v for v in values if v is not None]
        evolution.append({
            "publish_utc": iso_z(publication.publish), "publish_local": iso_local(publication.publish),
            "status": _publication_status(publication, used, cutoff),
            "values": values, "mean_forecast_mw": mean(covered), "hours_covered": len(covered),
        })
    used_entry = next((e for e in evolution if e["status"] == "used"), None)
    decision_mean = used_entry["mean_forecast_mw"] if used_entry else summary["mean_forecast_mw"]
    for entry in evolution:
        entry["delta_vs_decision_mw"] = entry["mean_forecast_mw"] - decision_mean

    return {
        "delivery_date": delivery_day.isoformat(),
        "decision_time": decision_time.strftime("%H:%M"),
        "cutoff_utc": iso_z(cutoff), "cutoff_local": iso_local(cutoff),
        "decision_date": (delivery_day - timedelta(days=1)).isoformat(),
        "used_publication": {
            "publish_utc": iso_z(used.publish), "publish_local": iso_local(used.publish),
            "age_at_cutoff_minutes": round((cutoff - used.publish).total_seconds() / 60),
            "hours_covered": used_counter[used.publish],
        },
        "hours": hours,
        "hours_without_forecast": uncovered,   # hours of the day no publication had reached by the cutoff
        "actual_half_hourly": [
            {"start_utc": iso_z(t), "actual_mw": ds.actual[t]}
            for t in (day_start + timedelta(minutes=30) * i for i in range(int((day_end - day_start) / timedelta(minutes=30))))
            if t in ds.actual],
        "summary": summary,
        "evolution": evolution,
        "error_model": {
            "built_from_days": len(others),
            "buckets": [
                {"lo_mw": b.lo, "hi_mw": b.hi, "n": b.n, "error_p10_mw": b.err_p10,
                 "error_p50_mw": b.err_p50, "error_p90_mw": b.err_p90} for b in model.bands],
        },
    }


# ----------------------------------------------------------------------------- accuracy view


def _bucket_label(lo: float | None, hi: float | None) -> str:
    if lo is None and hi is None:
        return "all forecast levels"
    if lo is None:
        return f"below {hi / 1000:.1f} GW"
    if hi is None:
        return f"{lo / 1000:.1f} GW and above"
    return f"{lo / 1000:.1f} to {hi / 1000:.1f} GW"


def _group_stats(pairs: list[Pair]) -> dict[str, float]:
    stats = error_stats([p.error for p in pairs], [p.actual for p in pairs])
    return {k: stats[k] for k in ("n", "bias_mw", "mae_mw", "rmse_mw")}


def horizon_table(ds: Dataset, days: list[date]) -> list[dict]:
    """Error by forecast lead time, across ALL publications for the chosen delivery days (not only the cutoff one)."""
    actual_for_target = {t: ds.actual[t] for day in days for t in hourly_targets(day) if t in ds.actual}
    buckets: dict[tuple[int, int], list[float]] = {b: [] for b in HORIZON_BUCKETS}
    for publication in ds.publications:
        for index, value in enumerate(publication.values):
            target = publication.first + HOUR * index
            actual = actual_for_target.get(target)
            if actual is None:
                continue
            horizon = (target - publication.publish) / HOUR
            for lo, hi in HORIZON_BUCKETS:
                if lo <= horizon < hi:
                    buckets[(lo, hi)].append(value - actual)
                    break
    rows = []
    for (lo, hi), errors in buckets.items():
        if not errors:
            continue
        rows.append({"label": f"{lo}-{hi} h", "lo_hours": lo, "hi_hours": hi, "n": len(errors),
                     "bias_mw": mean(errors), "mae_mw": mean([abs(e) for e in errors]),
                     "rmse_mw": math.sqrt(mean([e * e for e in errors]))})
    return rows


def persistence_benchmark(ds: Dataset, pairs: list[Pair], decision_time: time) -> dict | None:
    """Naive benchmark: hold the newest outturn known at the cutoff flat across the delivery day."""
    errors_persist, errors_forecast = [], []
    for pair in pairs:
        known = ds.last_actual_before(decision_cutoff(pair.day, decision_time))
        if known is None:
            continue
        errors_persist.append(abs(known[1] - pair.actual))
        errors_forecast.append(abs(pair.error))
    if not errors_persist:
        return None
    persist_mae, forecast_mae = mean(errors_persist), mean(errors_forecast)
    return {"n": len(errors_persist), "persistence_mae_mw": persist_mae, "forecast_mae_same_hours_mw": forecast_mae,
            "skill_vs_persistence_pct": 100 * (1 - forecast_mae / persist_mae)}


def accuracy_view(ds: Dataset, days: list[date], decision_time: time) -> dict:
    pairs = decision_pairs(ds, days, decision_time)
    if not pairs:
        raise AnalyticsError("no forecast/actual pairs for the selected days")
    errors = [p.error for p in pairs]
    actuals = [p.actual for p in pairs]
    headline = error_stats(errors, actuals)
    sorted_errors = sorted(errors)
    headline["error_quantiles_mw"] = {name: quantile(sorted_errors, q) for name, q in
                                      (("p5", 0.05), ("p10", 0.10), ("p50", 0.50), ("p90", 0.90), ("p95", 0.95))}
    by_day_map: dict[date, list[Pair]] = {}
    for pair in pairs:
        by_day_map.setdefault(pair.day, []).append(pair)
    by_day = [{"date": d.isoformat(), **_group_stats(group),
               "mean_actual_mw": mean([p.actual for p in group]), "mean_forecast_mw": mean([p.forecast for p in group])}
              for d, group in sorted(by_day_map.items())]
    headline["over_forecast_days"] = sum(1 for row in by_day if row["bias_mw"] > 0)
    headline["days"] = len(by_day)

    by_hour_map: dict[int, list[Pair]] = {}
    for pair in pairs:
        by_hour_map.setdefault(pair.target.astimezone(LOCAL).hour, []).append(pair)
    by_hour = [{"hour": h, **_group_stats(group)} for h, group in sorted(by_hour_map.items())]

    model = build_error_model(pairs)
    by_level = []
    for band in model.bands:
        group = [p for p in pairs if model.band_for(p.forecast) is band]
        by_level.append({"label": _bucket_label(band.lo, band.hi), "lo_mw": band.lo, "hi_mw": band.hi,
                         **_group_stats(group), "error_p10_mw": band.err_p10, "error_p90_mw": band.err_p90})

    lo_bin = math.floor(min(errors) / HISTOGRAM_BIN_MW) * HISTOGRAM_BIN_MW
    hi_bin = math.ceil((max(errors) + 1e-9) / HISTOGRAM_BIN_MW) * HISTOGRAM_BIN_MW
    histogram = []
    for lo in range(lo_bin, hi_bin, HISTOGRAM_BIN_MW):
        count = sum(1 for e in errors if lo <= e < lo + HISTOGRAM_BIN_MW)
        histogram.append({"lo_mw": lo, "hi_mw": lo + HISTOGRAM_BIN_MW, "count": count})

    worst = sorted(pairs, key=lambda p: abs(p.error), reverse=True)[:10]
    return {
        "decision_time": decision_time.strftime("%H:%M"),
        "first_delivery_date": min(days).isoformat(), "last_delivery_date": max(days).isoformat(),
        "headline": headline,
        "persistence": persistence_benchmark(ds, pairs, decision_time),
        "by_horizon": horizon_table(ds, days),
        "by_hour": by_hour, "by_level": by_level, "by_day": by_day, "histogram": histogram,
        "scatter": [[p.forecast, p.actual] for p in pairs],
        "worst_hours": [{"start_utc": iso_z(p.target), "delivery_date": p.day.isoformat(),
                         "forecast_mw": p.forecast, "actual_mw": p.actual, "error_mw": p.error,
                         "publish_utc": iso_z(p.publish)} for p in worst],
    }
