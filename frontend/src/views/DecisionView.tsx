import { useMemo, useState } from "react";
import { useApi } from "../api";
import { Callout, Hero, SectionLabel, Tile } from "../components";
import { ChartCard, DataTable } from "../charts/ChartCard";
import { LineChart, type LineSeries } from "../charts/LineChart";
import type { Decision } from "../types";
import { GW, MW, axisGW, londonDateTime, londonTime, longDate, minutesLabel, signedGW, signedMW } from "../format";

const HOUR_MS = 3_600_000;

export function DecisionView({ date, time }: { date: string; time: string }) {
  const { data, error, loading } = useApi<Decision>(`/api/decision?delivery_date=${date}&decision_time=${time}`);
  const [showOthers, setShowOthers] = useState(false);

  const model = useMemo(() => (data ? buildChartModel(data) : null), [data]);

  if (error) {
    return <Callout kind="error"><p><strong>No forecast view for this selection.</strong></p><p>{error}</p></Callout>;
  }
  if (!data || !model) return <p className="hint" role="status">Loading the forecast available at the cutoff…</p>;

  const s = data.summary;
  const pub = data.used_publication;
  const dimmed = loading;
  const hindsight = s.mean_actual_mw !== null && s.mean_error_mw !== null;

  const series: LineSeries[] = [
    ...(showOthers
      ? model.others.map((o) => ({ id: `rev-${o.publish_utc}`, color: "var(--muted-series)", muted: true, points: o.points }))
      : []),
    { id: "outturn", color: "var(--s2)", points: model.outturn },
    { id: "forecast", color: "var(--s1)", points: model.forecast, markers: true },
  ];

  return (
    <div className="layout">
      <section className="card" style={{ gridColumn: "span 12" }} aria-label="Summary">
        <Hero
          value={(s.mean_forecast_mw / 1000).toFixed(1)}
          unit="GW average forecast"
          caption={<>For delivery on <strong>{longDate(data.delivery_date)}</strong>, using what had been published by <strong>{data.decision_time}</strong> UK time on {longDate(data.decision_date)}.</>}
        >
          <div className="stack">
            <div>
              <SectionLabel chip={<span className="chip"><i style={{ background: "var(--s1)" }} />Known at the decision</span>}>Plan with</SectionLabel>
              <div className="tiles">
                <Tile label="Peak forecast" value={GW(s.peak_forecast_mw)} sub={`at ${s.peak_forecast_hour}`} />
                <Tile label="Lowest forecast" value={GW(s.min_forecast_mw)} sub={`at ${s.min_forecast_hour}`} />
                <Tile label="Wind to count on" value={GW(s.mean_p10_floor_mw)} sub={<>average P90 floor: outturn was at or above it in 9 of 10 similar hours. That is <strong>{GW(s.mean_buffer_mw)}</strong> below the forecast.</>} />
              </div>
            </div>
            {hindsight && (
              <div>
                <SectionLabel chip={<span className="chip"><i style={{ background: "var(--s2)" }} />In hindsight</span>}>How it turned out</SectionLabel>
                <div className="tiles">
                  <Tile label="Outturn averaged" value={GW(s.mean_actual_mw as number)} sub="FUELHH wind, hours where the forecast applies" />
                  <Tile label="Forecast error" value={signedGW(s.mean_error_mw as number)} sub={(s.mean_error_mw as number) >= 0 ? "forecast was too high (wind came in lower)" : "forecast was too low (wind beat it)"} />
                  <Tile label="Hours over-forecast" value={`${s.hours_over_forecast} of ${s.hours_with_actual}`} sub={`${s.outturn_inside_band_hours} of ${s.hours_with_actual} inside the P10–P90 band`} />
                </div>
              </div>
            )}
          </div>
        </Hero>
      </section>

      {data.hours_without_forecast.length > 0 && (
        <div style={{ gridColumn: "span 12" }}>
          <Callout>
            <p><strong>No forecast covered {data.hours_without_forecast.join(", ")} at this cutoff.</strong></p>
            <p>The newest run published by {data.decision_time} only looks about 46 to 66 hours ahead, depending on when it was issued, so the last hour(s) of the day had no forecast yet. Those hours are left blank, not estimated.</p>
          </Callout>
        </div>
      )}

      <div style={{ gridColumn: "span 12" }}>
        <ChartCard
          title="Forecast held at the decision, against what wind delivered"
          subtitle={<>Latest WINDFOR run at the cutoff: published <strong>{londonDateTime(pub.publish_utc)}</strong>, {minutesLabel(pub.age_at_cutoff_minutes)} before the {data.decision_time} cutoff, covering {pub.hours_covered} of {data.hours.length + data.hours_without_forecast.length} hours. Hover or use the arrow keys to read values.</>}
          legend={[
            { label: "Forecast available at the cutoff (hourly)", color: "var(--s1)", kind: "line" },
            { label: "Outturn, FUELHH wind (half-hourly)", color: "var(--s2)", kind: "line" },
            { label: "Plausible outturn, P10–P90 of past error", color: "var(--s2)", kind: "band" },
            ...(showOthers ? [{ label: "Other WINDFOR runs", color: "var(--muted-series)", kind: "line" as const }] : []),
          ]}
          table={{
            columns: ["Hour (UK)", "Forecast MW", "Outturn MW (first half-hour)", "Error MW", "P10 MW", "P50 MW", "P90 MW", "Run used (UTC)"],
            rows: data.hours.map((h) => [h.start_local, Math.round(h.forecast_mw), h.actual_mw === null ? "n/a" : Math.round(h.actual_mw), h.error_mw === null ? "n/a" : Math.round(h.error_mw), Math.round(h.p10_mw), Math.round(h.p50_mw), Math.round(h.p90_mw), h.publish_utc.replace("T", " ").replace(":00Z", "")]),
          }}
          dimmed={dimmed}
          wide
          footnote={<>
            <label style={{ display: "inline-flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
              <input type="checkbox" checked={showOthers} onChange={(e) => setShowOthers(e.target.checked)} />
              Show the other forecast runs for this day (earlier and later), to see how the forecast moved
            </label>
          </>}
        >
          <LineChart
            series={series}
            bands={[{ id: "band", color: "var(--s2)", points: model.band }]}
            xDomain={[0, model.span]}
            xTicks={model.ticks}
            yFormat={axisGW}
            yUnit="GW"
            snapXs={model.snapXs}
            endLabels={[{ seriesId: "forecast", text: "Forecast" }, { seriesId: "outturn", text: "Outturn" }]}
            ariaLabel={`Forecast available at ${data.decision_time} on ${data.decision_date} and outturn for ${data.delivery_date}`}
            tooltip={(x) => model.tooltipAt(x)}
          />
        </ChartCard>
      </div>

      <section className="card half" aria-label="How to read this">
        <h2>Reading this for a buy decision</h2>
        <div className="prose">
          <ul>
            <li><strong>Blue line</strong> is the forecast you can actually see when the day-ahead auction closes. Later runs (grey, if shown) are not available yet.</li>
            <li><strong>Orange band</strong> is where outturn landed in similar past hours (forecasts of a similar size, all other January days). Wind to count on is its lower edge.</li>
            <li>The forecast is <strong>usually too high</strong> in this data: see the Forecast accuracy tab for the size of that bias, by lead time, hour and forecast level.</li>
            <li>This app sees wind only. It has no demand or price data, so it cannot say how much to buy, only how much wind to count on.</li>
          </ul>
        </div>
      </section>

      <section className="card half" aria-label="Forecast runs">
        <h2>Forecast runs for this delivery day</h2>
        <p className="subtitle" style={{ marginBottom: 10 }}>Elexon publishes about 8 runs a day. Several consecutive runs are often identical for the next day.</p>
        <DataTable
          spec={{
            columns: ["Published (UK)", "Status", "Mean forecast MW", "Δ vs used MW"],
            rows: data.evolution.map((e) => [
              londonDateTime(e.publish_utc),
              e.status === "used" ? "Used at the cutoff" : e.status === "after_cutoff" ? "After the cutoff" : "Earlier",
              Math.round(e.mean_forecast_mw),
              e.status === "used" ? "0" : signedMW(e.delta_vs_decision_mw),
            ]),
          }}
        />
      </section>
    </div>
  );
}

interface ChartModel {
  forecast: { x: number; y: number | null }[];
  outturn: { x: number; y: number | null }[];
  band: { x: number; lo: number; hi: number }[];
  others: { publish_utc: string; points: { x: number; y: number | null }[] }[];
  span: number;
  ticks: { value: number; label: string }[];
  snapXs: number[];
  tooltipAt: (x: number) => { title: string; rows: { label: string; value: string; color?: string; kind?: "line" | "band" }[]; footnote?: string } | null;
}

function buildChartModel(data: Decision): ChartModel {
  const starts = [...data.hours.map((h) => Date.parse(h.start_utc)), ...data.actual_half_hourly.map((a) => Date.parse(a.start_utc))];
  const dayStart = Math.min(...starts);
  const xOf = (iso: string) => (Date.parse(iso) - dayStart) / HOUR_MS;
  const span = Math.ceil(Math.max(...starts.map((t) => (t - dayStart) / HOUR_MS)) + 0.5);
  const forecast = data.hours.map((h) => ({ x: xOf(h.start_utc), y: h.forecast_mw }));
  const outturn = data.actual_half_hourly.map((a) => ({ x: xOf(a.start_utc), y: a.actual_mw }));
  const band = data.hours.map((h) => ({ x: xOf(h.start_utc), lo: h.p10_mw, hi: h.p90_mw }));
  const others = data.evolution.filter((e) => e.status !== "used").map((e) => ({
    publish_utc: e.publish_utc,
    points: e.values.map((v, i) => ({ x: i, y: v })),
  }));
  const step = span > 12 ? 3 : 1;
  const ticks = [];
  for (let h = 0; h <= span; h += step) ticks.push({ value: h, label: londonTime(new Date(dayStart + h * HOUR_MS).toISOString()) });
  const snapXs = forecast.map((p) => p.x);
  const byX = new Map(data.hours.map((h) => [xOf(h.start_utc), h]));
  const halfByX = new Map(data.actual_half_hourly.map((a) => [xOf(a.start_utc), a.actual_mw]));
  const tooltipAt = (x: number) => {
    const h = byX.get(x);
    if (!h) return null;
    const second = halfByX.get(x + 0.5);
    const first = halfByX.get(x);
    const rows: { label: string; value: string; color?: string; kind?: "line" | "band" }[] = [
      { label: "forecast at the cutoff", value: MW(h.forecast_mw), color: "var(--s1)" },
    ];
    if (first !== undefined) rows.push({ label: `outturn ${h.start_local}–${addMinutes(h.start_local, 30)}`, value: MW(first), color: "var(--s2)" });
    if (second !== undefined) rows.push({ label: `outturn ${addMinutes(h.start_local, 30)}–${addMinutes(h.start_local, 60)}`, value: MW(second), color: "var(--s2)" });
    if (h.error_mw !== null) rows.push({ label: "error (forecast − outturn)", value: signedMW(h.error_mw) });
    rows.push({ label: "plausible outturn P10–P90", value: `${MW(h.p10_mw)} to ${MW(h.p90_mw)}`, color: "var(--s2)", kind: "band" });
    return { title: `${h.start_local} UK time`, rows, footnote: `Horizon ${h.horizon_hours.toFixed(1)} h from the run used` };
  };
  return { forecast, outturn, band, others, span, ticks, snapXs, tooltipAt };
}

function addMinutes(hhmm: string, minutes: number): string {
  const [h, m] = hhmm.split(":").map(Number);
  const total = h * 60 + m + minutes;
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
