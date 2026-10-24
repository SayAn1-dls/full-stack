export interface LegendItem {
  label: string;
  color: string;
  kind: "line" | "rect" | "band";
}

/** Always present for two or more series; text stays in ink, the swatch carries the identity. */
export function Legend({ items }: { items: LegendItem[] }) {
  if (items.length < 2) return null;
  return (
    <ul className="legend" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label}>
          <span className={`swatch swatch-${item.kind}`} style={{ background: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
