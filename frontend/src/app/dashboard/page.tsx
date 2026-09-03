"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useClients, useCreateFiling, useFilings } from "@/lib/queries";
import { Badge, Button } from "@/components/ui";

export default function DashboardHomePage() {
  const router = useRouter();
  const { data: filings, isLoading: filingsLoading } = useFilings();
  const { data: clients, isLoading: clientsLoading } = useClients();
  const createFiling = useCreateFiling();
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const sortedFilings = useMemo(
    () => [...(filings ?? [])].sort((a, b) => (a.period > b.period ? -1 : 1)),
    [filings],
  );
  const filteredClients = useMemo(() => {
    const list = clients ?? [];
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter((c) => c.business_name.toLowerCase().includes(q));
  }, [clients, search]);

  const selectedClient = clients?.find((c) => c.id === selectedClientId) ?? null;
  const nextPeriod = previousPeriod();
  const alreadyExists = sortedFilings.some((f) => f.period === nextPeriod);

  function addNext() {
    if (alreadyExists) return;
    createFiling.mutate(nextPeriod, {
      onError: (e) => alert((e as Error).message),
    });
  }

  function openFiling(filingId: string) {
    const url = selectedClientId
      ? `/dashboard/filings/${filingId}?client_id=${selectedClientId}`
      : `/dashboard/filings/${filingId}`;
    router.push(url);
  }

  return (
    <div className="-m-4 sm:-m-6 flex flex-col" style={{ height: "calc(100dvh - 60px)" }}>
      {/* Body — clients sidebar + monthly filings list */}
      <div className="flex-1 flex min-h-0 bg-gray-50">
        {/* LEFT — 거래처 sidebar */}
        <aside className="w-[240px] border-r border-gray-200 bg-white flex flex-col shrink-0">
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
                  onClick={() => setSelectedClientId(active ? null : c.id)}
                  className={`w-full text-left px-3 py-2 rounded-[10px] transition-colors flex items-center gap-2 ${
                    active
                      ? "bg-blue-50 border border-blue-200"
                      : "border border-transparent hover:bg-gray-50"
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

        {/* CENTER — 월별신고내역 리스트 */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
            {/* Title */}
            <div className="mb-4">
              <h1 className="text-[18px] font-bold tracking-tight text-gray-900">
                {selectedClient ? `${selectedClient.business_name} · 월별 신고 내역` : "월별 신고 내역"}
              </h1>
              {!selectedClient && (
                <p className="text-[12px] text-gray-500 mt-1">
                  좌측에서 거래처를 선택하면 해당 업체의 신고를 바로 열 수 있어요.
                </p>
              )}
            </div>

            <div className="bg-white border border-gray-200 rounded-[14px] overflow-hidden">
              {/* 맨 상단: 새로운 신고추가 */}
              <button
                onClick={addNext}
                disabled={createFiling.isPending || alreadyExists}
                className={`w-full flex items-center gap-3 px-4 py-3.5 border-b border-gray-100 text-left transition-colors ${
                  alreadyExists
                    ? "bg-gray-50 cursor-not-allowed text-gray-400"
                    : "hover:bg-blue-50/40 text-blue-700"
                }`}
              >
                <span className={`w-7 h-7 rounded-full flex items-center justify-center text-[15px] font-bold shrink-0 ${
                  alreadyExists ? "bg-gray-200 text-gray-400" : "bg-blue-100 text-blue-600"
                }`}>
                  +
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-[14px] font-semibold">
                    {alreadyExists
                      ? `${koreanPeriod(nextPeriod)} 신고는 이미 생성됨`
                      : createFiling.isPending
                        ? "생성 중..."
                        : `새로운 신고 추가 (${koreanPeriod(nextPeriod)} 신고)`}
                  </span>
                  {!alreadyExists && (
                    <span className="block text-[11.5px] text-gray-500 font-normal mt-0.5">
                      클릭하면 {koreanPeriod(nextPeriod)} 신고 기간을 새로 만듭니다
                    </span>
                  )}
                </span>
              </button>

              {/* Existing filings */}
              {filingsLoading && (
                <div className="px-4 py-8 text-center text-[12px] text-gray-400">불러오는 중...</div>
              )}

              {!filingsLoading && sortedFilings.length === 0 && (
                <div className="px-4 py-10 text-center">
                  <div className="text-3xl mb-2 opacity-30">📋</div>
                  <p className="text-[13px] text-gray-500">아직 생성된 신고 기간이 없습니다</p>
                </div>
              )}

              {!filingsLoading &&
                sortedFilings.map((f) => {
                  const done = f.status === "COMPLETED" || f.status === "FILED";
                  return (
                    <button
                      key={f.id}
                      onClick={() => openFiling(f.id)}
                      className="w-full flex items-center gap-3 px-4 py-3.5 border-b border-gray-50 last:border-b-0 hover:bg-blue-50/40 transition-colors text-left"
                    >
                      <span className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 tabular-nums ${
                        done ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"
                      }`}>
                        {f.period.split("-")[1]}월
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block text-[14px] font-semibold text-gray-900">
                          {koreanPeriod(f.period)} {done ? "신고내역 보기" : "신고하기"}
                        </span>
                        <span className="flex items-center gap-2 mt-0.5">
                          <Badge tone={statusTone(f.status)}>{statusKo(f.status)}</Badge>
                          <span className="text-[11.5px] text-gray-500 tabular-nums">
                            거래처 {f.total_clients} · 항목 {f.total_entries}
                          </span>
                        </span>
                      </span>
                      <span className="text-gray-300 text-[14px] shrink-0">›</span>
                    </button>
                  );
                })}
            </div>

            {selectedClient && (
              <p className="mt-3 text-[11px] text-gray-400 text-center">
                클릭하면 <strong className="text-gray-600">{selectedClient.business_name}</strong>의 해당 월 신고로 이동합니다.
              </p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function previousPeriod(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function koreanPeriod(period: string): string {
  const [y, m] = period.split("-");
  return `${y}년 ${Number(m)}월분`;
}

function statusKo(s: string): string {
  return (
    {
      DRAFT: "준비",
      COLLECTING: "수집중",
      REVIEWING: "검증중",
      APPROVED: "승인",
      EXCEL_GENERATED: "엑셀 생성됨",
      FILED: "신고 완료",
      COMPLETED: "완료",
    }[s] ?? s
  );
}

function statusTone(s: string): "neutral" | "info" | "warning" | "success" {
  if (s === "COMPLETED" || s === "FILED") return "success";
  if (s === "REVIEWING" || s === "EXCEL_GENERATED") return "warning";
  if (s === "COLLECTING") return "info";
  return "neutral";
}
