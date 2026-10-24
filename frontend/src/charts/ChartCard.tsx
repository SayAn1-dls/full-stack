import { useId, useState, type ReactNode } from "react";
import { Legend, type LegendItem } from "./Legend";

export interface TableSpec {
  columns: string[];
  rows: (string | number)[][];
}

interface Props {
  title: string;
  subtitle?: ReactNode;
  legend?: LegendItem[];
  table: TableSpec;
  children: ReactNode;
  footnote?: ReactNode;
  dimmed?: boolean;
  wide?: boolean;
}

/** Card with the title, legend and a table-view twin: every value on the chart is also readable as a table. */
export function ChartCard({ title, subtitle, legend, table, children, footnote, dimmed, wide }: Props) {
  const [asTable, setAsTable] = useState(false);
  const id = useId();
  return (
    <figure className={`card chart-card${wide ? " wide" : ""}`} aria-labelledby={id}>
      <header className="chart-head">
        <div>
          <h3 id={id}>{title}</h3>
          {subtitle ? <p className="subtitle">{subtitle}</p> : null}
        </div>
        <button type="button" className="ghost" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "View chart" : "View as table"}
        </button>
      </header>
      {legend && !asTable ? <Legend items={legend} /> : null}
      <div className={`chart-body${dimmed ? " dimmed" : ""}`}>
        {asTable ? <DataTable spec={table} /> : children}
      </div>
      {footnote ? <figcaption className="footnote">{footnote}</figcaption> : null}
    </figure>
  );
}

export function DataTable({ spec }: { spec: TableSpec }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {spec.columns.map((column) => (
              <th key={column} scope="col">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} className={typeof cell === "number" ? "num" : undefined}>
                  {typeof cell === "number" ? cell.toLocaleString("en-GB") : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
