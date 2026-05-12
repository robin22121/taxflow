"use client";

import { clsx } from "clsx";
import { useEffect } from "react";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap",
        variant === "primary" && "bg-accent text-white border border-accent shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_8px_20px_-8px_rgba(19,112,206,0.45)] hover:brightness-110",
        variant === "secondary" && "bg-paper text-ink border border-ink-4 hover:border-ink-3",
        variant === "ghost" && "text-ink-2 border border-transparent hover:bg-paper-2",
        variant === "danger" && "bg-paper text-alert border border-alert/25 hover:bg-alert-50/30",
        className,
      )}
    />
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={clsx(
        "rounded-[14px] border border-ink-4 bg-paper p-4 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]",
        className,
      )}
    />
  );
}

export function BezelCard({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={clsx(
        "p-1.5 bg-paper-2 border border-ink-4 rounded-[18px] shadow-[0_1px_0_rgba(28,25,23,0.04),0_4px_12px_-8px_rgba(28,25,23,0.06)]",
        className,
      )}
    >
      <div className="bg-paper border border-black/[0.06] rounded-[12px] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] overflow-hidden">
        {children}
      </div>
    </div>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-lg border border-ink-4 bg-paper px-3 py-2 text-[13px] text-ink-2 placeholder:text-ink-3 focus:border-accent focus:ring-1 focus:ring-accent outline-none transition-colors",
        className,
      )}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={clsx(
        "w-full rounded-lg border border-ink-4 bg-paper px-3 py-2 text-[13px] text-ink-2 placeholder:text-ink-3 focus:border-accent focus:ring-1 focus:ring-accent outline-none transition-colors",
        className,
      )}
    />
  );
}

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
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-[14px] bg-paper border border-ink-4 shadow-[0_2px_0_rgba(28,25,23,0.04),0_32px_64px_-28px_rgba(28,25,23,0.18)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-4 px-5 py-3.5">
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-3 hover:text-ink transition-colors"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-ink-4 px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-paper-2 text-ink-2 border border-ink-4",
        tone === "success" && "bg-paper-2 text-ink border border-ink-4",
        tone === "warning" && "bg-alert-50 text-alert border border-alert/20",
        tone === "danger" && "bg-alert-50 text-alert border border-alert/20",
        tone === "info" && "bg-accent-50 text-accent border border-accent/20",
      )}
    >
      {children}
    </span>
  );
}

export function Chip({
  children,
  active = false,
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { active?: boolean }) {
  return (
    <span
      {...props}
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-default transition-all",
        active
          ? "bg-ink text-white"
          : "bg-paper-2 text-ink-2 border border-transparent hover:border-ink-4",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-accent/8 text-accent text-[10.5px] font-semibold uppercase tracking-widest">
      {children}
    </span>
  );
}
