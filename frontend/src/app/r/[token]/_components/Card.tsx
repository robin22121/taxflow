import { clsx } from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

import styles from "./portal.module.css";

export function Card({
  className,
  hero,
  tight,
  ...props
}: HTMLAttributes<HTMLDivElement> & { hero?: boolean; tight?: boolean }) {
  return (
    <div
      {...props}
      className={clsx(
        hero ? styles.cardHero : styles.card,
        tight && !hero && styles.cardTight,
        className,
      )}
    />
  );
}

export function SectionHeader({
  title,
  action,
  desc,
}: {
  title: string;
  desc?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-2.5 flex items-end justify-between gap-3">
      <div>
        <h2 className={styles.h2}>{title}</h2>
        {desc && <p className="mt-0.5 text-[12.5px] text-[var(--muted)]">{desc}</p>}
      </div>
      {action}
    </div>
  );
}
