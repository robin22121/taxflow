"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

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
      <header className="flex items-center justify-between px-5 border-b border-gray-200 bg-white shrink-0 h-12">
        <div className="flex items-center gap-6">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="w-[22px] h-[22px] rounded-md bg-gray-900 text-white flex items-center justify-center text-[11px] font-extrabold">
              이
            </div>
            <span className="text-[14px] font-bold tracking-tight text-black">이지원천</span>
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
                    "px-3 py-1.5 rounded-full text-[13px] font-medium transition-colors " +
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

        <div className="flex items-center gap-3">
          <span className="text-[12px] text-gray-500 truncate max-w-[140px]">
            {me?.name ?? "세무사사무소"}
          </span>
          <button
            onClick={logout}
            className="text-[12px] font-medium text-red-600 hover:text-red-700 transition-colors"
          >
            로그아웃
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 min-w-0 bg-gray-50">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
