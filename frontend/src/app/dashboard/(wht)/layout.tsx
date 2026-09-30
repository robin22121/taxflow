"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// "원천세 신고" 세부메뉴 — 좌측 칼럼 (plan/08-action-items.md 2026-09-30 "상단 탑 메뉴 전면 개편")
const WHT_SUBMENU = [
  { href: "/dashboard/requests", label: "자료요청", match: (p: string) => p.startsWith("/dashboard/requests") },
  { href: "/dashboard", label: "월별 신고", match: (p: string) => p === "/dashboard" },
  { href: "/dashboard/clients", label: "거래처정보 등록/변경", match: (p: string) => p.startsWith("/dashboard/clients") },
  { href: "/dashboard/employee-changes", label: "사원정보 등록/변경", match: (p: string) => p.startsWith("/dashboard/employee-changes") },
] as const;

export default function WhtLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    // 원래 각 페이지가 갖고 있던 "-m-4 sm:-m-6 + calc(100dvh - 60px)" 전체높이 캔버스를
    // 이 레이아웃이 대신 잡아주고, 좌측 세부메뉴 칼럼을 그 안에 함께 배치한다.
    <div className="-m-4 sm:-m-6 flex" style={{ height: "calc(100dvh - 60px)" }}>
      <aside className="w-[176px] shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
        <nav className="flex flex-col gap-0.5 p-3">
          {WHT_SUBMENU.map((item) => {
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
      {/* overflow-y-auto: (wht)/page.tsx처럼 자체 스크롤 영역을 가진 화면도, 거래처·직원변동처럼
          평범한 문서 흐름 화면도 둘 다 이 안에서 잘리지 않고 보이게 하는 안전한 기본값 */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-y-auto">{children}</div>
    </div>
  );
}
