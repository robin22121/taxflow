import type { ReactNode } from "react";

import { Card } from "./Card";

export function KpiCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  accent?: "primary" | "muted";
}) {
  return (
    <Card tight>
      <div className="text-[11.5px] font-semibold uppercase tracking-wider text-[var(--muted-2)]">
        {label}
      </div>
      <div
        className="mt-2 text-[22px] font-bold tabular-nums"
        style={{ color: accent === "primary" ? "var(--navy)" : "var(--text)" }}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-[12px] text-[var(--muted)]">{hint}</div>}
    </Card>
  );
}
