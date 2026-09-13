import { clsx } from "clsx";
import type { ReactNode } from "react";

import styles from "./portal.module.css";
import type { PortalState } from "./types";

type Tone = "amber" | "blue" | "mint" | "red" | "violet" | "slate";

const stateToTone: Record<PortalState, Tone> = {
  NONE: "slate",
  COLLECTING: "amber",
  REVIEWING: "amber",
  FILED: "blue",
  PAID: "mint",
  OVERDUE: "red",
};

const stateLabel: Record<PortalState, string> = {
  NONE: "열린 신고 없음",
  COLLECTING: "자료 수집 중",
  REVIEWING: "검토 대기",
  FILED: "신고 완료 · 납부 대기",
  PAID: "납부 완료 · 확정",
  OVERDUE: "미납 · 기한 초과",
};

const toneClass: Record<Tone, string> = {
  amber: styles.badgeAmber,
  blue: styles.badgeBlue,
  mint: styles.badgeMint,
  red: styles.badgeRed,
  violet: styles.badgeViolet,
  slate: styles.badgeSlate,
};

export function Badge({
  tone = "slate",
  children,
  dot = true,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={clsx(styles.badge, toneClass[tone], className)}>
      {dot && <span className={styles.badgeDot} aria-hidden />}
      {children}
    </span>
  );
}

export function StatusBadge({ state }: { state: PortalState }) {
  const tone = stateToTone[state];
  return (
    <Badge tone={tone} dot={state !== "PAID"}>
      {state === "PAID" && (
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
          <path
            d="M2.5 6.5l2.2 2.2L9.5 3.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
      {stateLabel[state]}
    </Badge>
  );
}

export { stateLabel };
