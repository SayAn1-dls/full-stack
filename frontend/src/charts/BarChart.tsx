import { useState } from "react";
import { barPath, linear, niceDomain, niceTicks } from "./scales";
import { Tooltip, type TooltipData } from "./Tooltip";
import { useWidth } from "./useSize";

export interface BarSeries {
  id: string;
  color: string;
  values: (number | null)[];
}

interface Props {
  categories: { label: string; showTick?: boolean }[];
  series: BarSeries[];
  yFormat: (value: number) => string;
  yUnit?: string;
  tooltip: (category: number) => TooltipData;
  colorFor?: (seriesIndex: number, category: number, value: number) => string;
  annotations?: { category: number; series: number; text: string }[];
  height?: number;
  ariaLabel: string;
}

const M = { top: 22, bottom: 34, left: 40, right: 12 };
const GAP = 2; // surface gap between neighbouring bars

/** Grouped vertical bars: <= 24px thick, 4px rounded data end, square baseline, 2px surface gap. */
export function BarChart({ categories, series, yFormat, yUnit, tooltip, colorFor, annotations = [], height = 300, ariaLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotW = Math.max(40, width - M.left - M.right);
  const plotH = height - M.top - M.bottom;

  let min = 0;
  let max = 0;
  for (const s of series) for (const v of s.values) if (v !== null) { min = Math.min(min, v); max = Math.max(max, v); }
  const domain = niceDomain(min * 1.08, max * 1.08 || 1, 5);
  const y = linear(domain, [plotH, 0]);
  const ticks = niceTicks(domain[0], domain[1], 5);
  const slot = plotW / categories.length;
  const barW = Math.max(3, Math.min(24, Math.floor((slot * 0.78 - GAP * (series.length - 1)) / series.length)));
  const groupW = barW * series.length + GAP * (series.length - 1);
  const tickEvery = categories.some((c) => c.showTick !== undefined) ? 1 : Math.max(1, Math.ceil(categories.length / Math.floor(plotW / 54)));
  const tip = active === null ? null : tooltip(active);

  return (
    <div className="plot" ref={ref} style={{ height }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <g transform={`translate(${M.left},${M.top})`}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={0} x2={plotW} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "axis" : "grid"} />
              <text x={-8} y={y(tick)} dy="0.32em" textAnchor="end" className="tick">{yFormat(tick)}</text>
            </g>
          ))}
          {yUnit ? <text x={-M.left + 4} y={-10} className="tick unit">{yUnit}</text> : null}
          {categories.map((category, i) => {
            const x0 = i * slot + (slot - groupW) / 2;
            const show = category.showTick !== undefined ? category.showTick : i % tickEvery === 0;
            return (
              <g key={i}>
                {active === i && <rect x={i * slot} y={0} width={slot} height={plotH} className="hover-wash" />}
                {series.map((s, si) => {
                  const value = s.values[i];
                  if (value === null) return null;
                  const color = colorFor ? colorFor(si, i, value) : s.color;
                  return <path key={s.id} d={barPath(x0 + si * (barW + GAP), y(0), y(value), barW)} style={{ fill: color }} />;
                })}
                {show && <text x={i * slot + slot / 2} y={plotH + 19} textAnchor="middle" className="tick">{category.label}</text>}
                <rect
                  x={i * slot} y={0} width={slot} height={plotH} fill="transparent" tabIndex={0}
                  role="img" aria-label={`${category.label}: ${tooltip(i).rows.map((r) => `${r.label} ${r.value}`).join(", ")}`}
                  onPointerEnter={() => setActive(i)} onPointerMove={() => setActive(i)} onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
          {annotations.map((a) => {
            const value = series[a.series].values[a.category];
            if (value === null) return null;
            const cx = a.category * slot + (slot - groupW) / 2 + a.series * (barW + GAP) + barW / 2;
            return <text key={`${a.category}-${a.series}`} x={cx} y={value >= 0 ? y(value) - 6 : y(value) + 14} textAnchor="middle" className="bar-label">{a.text}</text>;
          })}
        </g>
      </svg>
      {tip && active !== null ? <Tooltip x={M.left + active * slot + slot / 2} y={M.top + 6} width={width} data={tip} /> : null}
    </div>
  );
}
