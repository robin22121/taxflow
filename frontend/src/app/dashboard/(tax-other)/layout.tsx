"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// "타세목 신고·납부" 세부메뉴 — 좌측 칼럼 (plan/08-action-items.md 2026-09-30 "상단 탑 메뉴 전면 개편")
const TAX_OTHER_SUBMENU = [
  { href: "/dashboard/messages", label: "문자발송", match: (p: string) => p.startsWith("/dashboard/messages") },
] as const;

export default function TaxOtherLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex gap-4 items-start">
      <aside className="w-[176px] shrink-0 sticky top-0">
        <nav className="flex flex-col gap-0.5">
          {TAX_OTHER_SUBMENU.map((item) => {
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "px-3 py-2 rounded-lg text-[13px] font-medium transition-colors " +
                  (active ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-100")
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
