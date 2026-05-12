"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

import { clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";

const NAV_ITEMS = [
  { href: "/dashboard", label: "월별 신고", icon: "calendar" },
  { href: "/dashboard/clients", label: "거래처", icon: "buildings" },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isError } = useMe();

  useEffect(() => {
    if (typeof window !== "undefined" && !getToken()) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 border-r border-ink-4 bg-paper flex flex-col shrink-0">
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 pt-5 pb-3">
          <div className="w-[26px] h-[26px] rounded-lg bg-ink text-white flex items-center justify-center text-[13px] font-extrabold">
            이
          </div>
          <span className="text-base font-bold tracking-tight text-black">이지원천</span>
        </div>

        {/* Workspace card */}
        <div className="mx-3 mb-3 px-3 py-2 rounded-lg bg-paper-2 border border-ink-5">
          <div className="text-[12px] font-medium text-ink-2 truncate">
            {me?.name ?? "세무사사무소"}
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "flex items-center gap-2.5 px-2.5 py-2 rounded-[9px] text-[13px] font-medium transition-colors " +
                  (active
                    ? "bg-paper-2 text-ink font-semibold"
                    : "text-ink-2 hover:bg-paper-2")
                }
              >
                <NavIcon name={item.icon} active={active} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="px-2 pb-3 border-t border-ink-5 pt-2 mt-2">
          <button
            onClick={logout}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[9px] text-[13px] text-ink-3 hover:bg-paper-2 transition-colors"
          >
            <NavIcon name="logout" active={false} />
            로그아웃
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 bg-paper-2">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}

function NavIcon({ name, active }: { name: string; active: boolean }) {
  const color = active ? "text-ink" : "text-ink-3";
  const paths: Record<string, React.ReactNode> = {
    calendar: (
      <>
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </>
    ),
    buildings: (
      <>
        <path d="M3 21h18" />
        <path d="M5 21V7l8-4v18" />
        <path d="M19 21V11l-6-4" />
        <path d="M9 9v.01M9 12v.01M9 15v.01M9 18v.01" />
      </>
    ),
    logout: (
      <>
        <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" y1="12" x2="9" y2="12" />
      </>
    ),
  };

  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={color}
    >
      {paths[name]}
    </svg>
  );
}
