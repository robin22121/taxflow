import { clsx } from "clsx";

import { avatarTone, initials } from "./format";
import styles from "./portal.module.css";

const toneClass = {
  blue: styles.avatarBlue,
  mint: styles.avatarMint,
  violet: styles.avatarViolet,
  amber: styles.avatarAmber,
  rose: styles.avatarRose,
};

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const tone = avatarTone(name);
  return (
    <span
      className={clsx(styles.avatar, toneClass[tone])}
      style={{ width: size, height: size, fontSize: size * 0.35 }}
    >
      {initials(name)}
    </span>
  );
}
