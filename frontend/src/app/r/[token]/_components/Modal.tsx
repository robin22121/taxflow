"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";

import styles from "./portal.module.css";

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className={styles.modalBackdrop} onClick={onClose} role="presentation">
      <div className={styles.modalSheet} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <div className="text-[16px] font-bold">{title}</div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="h-9 w-9 rounded-full text-[var(--muted)] hover:bg-[var(--line)] flex items-center justify-center"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <path
                d="M4 4l12 12M16 4L4 16"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 pb-4">{children}</div>
        {footer && (
          <div className="border-t border-[var(--line)] px-5 py-3 flex gap-2 justify-end bg-[var(--card)]">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
