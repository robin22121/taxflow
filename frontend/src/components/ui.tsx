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
        variant === "primary" && "bg-blue-600 text-white border border-blue-600 shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_8px_20px_-8px_rgba(19,112,206,0.45)] hover:brightness-110",
        variant === "secondary" && "bg-white text-gray-900 border border-gray-300 hover:border-gray-400",
        variant === "ghost" && "text-gray-700 border border-transparent hover:bg-gray-50",
        variant === "danger" && "bg-white text-red-600 border border-red-600/25 hover:bg-red-50/30",
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
        "rounded-[14px] border border-gray-300 bg-white p-4 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]",
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
        "p-1.5 bg-gray-50 border border-gray-300 rounded-[18px] shadow-[0_1px_0_rgba(28,25,23,0.04),0_4px_12px_-8px_rgba(28,25,23,0.06)]",
        className,
      )}
    >
      <div className="bg-white border border-black/[0.06] rounded-[12px] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] overflow-hidden">
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
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 placeholder:text-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors",
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
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 placeholder:text-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors",
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
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
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
        className={clsx(
          "w-full rounded-[14px] bg-white border border-gray-300 shadow-[0_2px_0_rgba(28,25,23,0.04),0_32px_64px_-28px_rgba(28,25,23,0.18)]",
          size === "lg" ? "max-w-3xl" : "max-w-md",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-300 px-5 py-3.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-gray-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-900 transition-colors"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-gray-300 px-5 py-3">
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
        tone === "neutral" && "bg-gray-50 text-gray-700 border border-gray-300",
        tone === "success" && "bg-gray-50 text-gray-900 border border-gray-300",
        tone === "warning" && "bg-red-50 text-red-600 border border-red-600/20",
        tone === "danger" && "bg-red-50 text-red-600 border border-red-600/20",
        tone === "info" && "bg-blue-50 text-blue-600 border border-blue-600/20",
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
          ? "bg-gray-900 text-white"
          : "bg-gray-50 text-gray-700 border border-transparent hover:border-gray-300",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-600/8 text-blue-600 text-[10.5px] font-semibold uppercase tracking-widest">
      {children}
    </span>
  );
}
