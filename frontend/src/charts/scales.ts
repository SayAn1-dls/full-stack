/** Small scale helpers for the SVG charts (no charting library). */

export function niceStep(span: number, target: number): number {
  const raw = span / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const fraction = raw / power;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * power;
}

const clean = (value: number): number => Math.round(value * 1e9) / 1e9;

export function niceTicks(min: number, max: number, target = 5): number[] {
  if (!(max > min)) return [clean(min)];
  const step = niceStep(max - min, target);
  const first = Math.ceil(clean(min / step));
  const last = Math.floor(clean(max / step));
  const ticks: number[] = [];
  for (let i = first; i <= last; i++) ticks.push(clean(i * step));
  return ticks;
}

export function niceDomain(min: number, max: number, target = 5): [number, number] {
  if (!(max > min)) return [min - 1, max + 1];
  const step = niceStep(max - min, target);
  return [clean(Math.floor(clean(min / step)) * step), clean(Math.ceil(clean(max / step)) * step)];
}

export function linear(domain: [number, number], range: [number, number]): (value: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const scale = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (value) => r0 + (value - d0) * scale;
}

export function invert(domain: [number, number], range: [number, number]): (pixel: number) => number {
  return linear(range, domain);
}

/** Index of the value in a sorted array closest to `target`. */
export function nearestIndex(sorted: number[], target: number): number {
  if (sorted.length === 0) return -1;
  let low = 0;
  let high = sorted.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (sorted[mid] < target) low = mid + 1;
    else high = mid;
  }
  if (low > 0 && Math.abs(sorted[low - 1] - target) <= Math.abs(sorted[low] - target)) return low - 1;
  return low;
}

/** A path for a bar with a 4px rounded data end and a square baseline end (vertical bars, either sign). */
export function barPath(x: number, baselineY: number, valueY: number, width: number, radius = 4): string {
  const height = Math.abs(valueY - baselineY);
  if (height < 0.5) return "";
  const r = Math.min(radius, width / 2, height);
  const up = valueY < baselineY;
  const top = up ? valueY : baselineY;
  const bottom = up ? baselineY : valueY;
  const x2 = x + width;
  return up
    ? `M${x},${bottom}V${top + r}Q${x},${top} ${x + r},${top}H${x2 - r}Q${x2},${top} ${x2},${top + r}V${bottom}Z`
    : `M${x},${top}V${bottom - r}Q${x},${bottom} ${x + r},${bottom}H${x2 - r}Q${x2},${bottom} ${x2},${bottom - r}V${top}Z`;
}
