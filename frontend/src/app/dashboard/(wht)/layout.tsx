"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { useClients } from "@/lib/queries";

// "원천세 신고" 세부메뉴 — 좌측 칼럼 (plan/08-action-items.md 2026-09-30 "상단 탑 메뉴 전면 개편")
const WHT_SUBMENU = [
  { href: "/dashboard/requests", label: "자료요청", match: (p: string) => p.startsWith("/dashboard/requests") },
  { href: "/dashboard", label: "월별 신고", match: (p: string) => p === "/dashboard" },
  { href: "/dashboard/clients", label: "거래처정보 등록/변경", match: (p: string) => p.startsWith("/dashboard/clients") },
  { href: "/dashboard/employee-changes", label: "사원정보 등록/변경", match: (p: string) => p.startsWith("/dashboard/employee-changes") },
] as const;

// useSearchParams()(client_id 공유)를 쓰므로 Suspense로 감싼다 — 정적 프리렌더 중
// CSR로 넘어가는 구간을 Next.js가 요구한다. 이 경계가 children(각 세부메뉴 페이지)의
// useSearchParams 사용도 함께 커버한다.
export default function WhtLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <WhtLayoutInner>{children}</WhtLayoutInner>
    </Suspense>
  );
}

function WhtLayoutInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedClientId = searchParams.get("client_id");
  const { data: clients, isLoading: clientsLoading } = useClients();
  const [search, setSearch] = useState("");

  const filteredClients = useMemo(() => {
    const list = clients ?? [];
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter((c) => c.business_name.toLowerCase().includes(q));
  }, [clients, search]);

  // 2026-09-30 결정 — 거래처 명단을 전역 좌측 칼럼으로 옮기고, 모든 세부메뉴가 선택된 거래처를
  // 쿼리스트링(client_id)으로 공유한다. 거래처를 선택 안 하면 거래처정보/사원정보는 전체 목록을 보여준다.
  function selectClient(id: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (id === selectedClientId) {
      params.delete("client_id");
    } else {
      params.set("client_id", id);
    }
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  function withClient(href: string): string {
    return selectedClientId ? `${href}?client_id=${selectedClientId}` : href;
  }

  return (
    <div className="-m-4 sm:-m-6 flex" style={{ height: "calc(100dvh - 60px)" }}>
      {/* LEFT — 거래처 명단 (전역, 모든 세부메뉴가 공유) */}
      <aside className="w-[220px] shrink-0 border-r border-gray-200 bg-white flex flex-col">
        <div className="px-3 pt-3 pb-2 space-y-2 border-b border-gray-100">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-gray-900">거래처</span>
            <span className="text-[11px] text-gray-400 tabular-nums">{clients?.length ?? 0}</span>
          </div>
          <input
            type="text"
            placeholder="거래처 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-[12px] placeholder:text-gray-400 outline-none focus:border-blue-500 focus:bg-white"
          />
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {clientsLoading && (
            <div className="text-[12px] text-gray-400 text-center py-4">불러오는 중...</div>
          )}
          {!clientsLoading && filteredClients.length === 0 && (
            <div className="text-[12px] text-gray-400 text-center py-4">
              {search ? "검색 결과 없음" : "등록된 거래처 없음"}
            </div>
          )}
          {filteredClients.map((c) => {
            const active = c.id === selectedClientId;
            return (
              <button
                key={c.id}
                onClick={() => selectClient(c.id)}
                className={`w-full text-left px-3 py-2 rounded-[10px] transition-colors flex items-center gap-2 ${
                  active ? "bg-blue-50 border border-blue-200" : "border border-transparent hover:bg-gray-50"
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${active ? "bg-blue-500" : "bg-gray-300"}`} />
                <span className={`text-[13px] truncate ${active ? "font-semibold text-blue-700" : "text-gray-800"}`}>
                  {c.business_name}
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      {/* 세부메뉴 */}
      <aside className="w-[176px] shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
        <nav className="flex flex-col gap-0.5 p-3">
          {WHT_SUBMENU.map((item) => {
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={withClient(item.href)}
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

      {/* overflow-y-auto: 자체 스크롤 영역을 가진 화면도, 평범한 문서 흐름 화면도 둘 다
          이 안에서 잘리지 않고 보이게 하는 안전한 기본값 */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-y-auto">{children}</div>
    </div>
  );
}
