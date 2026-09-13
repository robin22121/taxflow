import { dDay, periodLabel } from "./format";
import styles from "./portal.module.css";
import { StatusBadge } from "./Badge";
import type { PortalStatusInfo } from "./types";

export function StatusStrip({ status }: { status: PortalStatusInfo }) {
  const d = status.due_date ? dDay(status.due_date) : "";
  return (
    <div className={styles.statusStrip}>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-semibold text-[var(--text)] truncate">
          {status.period ? `${periodLabel(status.period)} 귀속` : "지금 열린 신고가 없어요"}
        </div>
        {status.due_date && (
          <div className="text-[11.5px] text-[var(--muted)] mt-0.5">
            납부기한 {status.due_date} {d && `· ${d}`}
          </div>
        )}
      </div>
      <StatusBadge state={status.state} />
    </div>
  );
}
