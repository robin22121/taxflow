"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: me, isError, isLoading } = useMe();

  useEffect(() => {
    if (typeof window !== "undefined" && !getToken()) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  // 슈퍼어드민이 아니면 일반 대시보드로
  useEffect(() => {
    if (me && !me.is_superadmin) router.replace("/dashboard");
  }, [me, router]);

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  if (isLoading || !me || !me.is_superadmin) {
    return (
      <div className="flex min-h-screen items-center justify-center text-[13px] text-gray-400">
        로딩중...
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      <header className="flex items-center justify-between px-3 sm:px-5 border-b border-gray-200 bg-white shrink-0 h-12">
        <Link href="/admin" className="flex items-center gap-2 shrink-0">
          <div className="w-[22px] h-[22px] rounded-md bg-gray-900 text-white flex items-center justify-center text-[11px] font-extrabold">
            이
          </div>
          <span className="text-[14px] font-bold tracking-tight text-black">이지원천</span>
          <span className="text-[11px] font-medium text-blue-600 bg-blue-50 border border-blue-600/20 rounded-full px-2 py-0.5">
            서버 관리자
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-gray-600 hidden sm:inline">{me.name}</span>
          <button
            onClick={logout}
            className="text-[12px] text-red-600 hover:underline font-medium"
          >
            로그아웃
          </button>
        </div>
      </header>
      <main className="flex-1 min-w-0 bg-gray-50">
        <div className="p-4 sm:p-6 pb-24">{children}</div>
      </main>
    </div>
  );
}
