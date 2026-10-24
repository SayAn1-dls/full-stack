import { describe, expect, it } from "vitest";
import { addDays, axisGW, longDate, minutesLabel, pct, signedGW, signedMW } from "./format";
import { thin } from "./charts/LineChart";

describe("signed formatting", () => {
  it("uses a real minus sign and never prints +0", () => {
    expect(signedMW(1823.4)).toBe("+1,823 MW");
    expect(signedMW(-406)).toBe("−406 MW");
    expect(signedMW(0.2)).toBe("0 MW");
    expect(signedMW(-0.4)).toBe("0 MW");
    expect(signedGW(1823)).toBe("+1.8 GW");
    expect(signedGW(-684)).toBe("−0.7 GW");
  });
});

describe("axis and labels", () => {
  it("drops the decimal for whole GW", () => {
    expect(axisGW(5000)).toBe("5");
    expect(axisGW(2500)).toBe("2.5");
  });
  it("formats percentages and durations", () => {
    expect(pct(15.96)).toBe("16%");
    expect(pct(null)).toBe("n/a");
    expect(minutesLabel(110)).toBe("1 h 50 min");
    expect(minutesLabel(45)).toBe("45 min");
    expect(minutesLabel(120)).toBe("2 h");
  });
});

describe("dates", () => {
  it("never shifts a date-only string across a timezone boundary", () => {
    expect(longDate("2026-01-15")).toBe("Thu, 15 Jan 2026");
    expect(addDays("2026-01-31", 1)).toBe("2026-02-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
  });
});

describe("tick thinning", () => {
  const ticks = [0, 3, 6, 9, 12, 15, 18, 21].map((value) => ({ value }));
  it("keeps all ticks when there is room", () => {
    expect(thin(ticks, (v) => v * 40, 54)).toHaveLength(8);
  });
  it("drops ticks that would overlap on a narrow chart", () => {
    const kept = thin(ticks, (v) => v * 8, 54);   // 24px between ticks, 54px needed
    expect(kept.map((t) => t.value)).toEqual([0, 9, 18]);
  });
});
