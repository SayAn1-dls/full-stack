import type { ReactNode } from "react";

export function Hero({ value, unit, caption, children }: { value: string; unit: string; caption: ReactNode; children?: ReactNode }) {
  return (
    <div className="hero">
      <div>
        <div className="hero-figure">
          <span className="value">{value}</span>
          <span className="unit">{unit}</span>
        </div>
        <p className="hero-caption">{caption}</p>
      </div>
      {children}
    </div>
  );
}

export function Tile({ label, value, sub }: { label: string; value: string; sub?: ReactNode }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub ? <div className="sub">{sub}</div> : null}
    </div>
  );
}

export function Callout({ children, kind }: { children: ReactNode; kind?: "error" }) {
  return (
    <div className={`callout${kind ? ` ${kind}` : ""}`} role={kind === "error" ? "alert" : undefined}>
      <span className="mark" aria-hidden="true">{kind === "error" ? "!" : "i"}</span>
      <div>{children}</div>
    </div>
  );
}

export function SectionLabel({ children, chip }: { children: ReactNode; chip?: ReactNode }) {
  return (
    <div className="section-label">
      {children}
      {chip}
    </div>
  );
}
