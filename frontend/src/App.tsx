import { useEffect, useMemo, useState } from "react";
import { useApi } from "./api";
import { Callout } from "./components";
import { AccuracyView } from "./views/AccuracyView";
import { DecisionView } from "./views/DecisionView";
import { MethodView } from "./views/MethodView";
import type { Meta } from "./types";
import { addDays, londonDateTime } from "./format";

type Tab = "decision" | "accuracy" | "method";
type Theme = "auto" | "light" | "dark";

const DEFAULT_DAY = "2026-01-15";

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  const tab = p.get("tab");
  return {
    tab: (tab === "accuracy" || tab === "method" ? tab : "decision") as Tab,
    date: p.get("date"), time: p.get("time"), from: p.get("from"), to: p.get("to"),
  };
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = window.localStorage.getItem("theme");
      return saved === "light" || saved === "dark" ? saved : "auto";
    } catch {
      return "auto";
    }
  });
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem("theme", theme);
    } catch {
      /* storage unavailable: the choice just will not persist */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "auto" ? "dark" : t === "dark" ? "light" : "auto"))];
}

export default function App() {
  const { data: meta, error } = useApi<Meta>("/api/meta");
  const initial = useMemo(readUrl, []);
  const [tab, setTab] = useState<Tab>(initial.tab);
  const [date, setDate] = useState(initial.date ?? DEFAULT_DAY);
  const [time, setTime] = useState(initial.time ?? "");
  const [from, setFrom] = useState(initial.from ?? "");
  const [to, setTo] = useState(initial.to ?? "");
  const [theme, cycleTheme] = useTheme();

  const first = meta?.delivery_days[0].date ?? "2026-01-01";
  const last = meta?.delivery_days[meta.delivery_days.length - 1].date ?? "2026-02-01";
  const cutoff = /^\d{2}:\d{2}$/.test(time) ? time : meta?.default_decision_time ?? "09:20";
  const rangeFrom = from || first;
  const rangeTo = to || last;

  useEffect(() => {
    const p = new URLSearchParams();
    p.set("tab", tab);
    if (tab === "decision") p.set("date", date);
    if (tab === "accuracy") { p.set("from", rangeFrom); p.set("to", rangeTo); }
    if (tab !== "method") p.set("time", cutoff);
    window.history.replaceState(null, "", `?${p.toString()}`);
  }, [tab, date, cutoff, rangeFrom, rangeTo]);

  if (error) {
    return <div className="app"><div style={{ paddingTop: 40 }}><Callout kind="error"><p><strong>The API is not reachable.</strong></p><p>{error}</p></Callout></div></div>;
  }
  if (!meta) return <div className="app"><p className="hint" role="status" style={{ paddingTop: 40 }}>Loading…</p></div>;

  const tabs: [Tab, string][] = [["decision", "Decision view"], ["accuracy", "Forecast accuracy"], ["method", "Method and limits"]];
  const ranges: [string, string, string][] = [
    ["Whole window", first, last],
    ["Decisions made in January", addDays(first, 1), last],
    ["Last 7 delivery days", addDays(last, -6), last],
  ];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Wind Intelligence</h1>
          <p>Day-ahead wind forecast check · Elexon FUELHH and WINDFOR · decisions made in January 2026</p>
        </div>
        <button type="button" className="icon-btn" onClick={cycleTheme} aria-label={`Colour theme: ${theme}. Click to change.`}>
          Theme: {theme}
        </button>
      </header>

      <nav className="tabs" role="tablist" aria-label="Views">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" role="tab" className="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      {tab !== "method" && (
        <div className="filters" role="group" aria-label="Filters">
          <div className="field">
            <span>Day-ahead decision cutoff (UK time, day before delivery)</span>
            <div className="row">
              <div className="seg" role="group" aria-label="Cutoff presets">
                {meta.decision_presets.map((preset) => (
                  <button key={preset.time} type="button" aria-pressed={cutoff === preset.time} onClick={() => setTime(preset.time)} title={preset.label}>
                    {preset.time} {preset.time === "09:20" ? "EPEX" : "N2EX"}
                  </button>
                ))}
              </div>
              <label className="sr-only" htmlFor="cutoff">Custom cutoff time</label>
              <input id="cutoff" type="time" value={cutoff} onChange={(e) => e.target.value && setTime(e.target.value)} />
            </div>
          </div>

          {tab === "decision" && (
            <div className="field">
              <span>Delivery day</span>
              <div className="row">
                <button type="button" className="icon-btn" aria-label="Previous day" disabled={date <= first} onClick={() => setDate(addDays(date, -1))}>‹</button>
                <label className="sr-only" htmlFor="day">Delivery day</label>
                <input id="day" type="date" min={first} max={last} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
                <button type="button" className="icon-btn" aria-label="Next day" disabled={date >= last} onClick={() => setDate(addDays(date, 1))}>›</button>
              </div>
              <span className="hint">
                {meta.delivery_days.find((d) => d.date === date)?.decision_in_january_2026 === false
                  ? "Decided on 31 December 2025, just outside the January window; shown so all of January is covered."
                  : `Decision taken on ${addDays(date, -1)}.`}
              </span>
            </div>
          )}

          {tab === "accuracy" && (
            <div className="field">
              <span>Delivery days to evaluate</span>
              <div className="row">
                <div className="seg" role="group" aria-label="Range presets">
                  {ranges.map(([label, a, b]) => (
                    <button key={label} type="button" aria-pressed={rangeFrom === a && rangeTo === b} onClick={() => { setFrom(a); setTo(b); }}>{label}</button>
                  ))}
                </div>
                <label className="sr-only" htmlFor="from">From</label>
                <input id="from" type="date" min={first} max={rangeTo} value={rangeFrom} onChange={(e) => e.target.value && setFrom(e.target.value)} />
                <span className="hint">to</span>
                <label className="sr-only" htmlFor="to">To</label>
                <input id="to" type="date" min={rangeFrom} max={last} value={rangeTo} onChange={(e) => e.target.value && setTo(e.target.value)} />
              </div>
            </div>
          )}
        </div>
      )}

      <main>
        {tab === "decision" && <DecisionView date={date} time={cutoff} />}
        {tab === "accuracy" && <AccuracyView from={rangeFrom} to={rangeTo} time={cutoff} />}
        {tab === "method" && <MethodView meta={meta} />}
      </main>

      <footer className="footer">
        <span>Data: {meta.data.source}, snapshot of {londonDateTime(meta.data.fetched_at)} UK time</span>
        <span>{meta.data.forecast_publications} WINDFOR runs · {meta.data.actual_half_hours.toLocaleString("en-GB")} FUELHH half-hours</span>
        <span>Hash {meta.data.snapshot_sha256.slice(0, 12)}</span>
        <a href="/api/docs">API docs</a>
      </footer>
    </div>
  );
}
