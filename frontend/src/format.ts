const LONDON = "Europe/London";

export const MW = (value: number): string => `${Math.round(value).toLocaleString("en-GB")} MW`;

export const GW = (valueMw: number, digits = 1): string => `${(valueMw / 1000).toFixed(digits)} GW`;

export const signedGW = (valueMw: number, digits = 1): string => {
  const text = (Math.abs(valueMw) / 1000).toFixed(digits);
  return `${valueMw < 0 ? "−" : "+"}${text} GW`;
};

export const signedMW = (valueMw: number): string => {
  const rounded = Math.round(valueMw);
  if (rounded === 0) return "0 MW";
  return `${rounded < 0 ? "−" : "+"}${Math.abs(rounded).toLocaleString("en-GB")} MW`;
};

export const pct = (value: number | null, digits = 0): string => (value === null ? "n/a" : `${value.toFixed(digits)}%`);

/** Axis tick: whole GW when possible. */
export const axisGW = (valueMw: number): string => {
  const gw = valueMw / 1000;
  return `${Number.isInteger(gw) ? gw : gw.toFixed(1)}`;
};

/** "Thu 15 Jan 2026" from "2026-01-15" (date-only strings are read as UTC so the day can never shift). */
export function longDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

export function shortDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** UK wall-clock time of an instant, correct across clock changes. */
export function londonTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: LONDON });
}

export function londonDateTime(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: LONDON });
  return `${day} ${londonTime(iso)}`;
}

export function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function minutesLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
