"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";

const NAV_ITEMS = [
  { href: "/dashboard", label: "월별 신고" },
  { href: "/dashboard/clients", label: "거래처" },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isError } = useMe();
  const [showMenu, setShowMenu] = useState(false);

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
    <div className="flex flex-col min-h-screen">
      {/* Top nav bar */}
      <header className="flex items-center justify-between px-3 sm:px-5 border-b border-gray-200 bg-white shrink-0 h-12">
        <div className="flex items-center gap-3 sm:gap-6 min-w-0">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="w-[22px] h-[22px] rounded-md bg-gray-900 text-white flex items-center justify-center text-[11px] font-extrabold">
              이
            </div>
            <span className="text-[14px] font-bold tracking-tight text-black hidden sm:inline">이지원천</span>
          </Link>

          {/* Nav tabs */}
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={
                    "px-2.5 sm:px-3 py-1.5 rounded-full text-[12px] sm:text-[13px] font-medium transition-colors " +
                    (active
                      ? "bg-gray-900 text-white"
                      : "text-gray-600 hover:bg-gray-100")
                  }
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User menu */}
        <div className="relative shrink-0">
          <button
            onClick={() => setShowMenu((v) => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full hover:bg-gray-100 transition-colors"
          >
            <div className="w-6 h-6 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center text-[11px] font-bold">
              {(me?.name ?? "?").charAt(0)}
            </div>
            <span className="text-[12px] font-medium text-gray-700 hidden sm:inline max-w-[120px] truncate">
              {me?.name ?? "로딩중"}
            </span>
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          {showMenu && (<>
            <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
            <div className="absolute right-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-xl shadow-lg z-50 py-1 overflow-hidden">
              <div className="px-3 py-2.5 border-b border-gray-100">
                <div className="text-[13px] font-semibold text-gray-900">{me?.name}</div>
                <div className="text-[11px] text-gray-500 mt-0.5">{me?.office_name ?? ""}</div>
                <div className="text-[11px] text-gray-400">{me?.email}</div>
              </div>
              <Link href="/dashboard/account" onClick={() => setShowMenu(false)} className="block px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50">
                내 정보
              </Link>
              <div className="border-t border-gray-100">
                <button onClick={() => { setShowMenu(false); logout(); }} className="w-full text-left px-3 py-2 text-[12px] text-red-600 hover:bg-red-50">
                  로그아웃
                </button>
              </div>
            </div>
          </>)}
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 min-w-0 bg-gray-50">
        <div className="p-4 sm:p-6 pb-24">{children}</div>
      </main>

    </div>
  );
}
