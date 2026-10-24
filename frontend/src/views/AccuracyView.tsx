import { useMemo } from "react";
import { useApi } from "../api";
import { Callout, Hero, Tile } from "../components";
import { BarChart } from "../charts/BarChart";
import { ChartCard, DataTable } from "../charts/ChartCard";
import { Histogram } from "../charts/Histogram";
import { LineChart } from "../charts/LineChart";
import { ScatterChart } from "../charts/ScatterChart";
import { niceDomain } from "../charts/scales";
import type { Accuracy } from "../types";
import { GW, MW, axisGW, londonTime, pct, shortDate, signedGW, signedMW } from "../format";

const signedAxis = (mw: number): string => (mw === 0 ? "0" : `${mw > 0 ? "+" : "−"}${Math.abs(mw / 1000)}`);
const OVER = "var(--over)";
const UNDER = "var(--under)";

export function AccuracyView({ from, to, time }: { from: string; to: string; time: string }) {
  const { data, error, loading } = useApi<Accuracy>(`/api/accuracy?start=${from}&end=${to}&decision_time=${time}`);
  const model = useMemo(() => (data ? buildHourLines(data) : null), [data]);
  const bins = useMemo(() => (data ? data.histogram.map((b) => ({ lo: b.lo_mw, hi: b.hi_mw, count: b.count })) : []), [data]);

  if (error) return <Callout kind="error"><p><strong>No accuracy figures for this selection.</strong></p><p>{error}</p></Callout>;
  if (!data || !model) return <p className="hint" role="status">Calculating forecast error…</p>;

  const h = data.headline;
  const high = h.bias_mw >= 0;
  const dimmed = loading;
  const errorKey = [
    { label: "Over-forecast: outturn below the forecast", color: OVER, kind: "rect" as const },
    { label: "Under-forecast: outturn above the forecast", color: UNDER, kind: "rect" as const },
  ];
  const metricKey = [
    { label: "Mean absolute error", color: "var(--s1)", kind: "rect" as const },
    { label: "Bias (forecast − outturn)", color: "var(--s2)", kind: "rect" as const },
  ];
  const metricLineKey = metricKey.map((m) => ({ ...m, kind: "line" as const }));

  return (
    <div className="layout">
      <section className="card" style={{ gridColumn: "span 12" }} aria-label="Summary">
        <Hero
          value={signedGW(h.bias_mw).replace(" GW", "")}
          unit={high ? "GW average over-forecast" : "GW average under-forecast"}
          caption={<>The forecast available at <strong>{data.decision_time}</strong> on the day before was on average <strong>{GW(Math.abs(h.bias_mw))}</strong> ({pct(Math.abs(h.bias_pct_of_actual ?? 0))} of mean outturn) {high ? "above" : "below"} what wind delivered. It was too high in <strong>{pct(h.over_forecast_share_pct)}</strong> of the {h.n.toLocaleString("en-GB")} hours and on <strong>{h.over_forecast_days} of {h.days}</strong> delivery days.</>}
        >
          <div className="tiles three">
            <Tile label="Typical miss (MAE)" value={GW(h.mae_mw)} sub={`${pct(h.wape_pct)} of mean outturn (${GW(h.mean_actual_mw)})`} />
            <Tile label="Big miss (P90 of |error|)" value={GW(h.p90_abs_error_mw)} sub="one hour in ten is off by more than this" />
            <Tile label="Hours off by 2 GW or more" value={pct(h.large_error_share_pct)} sub={`RMSE ${GW(h.rmse_mw)}`} />
            <Tile label="Error range, 9 hours in 10" value={`${signedGW(h.error_quantiles_mw.p5).replace(" GW", "")} to ${signedGW(h.error_quantiles_mw.p95)}`} sub="P5 to P95 of forecast − outturn" />
            <Tile label="MAE if the bias were removed" value={GW(h.mae_after_bias_removal_mw)} sub="in-sample: shows how much of the error is systematic" />
            {data.persistence && (
              <Tile label="Skill vs naive persistence" value={`${data.persistence.skill_vs_persistence_pct.toFixed(0)}%`} sub={`MAE ${GW(data.persistence.forecast_mae_same_hours_mw)} vs ${GW(data.persistence.persistence_mae_mw)} holding the last known outturn flat`} />
            )}
          </div>
        </Hero>
      </section>

      <div className="half">
        <ChartCard
          title="How wrong, and in which direction"
          subtitle={<>Distribution of forecast − outturn for every hour. {pct(h.over_forecast_share_pct)} of hours sit right of zero, where the forecast was too high.</>}
          legend={errorKey}
          dimmed={dimmed}
          table={{ columns: ["Error from (MW)", "Error to (MW)", "Hours"], rows: data.histogram.map((b) => [b.lo_mw, b.hi_mw, b.count]) }}
        >
          <Histogram
            bins={bins}
            total={h.n}
            xFormat={signedAxis}
            colorFor={(bin) => (bin.lo >= 0 ? OVER : UNDER)}
            refLines={[
              { value: h.error_quantiles_mw.p10, label: `P10 ${signedGW(h.error_quantiles_mw.p10)}` },
              { value: h.error_quantiles_mw.p50, label: `median ${signedGW(h.error_quantiles_mw.p50)}` },
              { value: h.error_quantiles_mw.p90, label: `P90 ${signedGW(h.error_quantiles_mw.p90)}` },
            ]}
            tooltip={(bin) => ({
              title: `${signedGW(bin.lo)} to ${signedGW(bin.hi)}`,
              rows: [{ label: "hours", value: `${bin.count}`, color: bin.lo >= 0 ? OVER : UNDER, kind: "bar" }, { label: "share of all hours", value: pct(100 * bin.count / h.n, 1) }],
            })}
            ariaLabel="Histogram of forecast error in GW"
          />
        </ChartCard>
      </div>

      <div className="half">
        <ChartCard
          title="Error by lead time"
          subtitle="Across every WINDFOR run for the selected days. A day-ahead decision sits at roughly 16 to 40 hours ahead. Bias stays large even close to delivery."
          legend={metricKey}
          dimmed={dimmed}
          table={{ columns: ["Lead time", "Hours compared", "MAE MW", "Bias MW", "RMSE MW"], rows: data.by_horizon.map((r) => [r.label, r.n, Math.round(r.mae_mw), Math.round(r.bias_mw), Math.round(r.rmse_mw)]) }}
        >
          <BarChart
            categories={data.by_horizon.map((r) => ({ label: r.label.replace("-", "–") }))}
            series={[{ id: "mae", color: "var(--s1)", values: data.by_horizon.map((r) => r.mae_mw) }, { id: "bias", color: "var(--s2)", values: data.by_horizon.map((r) => r.bias_mw) }]}
            yFormat={axisGW}
            yUnit="GW"
            tooltip={(i) => {
              const r = data.by_horizon[i];
              return { title: `${r.label.replace("-", " to ")} ahead`, rows: [{ label: "mean absolute error", value: MW(r.mae_mw), color: "var(--s1)", kind: "bar" }, { label: "bias", value: signedMW(r.bias_mw), color: "var(--s2)", kind: "bar" }, { label: "RMSE", value: MW(r.rmse_mw) }], footnote: `${r.n.toLocaleString("en-GB")} forecast/outturn pairs` };
            }}
            ariaLabel="Mean absolute error and bias by forecast lead time"
          />
        </ChartCard>
      </div>

      <div className="half">
        <ChartCard
          title="Error by hour of day"
          subtitle="Decision-time forecast, by UK hour of the delivery day."
          legend={metricLineKey}
          dimmed={dimmed}
          table={{ columns: ["Hour (UK)", "Hours compared", "MAE MW", "Bias MW"], rows: data.by_hour.map((r) => [`${String(r.hour).padStart(2, "0")}:00`, r.n, Math.round(r.mae_mw), Math.round(r.bias_mw)]) }}
        >
          <LineChart
            series={[{ id: "mae", color: "var(--s1)", points: model.mae }, { id: "bias", color: "var(--s2)", points: model.bias }]}
            xDomain={[0, 23]}
            xTicks={[0, 3, 6, 9, 12, 15, 18, 21].map((v) => ({ value: v, label: `${String(v).padStart(2, "0")}:00` }))}
            yFormat={axisGW}
            yUnit="GW"
            yDomain={model.yDomain}
            snapXs={model.xs}
            height={300}
            endLabels={[{ seriesId: "mae", text: "MAE" }, { seriesId: "bias", text: "Bias" }]}
            ariaLabel="Mean absolute error and bias by hour of day"
            tooltip={(x) => {
              const r = data.by_hour.find((row) => row.hour === x);
              if (!r) return null;
              return { title: `${String(r.hour).padStart(2, "0")}:00 UK`, rows: [{ label: "mean absolute error", value: MW(r.mae_mw), color: "var(--s1)" }, { label: "bias", value: signedMW(r.bias_mw), color: "var(--s2)" }], footnote: `${r.n} hours compared` };
            }}
          />
        </ChartCard>
      </div>

      <div className="half">
        <ChartCard
          title="Error by forecast size"
          subtitle="Forecasts in the top quartile are over-forecast by far the most. Forecast levels are split into quartiles of the selected hours."
          legend={metricKey}
          dimmed={dimmed}
          table={{ columns: ["Forecast level", "Hours", "MAE MW", "Bias MW", "Error P10 MW", "Error P90 MW"], rows: data.by_level.map((r) => [r.label, r.n, Math.round(r.mae_mw), Math.round(r.bias_mw), Math.round(r.error_p10_mw), Math.round(r.error_p90_mw)]) }}
        >
          <BarChart
            categories={data.by_level.map((r) => ({ label: r.label.replace(" to ", "–").replace(" GW and above", " GW or more").replace("below ", "under ") }))}
            series={[{ id: "mae", color: "var(--s1)", values: data.by_level.map((r) => r.mae_mw) }, { id: "bias", color: "var(--s2)", values: data.by_level.map((r) => r.bias_mw) }]}
            yFormat={axisGW}
            yUnit="GW"
            tooltip={(i) => {
              const r = data.by_level[i];
              return { title: `Forecast ${r.label}`, rows: [{ label: "mean absolute error", value: MW(r.mae_mw), color: "var(--s1)", kind: "bar" }, { label: "bias", value: signedMW(r.bias_mw), color: "var(--s2)", kind: "bar" }, { label: "error P10 to P90", value: `${signedMW(r.error_p10_mw)} to ${signedMW(r.error_p90_mw)}` }], footnote: `${r.n} hours` };
            }}
            ariaLabel="Mean absolute error and bias by forecast size"
          />
        </ChartCard>
      </div>

      <div style={{ gridColumn: "span 12" }}>
        <ChartCard
          title="Day by day"
          subtitle="Average error of each delivery day's decision-time forecast. Red days are over-forecast days."
          legend={errorKey}
          dimmed={dimmed}
          wide
          table={{ columns: ["Delivery day", "Hours", "Mean forecast MW", "Mean outturn MW", "Bias MW", "MAE MW"], rows: data.by_day.map((r) => [r.date, r.n, Math.round(r.mean_forecast_mw), Math.round(r.mean_actual_mw), Math.round(r.bias_mw), Math.round(r.mae_mw)]) }}
        >
          <BarChart
            categories={data.by_day.map((r) => ({ label: shortDate(r.date) }))}
            series={[{ id: "bias", color: OVER, values: data.by_day.map((r) => r.bias_mw) }]}
            colorFor={(_, __, value) => (value >= 0 ? OVER : UNDER)}
            yFormat={signedAxis}
            yUnit="GW"
            height={260}
            tooltip={(i) => {
              const r = data.by_day[i];
              return { title: shortDate(r.date), rows: [{ label: "average error", value: signedMW(r.bias_mw), color: r.bias_mw >= 0 ? OVER : UNDER, kind: "bar" }, { label: "mean absolute error", value: MW(r.mae_mw) }, { label: "mean forecast", value: MW(r.mean_forecast_mw) }, { label: "mean outturn", value: MW(r.mean_actual_mw) }] };
            }}
            ariaLabel="Average forecast error for each delivery day"
          />
        </ChartCard>
      </div>

      <div className="half">
        <ChartCard
          title="Forecast against outturn"
          subtitle="One dot per hour. Dots below the diagonal were over-forecast."
          dimmed={dimmed}
          table={{ columns: ["Forecast MW", "Outturn MW", "Error MW"], rows: data.scatter.map(([f, a]) => [Math.round(f), Math.round(a), Math.round(f - a)]) }}
        >
          <ScatterChart
            points={data.scatter}
            color="var(--s1)"
            axisFormat={axisGW}
            xLabel="Forecast available at the cutoff (GW)"
            yLabel="Outturn (GW)"
            diagonalLabel="forecast = outturn"
            tooltip={(i) => {
              const [f, a] = data.scatter[i];
              return { title: "One hour", rows: [{ label: "forecast", value: MW(f), color: "var(--s1)", kind: "dot" }, { label: "outturn", value: MW(a) }, { label: "error", value: signedMW(f - a) }] };
            }}
            ariaLabel="Scatter of forecast against outturn"
          />
        </ChartCard>
      </div>

      <section className="card half" aria-label="Worst hours">
        <h2>The ten biggest misses</h2>
        <p className="subtitle" style={{ marginBottom: 10 }}>Largest absolute errors of the decision-time forecast.</p>
        <DataTable
          spec={{
            columns: ["Delivery day", "Hour (UK)", "Forecast MW", "Outturn MW", "Error MW"],
            rows: data.worst_hours.map((r) => [shortDate(r.delivery_date), londonTime(r.start_utc), Math.round(r.forecast_mw), Math.round(r.actual_mw), signedMW(r.error_mw)]),
          }}
        />
      </section>
    </div>
  );
}

function buildHourLines(data: Accuracy) {
  const xs = data.by_hour.map((r) => r.hour);
  const mae = data.by_hour.map((r) => ({ x: r.hour, y: r.mae_mw as number | null }));
  const bias = data.by_hour.map((r) => ({ x: r.hour, y: r.bias_mw as number | null }));
  const values = data.by_hour.flatMap((r) => [r.mae_mw, r.bias_mw]);
  const yDomain = niceDomain(Math.min(0, Math.min(...values) * 1.1), Math.max(...values) * 1.08, 5);
  return { xs, mae, bias, yDomain };
}
