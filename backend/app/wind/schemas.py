"""Response models for the wind API (the contract the React app is typed against)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HourPoint(BaseModel):
    start_utc: str
    start_local: str
    forecast_mw: float
    publish_utc: str
    horizon_hours: float
    actual_mw: float | None
    error_mw: float | None
    p10_mw: float
    p50_mw: float
    p90_mw: float


class HalfHourActual(BaseModel):
    start_utc: str
    actual_mw: float


class UsedPublication(BaseModel):
    publish_utc: str
    publish_local: str
    age_at_cutoff_minutes: int
    hours_covered: int


class DaySummary(BaseModel):
    mean_forecast_mw: float
    peak_forecast_mw: float
    peak_forecast_hour: str
    min_forecast_mw: float
    min_forecast_hour: str
    mean_p10_floor_mw: float
    mean_p50_expected_mw: float
    mean_p90_ceiling_mw: float
    mean_buffer_mw: float
    mean_actual_mw: float | None
    mean_error_mw: float | None
    mae_mw: float | None
    hours_over_forecast: int
    hours_with_actual: int
    outturn_inside_band_hours: int


class EvolutionEntry(BaseModel):
    publish_utc: str
    publish_local: str
    status: Literal["used", "earlier", "after_cutoff"]
    values: list[float | None]
    mean_forecast_mw: float
    hours_covered: int
    delta_vs_decision_mw: float


class ErrorBucket(BaseModel):
    lo_mw: float | None
    hi_mw: float | None
    n: int
    error_p10_mw: float
    error_p50_mw: float
    error_p90_mw: float


class ErrorModelInfo(BaseModel):
    built_from_days: int
    buckets: list[ErrorBucket]


class DecisionResponse(BaseModel):
    delivery_date: str
    decision_date: str
    decision_time: str
    cutoff_utc: str
    cutoff_local: str
    used_publication: UsedPublication
    hours: list[HourPoint]
    hours_without_forecast: list[str]
    actual_half_hourly: list[HalfHourActual]
    summary: DaySummary
    evolution: list[EvolutionEntry]
    error_model: ErrorModelInfo


class ErrorQuantiles(BaseModel):
    p5: float
    p10: float
    p50: float
    p90: float
    p95: float


class Headline(BaseModel):
    n: int
    days: int
    over_forecast_days: int
    mean_actual_mw: float
    mean_forecast_mw: float
    bias_mw: float
    bias_pct_of_actual: float | None
    mae_mw: float
    rmse_mw: float
    wape_pct: float | None
    median_abs_error_mw: float
    p90_abs_error_mw: float
    p95_abs_error_mw: float
    over_forecast_share_pct: float
    large_error_share_pct: float
    mae_after_bias_removal_mw: float
    error_quantiles_mw: ErrorQuantiles


class Persistence(BaseModel):
    n: int
    persistence_mae_mw: float
    forecast_mae_same_hours_mw: float
    skill_vs_persistence_pct: float


class GroupStats(BaseModel):
    n: int
    bias_mw: float
    mae_mw: float
    rmse_mw: float


class HorizonRow(GroupStats):
    label: str
    lo_hours: int
    hi_hours: int


class HourRow(GroupStats):
    hour: int


class LevelRow(GroupStats):
    label: str
    lo_mw: float | None
    hi_mw: float | None
    error_p10_mw: float
    error_p90_mw: float


class DayRow(GroupStats):
    date: str
    mean_actual_mw: float
    mean_forecast_mw: float


class HistogramBin(BaseModel):
    lo_mw: int
    hi_mw: int
    count: int


class WorstHour(BaseModel):
    start_utc: str
    delivery_date: str
    forecast_mw: float
    actual_mw: float
    error_mw: float
    publish_utc: str


class AccuracyResponse(BaseModel):
    decision_time: str
    first_delivery_date: str
    last_delivery_date: str
    headline: Headline
    persistence: Persistence | None
    by_horizon: list[HorizonRow]
    by_hour: list[HourRow]
    by_level: list[LevelRow]
    by_day: list[DayRow]
    histogram: list[HistogramBin]
    scatter: list[list[float]]
    worst_hours: list[WorstHour]


class DeliveryDay(BaseModel):
    date: str
    decision_date: str
    decision_in_january_2026: bool


class Preset(BaseModel):
    label: str
    time: str


class DataInfo(BaseModel):
    source: str
    fetched_at: str
    snapshot_sha256: str
    actual_half_hours: int
    forecast_publications: int
    forecast_hourly_values: int
    publish_clock_times_utc: dict[str, int]
    units: str


class MetaResponse(BaseModel):
    title: str
    scope_note: str
    delivery_days: list[DeliveryDay]
    default_decision_time: str
    decision_presets: list[Preset]
    data: DataInfo
    assumptions: list[str]
