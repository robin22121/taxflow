"use client";

import { clsx } from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        variant === "primary" && "bg-blue-600 text-white hover:bg-blue-700",
        variant === "secondary" && "bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700",
        variant === "ghost" && "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
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
        "rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100",
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
        "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100",
        className,
      )}
    />
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
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
        tone === "success" && "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
        tone === "warning" && "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
        tone === "danger" && "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
        tone === "info" && "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
      )}
    >
      {children}
    </span>
  );
}
