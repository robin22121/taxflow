"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

import { clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { Button } from "@/components/ui";

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
      <aside className="w-60 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4 flex flex-col">
        <div className="text-lg font-semibold mb-1">TaxFlow AI</div>
        <div className="text-xs text-gray-500 mb-6">{me?.name ?? "..."}</div>
        <nav className="space-y-1 flex-1">
          <NavLink href="/dashboard" current={pathname}>월별 신고</NavLink>
          <NavLink href="/dashboard/clients" current={pathname}>거래처 관리</NavLink>
        </nav>
        <Button variant="ghost" onClick={logout} className="text-left">
          로그아웃
        </Button>
      </aside>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}

function NavLink({
  href,
  current,
  children,
}: {
  href: string;
  current: string;
  children: React.ReactNode;
}) {
  const active = current === href || current.startsWith(href + "/");
  return (
    <Link
      href={href}
      className={
        "block rounded-md px-3 py-2 text-sm " +
        (active
          ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800")
      }
    >
      {children}
    </Link>
  );
}
