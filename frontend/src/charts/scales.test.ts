import { describe, expect, it } from "vitest";
import { barPath, invert, linear, nearestIndex, niceDomain, niceStep, niceTicks } from "./scales";

describe("niceTicks", () => {
  it("returns round numbers inside the range", () => {
    expect(niceTicks(0, 20000, 5)).toEqual([0, 5000, 10000, 15000, 20000]);
    expect(niceTicks(0, 1, 5)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(niceTicks(-1500, 4500, 6)).toEqual([-1000, 0, 1000, 2000, 3000, 4000]);
  });
  it("has no floating point noise", () => {
    for (const tick of niceTicks(0, 0.7, 7)) expect(String(tick).length).toBeLessThan(6);
  });
  it("copes with a degenerate range", () => {
    expect(niceTicks(5, 5)).toEqual([5]);
  });
});

describe("niceDomain", () => {
  it("covers the data and snaps to the tick step", () => {
    expect(niceDomain(0, 17805, 5)).toEqual([0, 20000]);
    expect(niceDomain(-684, 5329, 5)).toEqual([-2000, 6000]);
  });
  it("widens a zero-width domain", () => {
    expect(niceDomain(3, 3)).toEqual([2, 4]);
  });
});

describe("niceStep", () => {
  it("picks 1, 2, 5 times a power of ten", () => {
    expect(niceStep(10, 5)).toBe(2);
    expect(niceStep(100, 4)).toBe(50);
    expect(niceStep(0.9, 5)).toBe(0.2);
  });
});

describe("linear / invert", () => {
  it("maps and inverts", () => {
    const scale = linear([0, 10], [100, 300]);
    expect(scale(0)).toBe(100);
    expect(scale(10)).toBe(300);
    expect(scale(5)).toBe(200);
    expect(invert([0, 10], [100, 300])(250)).toBe(7.5);
  });
  it("supports inverted ranges (y axes)", () => {
    expect(linear([0, 100], [200, 0])(25)).toBe(150);
  });
  it("does not divide by zero", () => {
    expect(linear([4, 4], [0, 10])(4)).toBe(0);
  });
});

describe("nearestIndex", () => {
  const xs = [0, 1, 2, 3, 10];
  it("finds the closest value", () => {
    expect(nearestIndex(xs, -5)).toBe(0);
    expect(nearestIndex(xs, 1.4)).toBe(1);
    expect(nearestIndex(xs, 1.6)).toBe(2);
    expect(nearestIndex(xs, 6)).toBe(3);
    expect(nearestIndex(xs, 7)).toBe(4);
    expect(nearestIndex(xs, 99)).toBe(4);
  });
  it("breaks ties towards the earlier point and handles empty input", () => {
    expect(nearestIndex([0, 2], 1)).toBe(0);
    expect(nearestIndex([], 1)).toBe(-1);
  });
});

describe("barPath", () => {
  it("is empty for a zero-height bar and rounds only the data end", () => {
    expect(barPath(0, 100, 100, 20)).toBe("");
    const up = barPath(10, 100, 40, 20);
    expect(up.startsWith("M10,100V44")).toBe(true);   // square at the baseline, rounded at the top (y=40, r=4)
    const down = barPath(10, 100, 160, 20);
    expect(down.startsWith("M10,100V156")).toBe(true); // rounded at the bottom end
  });
  it("shrinks the radius for very thin bars", () => {
    expect(barPath(0, 100, 99, 20)).toContain("Q0,99");
  });
});
