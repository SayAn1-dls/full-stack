import { useState, type PointerEvent } from "react";
import { linear, niceDomain, niceTicks } from "./scales";
import { Tooltip, type TooltipData } from "./Tooltip";
import { useWidth } from "./useSize";

interface Props {
  points: [number, number][];
  color: string;
  axisFormat: (value: number) => string;
  xLabel: string;
  yLabel: string;
  diagonalLabel: string;
  tooltip: (index: number) => TooltipData;
  ariaLabel: string;
}

const M = { top: 14, bottom: 40, left: 44, right: 14 };
const HIT_RADIUS = 24;

/** Forecast (x) vs outturn (y). Nearest-point hover with a 24px reach, so no one has to land on a 3px dot. */
export function ScatterChart({ points, color, axisFormat, xLabel, yLabel, diagonalLabel, tooltip, ariaLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotW = Math.max(60, width - M.left - M.right);
  const plotH = Math.min(plotW, 360);
  const height = plotH + M.top + M.bottom;
  const max = Math.max(...points.flat(), 1);
  const [, top] = niceDomain(0, max * 1.03, 5);
  const x = linear([0, top], [0, plotW]);
  const y = linear([0, top], [plotH, 0]);
  const ticks = niceTicks(0, top, 5);

  function onMove(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left;
    const py = event.clientY - box.top;
    let best = -1;
    let bestDistance = HIT_RADIUS * HIT_RADIUS;
    points.forEach(([fx, fy], i) => {
      const d = (x(fx) - px) ** 2 + (y(fy) - py) ** 2;
      if (d < bestDistance) { best = i; bestDistance = d; }
    });
    setActive(best >= 0 ? best : null);
  }

  const tip = active === null ? null : tooltip(active);
  return (
    <div className="plot" ref={ref} style={{ height }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <g transform={`translate(${M.left},${M.top})`}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={0} x2={plotW} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "axis" : "grid"} />
              <text x={-8} y={y(tick)} dy="0.32em" textAnchor="end" className="tick">{axisFormat(tick)}</text>
              <text x={x(tick)} y={plotH + 17} textAnchor="middle" className="tick">{axisFormat(tick)}</text>
            </g>
          ))}
          <line x1={x(0)} y1={y(0)} x2={x(top)} y2={y(top)} className="ref-line" />
          <text x={x(top) - 6} y={y(top) + 16} textAnchor="end" className="ref-label">{diagonalLabel}</text>
          {points.map(([fx, fy], i) => (
            <circle key={i} cx={x(fx)} cy={y(fy)} r={3.2} style={{ fill: color, opacity: 0.5 }} />
          ))}
          {active !== null && (
            <circle cx={x(points[active][0])} cy={y(points[active][1])} r={6} style={{ fill: color, stroke: "var(--surface)", strokeWidth: 2 }} pointerEvents="none" />
          )}
          <text x={plotW / 2} y={plotH + 34} textAnchor="middle" className="tick unit">{xLabel}</text>
          <text transform={`translate(${-34},${plotH / 2}) rotate(-90)`} textAnchor="middle" className="tick unit">{yLabel}</text>
          <rect x={0} y={0} width={plotW} height={plotH} fill="transparent" onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setActive(null)} />
        </g>
      </svg>
      {tip && active !== null ? <Tooltip x={M.left + x(points[active][0])} y={M.top + y(points[active][1]) - 8} width={width} data={tip} /> : null}
    </div>
  );
}
