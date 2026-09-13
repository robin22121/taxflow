import { clsx } from "clsx";
import type { ReactNode } from "react";

import styles from "./portal.module.css";

type Tone = "blue" | "mint" | "violet" | "amber" | "rose" | "slate";

const toneClass: Record<Tone, string> = {
  blue: styles.iconBoxBlue,
  mint: styles.iconBoxMint,
  violet: styles.iconBoxViolet,
  amber: styles.iconBoxAmber,
  rose: styles.iconBoxRose,
  slate: styles.iconBoxSlate,
};

export function IconBox({
  tone = "blue",
  size = "md",
  children,
}: {
  tone?: Tone;
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}) {
  return (
    <span
      className={clsx(
        styles.iconBox,
        size === "sm" && styles.iconBoxSm,
        size === "lg" && styles.iconBoxLg,
        toneClass[tone],
      )}
    >
      {children}
    </span>
  );
}
