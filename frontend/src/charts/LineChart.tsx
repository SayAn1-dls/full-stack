import { useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import { invert, linear, nearestIndex, niceDomain, niceTicks } from "./scales";
import { Tooltip, type TooltipData } from "./Tooltip";
import { useWidth } from "./useSize";

export interface LinePoint {
  x: number;
  y: number | null;
}

export interface LineSeries {
  id: string;
  color: string;
  points: LinePoint[];
  markers?: boolean;
  muted?: boolean;
  strokeWidth?: number;
}

export interface BandSeries {
  id: string;
  color: string;
  points: { x: number; lo: number; hi: number }[];
}

interface Props {
  series: LineSeries[];
  bands?: BandSeries[];
  xDomain: [number, number];
  xTicks: { value: number; label: string }[];
  yFormat: (value: number) => string;
  yUnit?: string;
  yDomain?: [number, number];
  snapXs: number[];
  tooltip: (x: number) => TooltipData | null;
  endLabels?: { seriesId: string; text: string }[];
  height?: number;
  ariaLabel: string;
}

const M = { top: 26, bottom: 30, left: 40 };

/** Keeps a tick only if it sits at least `gap` px right of the previous kept one (no overlapping labels). */
export function thin<T extends { value: number }>(ticks: T[], x: (v: number) => number, gap: number): T[] {
  const kept: T[] = [];
  let last = -Infinity;
  for (const tick of ticks) {
    const px = x(tick.value);
    if (px - last >= gap) {
      kept.push(tick);
      last = px;
    }
  }
  return kept;
}

function pathOf(points: LinePoint[], x: (v: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p.y === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function LineChart(props: Props) {
  const { series, bands = [], xDomain, xTicks, yFormat, snapXs, tooltip, endLabels = [], ariaLabel } = props;
  const [ref, width] = useWidth<HTMLDivElement>();
  const height = props.height ?? 340;
  const right = endLabels.length ? 66 : 14;
  const plotW = Math.max(40, width - M.left - right);
  const plotH = height - M.top - M.bottom;
  const [cursor, setCursor] = useState<number | null>(null);

  const yDomain = useMemo<[number, number]>(() => {
    if (props.yDomain) return props.yDomain;
    let max = 0;
    for (const s of series) for (const p of s.points) if (p.y !== null) max = Math.max(max, p.y);
    for (const b of bands) for (const p of b.points) max = Math.max(max, p.hi);
    return niceDomain(0, max * 1.04 || 1, 5);
  }, [props.yDomain, series, bands]);

  const x = useMemo(() => linear(xDomain, [0, plotW]), [xDomain, plotW]);
  const y = useMemo(() => linear(yDomain, [plotH, 0]), [yDomain, plotH]);
  const yTicks = niceTicks(yDomain[0], yDomain[1], 5);

  function moveTo(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const dataX = invert(xDomain, [0, plotW])(event.clientX - box.left);
    const index = nearestIndex(snapXs, dataX);
    if (index >= 0) setCursor(snapXs[index]);
  }

  function onKey(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Escape") return;
    event.preventDefault();
    if (event.key === "Escape") return setCursor(null);
    const current = cursor === null ? -1 : snapXs.indexOf(cursor);
    const next = event.key === "ArrowRight" ? Math.min(snapXs.length - 1, current + 1) : Math.max(0, current < 0 ? 0 : current - 1);
    setCursor(snapXs[next]);
  }

  const tip = cursor === null ? null : tooltip(cursor);
  const labelled = endLabels
    .map((label) => {
      const s = series.find((candidate) => candidate.id === label.seriesId);
      const last = s ? [...s.points].reverse().find((p) => p.y !== null) : undefined;
      return s && last && last.y !== null ? { ...label, y: y(last.y), x: x(last.x) } : null;
    })
    .filter((v): v is { seriesId: string; text: string; y: number; x: number } => v !== null);
  const separated = labelled.every((a, i) => labelled.every((b, j) => i === j || Math.abs(a.y - b.y) >= 15));

  return (
    <div className="plot" ref={ref} style={{ height }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel} tabIndex={0} onKeyDown={onKey} onBlur={() => setCursor(null)}>
        <g transform={`translate(${M.left},${M.top})`}>
          {yTicks.map((tick) => (
            <g key={tick}>
              <line x1={0} x2={plotW} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "axis" : "grid"} />
              <text x={-8} y={y(tick)} dy="0.32em" textAnchor="end" className="tick">{yFormat(tick)}</text>
            </g>
          ))}
          {props.yUnit ? <text x={-M.left + 4} y={-12} className="tick unit">{props.yUnit}</text> : null}
          {thin(xTicks, x, 54).map((tick) => (
            <text key={tick.value} x={x(tick.value)} y={plotH + 19} textAnchor="middle" className="tick">{tick.label}</text>
          ))}
          {bands.map((band) => {
            const upper = band.points.map((p) => `${x(p.x).toFixed(1)},${y(p.hi).toFixed(1)}`);
            const lower = [...band.points].reverse().map((p) => `${x(p.x).toFixed(1)},${y(p.lo).toFixed(1)}`);
            return <polygon key={band.id} points={[...upper, ...lower].join(" ")} style={{ fill: band.color, opacity: 0.14 }} />;
          })}
          {series.map((s) => (
            <path
              key={s.id}
              d={pathOf(s.points, x, y)}
              fill="none"
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ stroke: s.color, strokeWidth: s.strokeWidth ?? (s.muted ? 1.25 : 2), opacity: s.muted ? 0.7 : 1 }}
            />
          ))}
          {series.filter((s) => s.markers).map((s) =>
            s.points.filter((p) => p.y !== null).map((p) => (
              <circle key={`${s.id}-${p.x}`} cx={x(p.x)} cy={y(p.y as number)} r={4} style={{ fill: s.color, stroke: "var(--surface)", strokeWidth: 2 }} />
            )),
          )}
          {separated && labelled.map((label) => (
            <text key={label.seriesId} x={label.x + 8} y={label.y} dy="0.32em" className="end-label">{label.text}</text>
          ))}
          {cursor !== null && (
            <g pointerEvents="none">
              <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={plotH} className="crosshair" />
              {series.filter((s) => !s.muted).map((s) => {
                const p = s.points.find((q) => q.x === cursor && q.y !== null);
                return p ? <circle key={s.id} cx={x(cursor)} cy={y(p.y as number)} r={5} style={{ fill: s.color, stroke: "var(--surface)", strokeWidth: 2 }} /> : null;
              })}
            </g>
          )}
          <rect x={0} y={0} width={plotW} height={plotH} fill="transparent" onPointerMove={moveTo} onPointerDown={moveTo} onPointerLeave={() => setCursor(null)} />
        </g>
      </svg>
      {tip && cursor !== null ? <Tooltip x={M.left + x(cursor)} y={M.top + 6} width={width} data={tip} /> : null}
    </div>
  );
}
