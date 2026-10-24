"""HTTP endpoints (read-only)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response

from app.wind import analytics, scope
from app.wind.dataset import Dataset, SnapshotError, load_dataset
from app.wind.schemas import AccuracyResponse, DecisionResponse, MetaResponse

router = APIRouter(prefix="/api")

CACHE_CONTROL = "public, max-age=300, s-maxage=3600"  # data is a fixed snapshot, safe to cache
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

ASSUMPTIONS = [
    "Scope is Elexon only: FUELHH WIND outturn and WINDFOR forecasts. No demand, price or other data is used, so this "
    "app quantifies wind forecast risk but cannot compute the total volume to buy.",
    "Decisions are taken on D-1 for delivery day D. The forecast 'available at the decision' is, for each hour, the "
    "latest WINDFOR publication at or before the cutoff time you choose (UK local time).",
    "WINDFOR is hourly; FUELHH is half-hourly. A forecast for start time T is compared with the outturn whose start "
    "time is T. Other alignments change MAE by under 2% on this data.",
    "Error = forecast minus outturn. Positive means the forecast was too high, i.e. wind came in below it.",
    "The planning band is the empirical P10-P90 of past error for forecasts of a similar size, built from all OTHER "
    "delivery days in the window. It describes January 2026 behaviour; it is not a guarantee for future days.",
    "WINDFOR covers wind farms visible to NESO with operational metering. Outturn is FUELHH WIND. Any difference in "
    "what the two include (for example curtailed output) is not observable from Elexon data alone.",
]


def _dataset() -> Dataset:
    try:
        return load_dataset()
    except SnapshotError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _scope_days() -> list[date]:
    return analytics.days_between(scope.DELIVERY_FIRST, scope.DELIVERY_LAST)


def _check_day(day: date) -> None:
    if not scope.DELIVERY_FIRST <= day <= scope.DELIVERY_LAST:
        raise HTTPException(
            status_code=404,
            detail=f"{day} is out of scope: delivery days {scope.DELIVERY_FIRST} to {scope.DELIVERY_LAST} "
                   "(day-ahead decisions made in January 2026).")


def _decision_time(text: str):
    try:
        return analytics.parse_decision_time(text)
    except analytics.AnalyticsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
def health(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    ds = _dataset()
    return {"status": "ok", "snapshot_sha256": ds.sha256}


@router.get("/meta", response_model=MetaResponse)
def meta(response: Response) -> dict:
    response.headers["Cache-Control"] = CACHE_CONTROL
    ds = _dataset()
    info = ds.meta
    return {
        "title": "Wind Intelligence: day-ahead wind forecast check",
        "scope_note": "Elexon FUELHH (WIND) and WINDFOR only. Delivery days 1 January - 1 February 2026, i.e. "
                      "day-ahead decisions made in January 2026 (1 January delivery was decided on 31 December).",
        "delivery_days": [
            {"date": d.isoformat(), "decision_date": (d - timedelta(days=1)).isoformat(),
             "decision_in_january_2026": scope.DECISION_WINDOW_FIRST <= d - timedelta(days=1) <= scope.DECISION_WINDOW_LAST}
            for d in _scope_days()],
        "default_decision_time": scope.DEFAULT_DECISION_TIME.strftime("%H:%M"),
        "decision_presets": list(scope.DECISION_PRESETS),
        "data": {
            "source": info["source"], "fetched_at": info["fetched_at"], "snapshot_sha256": ds.sha256,
            "actual_half_hours": len(ds.actual), "forecast_publications": len(ds.publications),
            "forecast_hourly_values": info["windfor_rows_stored"],
            "publish_clock_times_utc": info["windfor_publish_clock_times_utc"], "units": info["units"],
        },
        "assumptions": ASSUMPTIONS,
    }


@router.get("/decision", response_model=DecisionResponse)
def decision(response: Response, delivery_date: date,
             decision_time: str = Query(scope.DEFAULT_DECISION_TIME.strftime("%H:%M"), pattern=TIME_PATTERN)) -> dict:
    _check_day(delivery_date)
    parsed = _decision_time(decision_time)
    response.headers["Cache-Control"] = CACHE_CONTROL
    try:
        return analytics.decision_view(_dataset(), delivery_date, parsed, _scope_days())
    except analytics.AnalyticsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/accuracy", response_model=AccuracyResponse)
def accuracy(response: Response, start: date | None = None, end: date | None = None,
             decision_time: str = Query(scope.DEFAULT_DECISION_TIME.strftime("%H:%M"), pattern=TIME_PATTERN)) -> dict:
    first, last = start or scope.DELIVERY_FIRST, end or scope.DELIVERY_LAST
    _check_day(first)
    _check_day(last)
    if first > last:
        raise HTTPException(status_code=422, detail="start must not be after end")
    parsed = _decision_time(decision_time)
    response.headers["Cache-Control"] = CACHE_CONTROL
    try:
        return analytics.accuracy_view(_dataset(), analytics.days_between(first, last), parsed)
    except analytics.AnalyticsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
