"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { HeaderSlotContext } from "@/components/header-slot";
import { ActivityBar } from "@/components/rpa/activity-bar";
import { CertificateIssueModal } from "@/components/certificates/certificate-issue-modal";
import { AiAssistantDialog } from "@/components/ai-assistant/ai-assistant-dialog";

// 2026-09-30 상단 탑 메뉴 재개편 (plan/08-action-items.md) — 거래처정보·사원정보를
// "원천세 신고" 세부메뉴에서 다시 꺼내 평평한 상단 탭으로 배치(사용자 확정, 회귀).
// "자료요청"은 실제 발송 로직이 없는 플레이스홀더였는데 상단 탭에서 제거(2026-09-30).
// "타세목 신고·납부"는 문자발송 세부메뉴를 그대로 유지한다((tax-other)/layout.tsx).
const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "원천세 신고",
    match: (p: string) => p === "/dashboard" || p.startsWith("/dashboard/filings"),
  },
  {
    href: "/dashboard/clients",
    label: "거래처정보",
    match: (p: string) => p.startsWith("/dashboard/clients"),
  },
  {
    href: "/dashboard/employee-changes",
    label: "사원정보",
    match: (p: string) => p.startsWith("/dashboard/employee-changes"),
  },
  {
    href: "/dashboard/messages",
    label: "타세목 신고·납부",
    match: (p: string) => p.startsWith("/dashboard/messages"),
  },
  {
    href: "/dashboard/wehago-jobs",
    label: "위하고 작업",
    match: (p: string) => p.startsWith("/dashboard/wehago-jobs"),
  },
  {
    href: "/dashboard/pending-tasks",
    label: "업무미처리내역",
    match: (p: string) => p.startsWith("/dashboard/pending-tasks"),
  },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isError } = useMe();
  const [showMenu, setShowMenu] = useState(false);
  // 증명원 발급 팝업 — 화면에서 선택된 거래처(?client_id)가 있으면 거래처 선택 단계를 건너뛴다
  const [certificate, setCertificate] = useState<{ clientId: string | null } | null>(null);
  // AI 도우미 — 화면 이동 없이 팝업으로만 연다 (2026-09-30 결정)
  const [showAiAssistant, setShowAiAssistant] = useState(false);
  const [infoSlot, setInfoSlot] = useState<HTMLDivElement | null>(null);
  const [actionsSlot, setActionsSlot] = useState<HTMLDivElement | null>(null);
  const headerSlots = useMemo(() => ({ info: infoSlot, actions: actionsSlot }), [infoSlot, actionsSlot]);

  useEffect(() => {
    if (typeof window !== "undefined" && !getToken()) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  // 최초 로그인 비밀번호 변경 강제 — 로그인 화면 리다이렉트를 우회해 대시보드로 바로 와도 여기서 막는다.
  useEffect(() => {
    if (me?.must_change_password) router.replace("/change-password");
  }, [me?.must_change_password, router]);

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Top nav bar — 로고 · 페이지 정보 · 네비 · 페이지 액션 · 사용자 메뉴 */}
      <header className="flex flex-col md:flex-row md:items-center md:h-[60px] gap-2 md:gap-4 px-3 md:px-5 py-2 md:py-0 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center gap-2 md:gap-4 min-w-0 flex-wrap md:flex-nowrap">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="w-[22px] h-[22px] rounded-md bg-gray-900 text-white flex items-center justify-center text-[11px] font-extrabold">
              이
            </div>
            <span className="text-[14px] font-bold tracking-tight text-black hidden sm:inline">이지원천</span>
          </Link>

          {/* 페이지 정보 슬롯 — 마감/신고기한 등 */}
          <div ref={setInfoSlot} className="flex items-center min-w-0 empty:hidden" />

          {/* Nav tabs */}
          <nav className="flex items-center gap-1 shrink-0">
            {NAV_ITEMS.map((item) => {
              const active = item.match(pathname);
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
            <button
              onClick={() => setCertificate({ clientId: new URLSearchParams(window.location.search).get("client_id") })}
              className="px-2.5 sm:px-3 py-1.5 rounded-full text-[12px] sm:text-[13px] font-medium transition-colors text-gray-600 hover:bg-gray-100"
            >
              증명원 발급
            </button>
            {/* AI 도우미 — 클릭해도 화면 이동 없이 팝업으로만 열린다 (2026-09-30 결정) */}
            <button
              onClick={() => setShowAiAssistant(true)}
              className="px-2.5 sm:px-3 py-1.5 rounded-full text-[12px] sm:text-[13px] font-medium transition-colors text-gray-600 hover:bg-gray-100"
            >
              AI 도우미
            </button>
          </nav>
        </div>

        <div className="hidden md:block flex-1" />

        <div className="flex items-center gap-1.5 md:gap-3">
          {/* 페이지 액션 슬롯 — 통합 다운로드 / 급여명세서 등 */}
          <div ref={setActionsSlot} className="flex items-center gap-1.5 flex-wrap empty:hidden" />

          {/* User menu */}
          <div className="relative shrink-0 ml-auto">
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
              {/* "내 정보" — 직원계정 등록/변경·사무실 설정·수임담당지정 3탭 화면으로 이동
                  (plan/14-accounts-permissions.md §6.6). 사무소 설정은 이제 그 탭으로만 존재. */}
              <Link href="/dashboard/staff" onClick={() => setShowMenu(false)} className="block px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50">
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
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 min-w-0 bg-gray-50">
        <div className="p-4 sm:p-6 pb-24">
          <HeaderSlotContext.Provider value={headerSlots}>
            {children}
          </HeaderSlotContext.Provider>
        </div>
      </main>

      {/* 하단 자동화 작업바 (plan/17 §4-9) */}
      <ActivityBar insetLeftMd={pathname.startsWith("/dashboard/filings/")} />

      {certificate && (
        <CertificateIssueModal initialClientId={certificate.clientId} onClose={() => setCertificate(null)} />
      )}

      {showAiAssistant && <AiAssistantDialog onClose={() => setShowAiAssistant(false)} />}
    </div>
  );
}

