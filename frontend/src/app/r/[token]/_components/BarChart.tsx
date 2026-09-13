import { periodShort } from "./format";
import styles from "./portal.module.css";
import type { MonthlyCostPoint } from "./types";

const SERIES = [
  { key: "wage" as const, label: "근로", color: "#3b82f6" },
  { key: "business" as const, label: "사업", color: "#8b5cf6" },
  { key: "daily" as const, label: "일용", color: "#f59e0b" },
  { key: "other" as const, label: "기타", color: "#94a3b8" },
];

export function StackedBarChart({ data }: { data: MonthlyCostPoint[] }) {
  const max = Math.max(1, ...data.map((d) => d.total));
  return (
    <div>
      <div className={styles.chartWrap} role="img" aria-label="월별 인건비">
        {data.map((point) => {
          const heightPct = (point.total / max) * 100;
          return (
            <div
              key={point.period}
              className={styles.chartBar}
              style={{ height: `${heightPct}%`, minHeight: point.total > 0 ? 2 : 0 }}
            >
              {SERIES.map(({ key, color }) => {
                const value = point[key];
                if (value <= 0) return null;
                const segPct = point.total > 0 ? (value / point.total) * 100 : 0;
                return (
                  <div
                    key={key}
                    className={styles.chartSeg}
                    style={{ height: `${segPct}%`, background: color }}
                    title={`${key}: ${value.toLocaleString()}`}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
      <div className={styles.chartWrap} style={{ height: "auto", alignItems: "flex-start", paddingTop: 4 }}>
        {data.map((point) => (
          <div key={point.period} className={styles.chartLabel} style={{ flex: 1 }}>
            {periodShort(point.period)}
          </div>
        ))}
      </div>
      <div className={`${styles.legend} mt-3`}>
        {SERIES.map((s) => (
          <span key={s.key}>
            <span className={styles.legendSwatch} style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
