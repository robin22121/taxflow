"use client";

import { clsx } from "clsx";
import type { ReactNode } from "react";

import styles from "./portal.module.css";
import type { ViewKey } from "./types";

const MENU: { key: ViewKey; label: string; icon: ReactNode; short: string }[] = [
  {
    key: "filing",
    label: "이달분 신고하기",
    short: "이달분",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <rect x="3.5" y="4.5" width="13" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M7 3v3M13 3v3M4 9h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    key: "payment",
    label: "원천세 납부하기",
    short: "납부",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <rect x="2.5" y="5.5" width="15" height="10" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M2.5 9h15" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="14" cy="12.5" r="1" fill="currentColor" />
      </svg>
    ),
  },
  {
    key: "cost",
    label: "월별 인건비",
    short: "인건비",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <path d="M4 15V9M8 15V6M12 15V11M16 15V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    key: "employee",
    label: "직원별 명세",
    short: "직원",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="7.5" r="3" stroke="currentColor" strokeWidth="1.5" />
        <path d="M4 16.5c1.4-2.5 3.5-3.5 6-3.5s4.6 1 6 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
];

export function Shell({
  clientName,
  taxOfficeName,
  view,
  setView,
  children,
}: {
  clientName: string;
  taxOfficeName?: string;
  view: ViewKey;
  setView: (v: ViewKey) => void;
  children: ReactNode;
}) {
  return (
    <div className={styles.portal}>
      <div className={styles.shell}>
        {/* 데스크톱 사이드바 */}
        <aside className={`${styles.sidebar} hidden lg:block`}>
          <div className="px-3 pb-4 border-b border-[var(--line)]">
            <div className="flex items-center gap-2">
              <span
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg font-extrabold text-white"
                style={{ background: "var(--navy)" }}
              >
                이
              </span>
              <div className="min-w-0">
                <div className="text-[13.5px] font-bold text-[var(--navy)]">이지원천</div>
                <div className="text-[11px] text-[var(--muted)] truncate">
                  {taxOfficeName ?? "세무 대리"}
                </div>
              </div>
            </div>
            <div className="mt-3 text-[13px] font-semibold text-[var(--text)] truncate">
              {clientName}
            </div>
          </div>
          <nav className="mt-3 flex flex-col gap-1">
            {MENU.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setView(item.key)}
                className={clsx(
                  styles.sidebarItem,
                  view === item.key && styles.sidebarItemActive,
                )}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>
        </aside>

        <div className="flex-1 min-w-0">
          {/* 모바일 상단 헤더 */}
          <header className="lg:hidden bg-[var(--card)] border-b border-[var(--line)] px-5 py-4">
            <div className="flex items-center gap-2">
              <span
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg font-extrabold text-white"
                style={{ background: "var(--navy)" }}
              >
                이
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[15px] font-bold text-[var(--text)] truncate">
                  {clientName}
                </div>
                <div className="text-[11.5px] text-[var(--muted)] truncate">
                  이지원천 · {taxOfficeName ?? "세무 대리"}
                </div>
              </div>
            </div>
          </header>

          <main className={styles.content}>{children}</main>
        </div>
      </div>

      {/* 모바일 하단 탭바 */}
      <nav className={`${styles.tabbar} lg:hidden`} aria-label="주요 메뉴">
        {MENU.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setView(item.key)}
            className={clsx(styles.tab, view === item.key && styles.tabActive)}
          >
            {item.icon}
            <span>{item.short}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
