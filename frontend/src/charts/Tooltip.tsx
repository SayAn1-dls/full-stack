import type { CSSProperties } from "react";

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
  kind?: "line" | "band" | "bar" | "dot";
}

export interface TooltipData {
  title: string;
  rows: TooltipRow[];
  footnote?: string;
}

/** Values lead (strong), labels follow (secondary); rows are keyed by a short stroke of the series colour. */
export function Tooltip({ x, y, width, data }: { x: number; y: number; width: number; data: TooltipData }) {
  const flip = x > width * 0.55;
  const style: CSSProperties = { left: x, top: y, transform: flip ? "translateX(calc(-100% - 14px))" : "translateX(14px)" };
  return (
    <div className="tooltip" style={style} role="status">
      <div className="tooltip-title">{data.title}</div>
      {data.rows.map((row) => (
        <div className="tooltip-row" key={row.label}>
          <span
            className={`key key-${row.kind ?? "line"}`}
            style={{ background: row.color ?? "transparent", visibility: row.color ? "visible" : "hidden" }}
          />
          <span className="tooltip-value">{row.value}</span>
          <span className="tooltip-label">{row.label}</span>
        </div>
      ))}
      {data.footnote ? <div className="tooltip-foot">{data.footnote}</div> : null}
    </div>
  );
}
