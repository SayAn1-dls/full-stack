import { useState } from "react";
import { barPath, linear, niceTicks } from "./scales";
import { Tooltip, type TooltipData } from "./Tooltip";
import { useWidth } from "./useSize";

export interface Bin {
  lo: number;
  hi: number;
  count: number;
}

interface Props {
  bins: Bin[];
  total: number;
  refLines: { value: number; label: string }[];
  xFormat: (value: number) => string;
  colorFor: (bin: Bin) => string;
  tooltip: (bin: Bin) => TooltipData;
  height?: number;
  ariaLabel: string;
}

const M = { top: 26, bottom: 34, left: 40, right: 14 };

/** Error histogram on a continuous x axis. Bars are coloured by the sign of the error (polarity). */
export function Histogram({ bins, total, refLines, xFormat, colorFor, tooltip, height = 300, ariaLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotW = Math.max(40, width - M.left - M.right);
  const plotH = height - M.top - M.bottom;
  const xMin = bins[0].lo;
  const xMax = bins[bins.length - 1].hi;
  const x = linear([xMin, xMax], [0, plotW]);
  const maxCount = Math.max(...bins.map((b) => b.count), 1);
  const yTop = Math.ceil(maxCount / 20) * 20 || 20;
  const y = linear([0, yTop], [plotH, 0]);
  const yTicks = niceTicks(0, yTop, 4);
  const xTicks = niceTicks(xMin, xMax, Math.max(3, Math.floor(plotW / 80)));
  const tip = active === null ? null : tooltip(bins[active]);
  const lines = [...refLines].sort((a, b) => a.value - b.value);

  return (
    <div className="plot" ref={ref} style={{ height }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <g transform={`translate(${M.left},${M.top})`}>
          {yTicks.map((tick) => (
            <g key={tick}>
              <line x1={0} x2={plotW} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "axis" : "grid"} />
              <text x={-8} y={y(tick)} dy="0.32em" textAnchor="end" className="tick">{tick}</text>
            </g>
          ))}
          <text x={-M.left + 4} y={-12} className="tick unit">hours</text>
          {xTicks.map((tick) => (
            <text key={tick} x={x(tick)} y={plotH + 19} textAnchor="middle" className="tick">{xFormat(tick)}</text>
          ))}
          <line x1={x(0)} x2={x(0)} y1={0} y2={plotH} className="zero-line" />
          {bins.map((bin, i) => {
            const w = Math.max(2, x(bin.hi) - x(bin.lo) - 2);
            return (
              <g key={bin.lo}>
                {active === i && <rect x={x(bin.lo)} y={0} width={x(bin.hi) - x(bin.lo)} height={plotH} className="hover-wash" />}
                <path d={barPath(x(bin.lo) + 1, y(0), y(bin.count), w)} style={{ fill: colorFor(bin) }} />
                <rect
                  x={x(bin.lo)} y={0} width={x(bin.hi) - x(bin.lo)} height={plotH} fill="transparent" tabIndex={0} role="img"
                  aria-label={tooltip(bin).title + ": " + tooltip(bin).rows.map((r) => r.value).join(", ")}
                  onPointerEnter={() => setActive(i)} onPointerMove={() => setActive(i)} onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
          {lines.map((line) => {
            const flip = x(line.value) > plotW - 100;
            return (
              <g key={line.label} pointerEvents="none">
                <line x1={x(line.value)} x2={x(line.value)} y1={-4} y2={plotH} className="ref-line" />
                <text x={x(line.value) + (flip ? -4 : 4)} y={-10} textAnchor={flip ? "end" : "start"} className="ref-label">{line.label}</text>
              </g>
            );
          })}
          <text x={plotW} y={plotH + 31} textAnchor="end" className="tick unit">forecast − outturn (GW); {total.toLocaleString("en-GB")} hours</text>
        </g>
      </svg>
      {tip && active !== null ? <Tooltip x={M.left + x((bins[active].lo + bins[active].hi) / 2)} y={M.top + 6} width={width} data={tip} /> : null}
    </div>
  );
}
