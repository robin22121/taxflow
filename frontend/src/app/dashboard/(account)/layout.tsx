"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe } from "@/lib/queries";

// "내 정보" 세부메뉴 — 좌측 칼럼 (plan/14-accounts-permissions.md §6.6)
const ACCOUNT_SUBMENU = [
  { href: "/dashboard/staff", label: "직원계정 등록/변경", match: (p: string) => p.startsWith("/dashboard/staff") },
  { href: "/dashboard/settings", label: "사무실 설정", match: (p: string) => p.startsWith("/dashboard/settings") },
  { href: "/dashboard/assignments", label: "수임담당지정", match: (p: string) => p.startsWith("/dashboard/assignments") },
] as const;

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: me } = useMe();
  // 직원계정·수임담당지정은 대표(OWNER) 전용 — STAFF는 사무실 설정만 본다 (§6.6, §3 역할표)
  const items = me && me.role !== "OWNER"
    ? ACCOUNT_SUBMENU.filter((item) => item.href === "/dashboard/settings")
    : ACCOUNT_SUBMENU;

  return (
    <div className="flex gap-4 items-start">
      <aside className="w-[176px] shrink-0 sticky top-0">
        <nav className="flex flex-col gap-0.5">
          {items.map((item) => {
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
