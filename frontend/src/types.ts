// Mirrors backend/app/wind/schemas.py. All power values are MW; error = forecast - outturn (positive = forecast too high).

export interface HourPoint {
  start_utc: string;
  start_local: string;
  forecast_mw: number;
  publish_utc: string;
  horizon_hours: number;
  actual_mw: number | null;
  error_mw: number | null;
  p10_mw: number;
  p50_mw: number;
  p90_mw: number;
}

export interface EvolutionEntry {
  publish_utc: string;
  publish_local: string;
  status: "used" | "earlier" | "after_cutoff";
  values: (number | null)[];
  mean_forecast_mw: number;
  hours_covered: number;
  delta_vs_decision_mw: number;
}

export interface DaySummary {
  mean_forecast_mw: number;
  peak_forecast_mw: number;
  peak_forecast_hour: string;
  min_forecast_mw: number;
  min_forecast_hour: string;
  mean_p10_floor_mw: number;
  mean_p50_expected_mw: number;
  mean_p90_ceiling_mw: number;
  mean_buffer_mw: number;
  mean_actual_mw: number | null;
  mean_error_mw: number | null;
  mae_mw: number | null;
  hours_over_forecast: number;
  hours_with_actual: number;
  outturn_inside_band_hours: number;
}

export interface Decision {
  delivery_date: string;
  decision_date: string;
  decision_time: string;
  cutoff_utc: string;
  cutoff_local: string;
  used_publication: { publish_utc: string; publish_local: string; age_at_cutoff_minutes: number; hours_covered: number };
  hours: HourPoint[];
  hours_without_forecast: string[];
  actual_half_hourly: { start_utc: string; actual_mw: number }[];
  summary: DaySummary;
  evolution: EvolutionEntry[];
  error_model: {
    built_from_days: number;
    buckets: { lo_mw: number | null; hi_mw: number | null; n: number; error_p10_mw: number; error_p50_mw: number; error_p90_mw: number }[];
  };
}

export interface GroupStats {
  n: number;
  bias_mw: number;
  mae_mw: number;
  rmse_mw: number;
}

export interface Accuracy {
  decision_time: string;
  first_delivery_date: string;
  last_delivery_date: string;
  headline: {
    n: number;
    days: number;
    over_forecast_days: number;
    mean_actual_mw: number;
    mean_forecast_mw: number;
    bias_mw: number;
    bias_pct_of_actual: number | null;
    mae_mw: number;
    rmse_mw: number;
    wape_pct: number | null;
    median_abs_error_mw: number;
    p90_abs_error_mw: number;
    p95_abs_error_mw: number;
    over_forecast_share_pct: number;
    large_error_share_pct: number;
    mae_after_bias_removal_mw: number;
    error_quantiles_mw: { p5: number; p10: number; p50: number; p90: number; p95: number };
  };
  persistence: { n: number; persistence_mae_mw: number; forecast_mae_same_hours_mw: number; skill_vs_persistence_pct: number } | null;
  by_horizon: (GroupStats & { label: string; lo_hours: number; hi_hours: number })[];
  by_hour: (GroupStats & { hour: number })[];
  by_level: (GroupStats & { label: string; lo_mw: number | null; hi_mw: number | null; error_p10_mw: number; error_p90_mw: number })[];
  by_day: (GroupStats & { date: string; mean_actual_mw: number; mean_forecast_mw: number })[];
  histogram: { lo_mw: number; hi_mw: number; count: number }[];
  scatter: [number, number][];
  worst_hours: { start_utc: string; delivery_date: string; forecast_mw: number; actual_mw: number; error_mw: number; publish_utc: string }[];
}

export interface Meta {
  title: string;
  scope_note: string;
  delivery_days: { date: string; decision_date: string; decision_in_january_2026: boolean }[];
  default_decision_time: string;
  decision_presets: { label: string; time: string }[];
  data: {
    source: string;
    fetched_at: string;
    snapshot_sha256: string;
    actual_half_hours: number;
    forecast_publications: number;
    forecast_hourly_values: number;
    publish_clock_times_utc: Record<string, number>;
    units: string;
  };
  assumptions: string[];
}
