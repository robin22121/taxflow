"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// "사원정보" 세부메뉴 — 좌측 칼럼 ((tax-other)/layout.tsx와 같은 패턴).
// 거래처정보에 있던 "사원 목록"·"급여명세서"(급여 이력)·"위하고에서 가져오기"를
// 이 메뉴 하위로 옮겼다 (2026-10-01, plan/08-action-items.md).
const EMPLOYEE_INFO_SUBMENU = [
  { href: "/dashboard/employee-changes", label: "입퇴사 승인", match: (p: string) => p === "/dashboard/employee-changes" },
  { href: "/dashboard/employee-changes/roster", label: "사원 목록", match: (p: string) => p.startsWith("/dashboard/employee-changes/roster") },
  { href: "/dashboard/employee-changes/payroll", label: "급여명세서", match: (p: string) => p.startsWith("/dashboard/employee-changes/payroll") },
] as const;

export default function EmployeeInfoLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex gap-4 items-start">
      <aside className="w-[176px] shrink-0 sticky top-0">
        <nav className="flex flex-col gap-0.5">
          {EMPLOYEE_INFO_SUBMENU.map((item) => {
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
