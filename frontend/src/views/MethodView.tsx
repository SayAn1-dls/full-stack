import type { Meta } from "../types";
import { londonDateTime } from "../format";

const NORD_POOL = "https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-day-ahead-gb-auction";
const EPEX = "https://www.epexspot.com/en";

export function MethodView({ meta }: { meta: Meta }) {
  const d = meta.data;
  return (
    <div className="layout">
      <article className="card prose" style={{ gridColumn: "span 12" }}>
        <h2>What this app answers</h2>
        <p>A day-ahead buyer commits to power the day before delivery, so they need (1) the latest wind forecast they can actually see when the auction closes, and (2) a quantified idea of how wrong that forecast tends to be. The <strong>Decision view</strong> answers the first, the <strong>Forecast accuracy</strong> tab the second.</p>

        <h2>Data and scope</h2>
        <ul>
          <li><strong>Elexon only</strong>, as required: <code>FUELHH</code> (half-hourly generation outturn by fuel, fuel type WIND) and <code>WINDFOR</code> (wind generation forecast: <code>publishTime</code>, <code>startTime</code>, <code>generation</code>). No demand, price or weather data.</li>
          <li>{meta.scope_note}</li>
          <li>Snapshot of the Elexon API taken {londonDateTime(d.fetched_at)} UK time: {d.actual_half_hours.toLocaleString("en-GB")} half-hours of outturn, {d.forecast_publications} forecast runs ({d.forecast_hourly_values.toLocaleString("en-GB")} hourly values). Integrity hash <code>{d.snapshot_sha256.slice(0, 16)}…</code>.</li>
          <li>WINDFOR is published about 8 times a day, at (UTC) {Object.entries(d.publish_clock_times_utc).map(([t, n]) => `${t} (${n} days)`).join(", ")}. One run on 15 January came at 12:25 instead of 11:30. Each run covers hourly targets from roughly a day before to about 2 days after it was issued.</li>
          <li>Units are MW. FUELHH is a half-hour average; WINDFOR gives one value per hour.</li>
        </ul>

        <h2>How "the forecast available at the decision" is chosen</h2>
        <p>The delivery day is D. The decision is taken on D−1 at the cutoff time you pick (UK local time). For every hour of D the app uses the newest WINDFOR run published at or before that cutoff. GB day-ahead auctions close at <strong>09:20</strong> (EPEX GB, ten-twenty CET) and <strong>09:50</strong> (N2EX, Nord Pool), which are the two presets; check the times against your own exchange. Sources: <a href={NORD_POOL} target="_blank" rel="noreferrer">Nord Pool GB day-ahead</a> and <a href={EPEX} target="_blank" rel="noreferrer">EPEX SPOT</a>.</p>

        <h2>How error is measured</h2>
        <ul>
          <li><strong>Error = forecast − outturn.</strong> Positive means the forecast was too high, so wind came in below it, which is the costly side for a buyer.</li>
          <li>A forecast for hour T is compared with the outturn whose start time is T. Comparing with the other half-hour, or with the hour's average, changes the mean absolute error by under 2% on this data, so the choice does not drive the conclusions.</li>
          <li><strong>MAE</strong> is the average size of the miss, <strong>bias</strong> the average signed miss, <strong>RMSE</strong> weights large misses more, <strong>P90 of absolute error</strong> is the miss that one hour in ten exceeds.</li>
          <li><strong>Persistence</strong> is a naive benchmark: hold the newest outturn known at the cutoff flat for the whole day. <strong>Skill</strong> is how much smaller the forecast's MAE is than that.</li>
          <li>The <strong>lead-time</strong> chart uses every forecast run for the chosen days; the other charts use only the run available at your cutoff.</li>
        </ul>

        <h2>The planning band</h2>
        <p>For each hour the band shows where the outturn landed, in other hours of the window, when the forecast was a similar size (forecast levels are split into quartiles; the P10 and P90 of the error in the matching quartile give the band). The day being viewed is left out of its own band. <strong>Wind to count on</strong> is the lower edge: outturn was at or above it in 9 of 10 similar hours.</p>
        <p>This describes how the forecast behaved in this window. It uses information from later days and is not a guarantee about future days.</p>

        <h2>Limits you should know about</h2>
        <ul>
          <li><strong>Wind only.</strong> Without demand there is no "how much to buy", only "how much wind to count on".</li>
          <li><strong>One month.</strong> A winter month is a small sample; the bias may differ in other seasons.</li>
          <li><strong>Why is the forecast high?</strong> This data cannot say. Candidate explanations, which are not tested here: WINDFOR describes wind farms visible to NESO with operational metering and may represent available rather than delivered output, so curtailment would show up as over-forecast; or the two series cover slightly different sets of plants.</li>
          <li><strong>Snapshot, not live.</strong> The figures come from a stored copy of the Elexon data for January 2026. Re-run the ingest to refresh it.</li>
        </ul>
      </article>
    </div>
  );
}
