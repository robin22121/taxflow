"use client";

import Link from "next/link";
import { useState } from "react";

import { useCreateFiling, useFilings } from "@/lib/queries";
import { Badge, Button, Card, Input } from "@/components/ui";

export default function DashboardHomePage() {
  const { data, isLoading } = useFilings();
  const createFiling = useCreateFiling();
  const [period, setPeriod] = useState(currentPeriod());

  const filings = data ?? [];

  // KPI calculations
  const activeFiling = filings.find(
    (f) => f.status !== "COMPLETED" && f.status !== "FILED",
  );
  const totalClients = activeFiling?.total_clients ?? 0;
  const totalEntries = activeFiling?.total_entries ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight">월별 신고</h1>
          <p className="text-[13px] text-ink-3 mt-0.5">기간을 선택해 자료 수집을 시작하세요.</p>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            createFiling.mutate(period);
          }}
        >
          <Input
            type="text"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            placeholder="YYYY-MM"
            pattern="\d{4}-\d{2}"
            className="w-32"
          />
          <Button disabled={createFiling.isPending}>새 기간 생성</Button>
        </form>
      </div>

      {/* KPI Cards */}
      {activeFiling && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="총 거래처" value={String(totalClients)} unit="곳" />
          <KpiCard
            label="이번달 수집률"
            value={totalClients > 0 ? String(Math.round((totalEntries / Math.max(totalClients, 1)) * 100)) : "0"}
            unit="%"
          />
          <KpiCard label="전체 항목" value={String(totalEntries)} unit="건" />
          <KpiCard
            label="현재 상태"
            value={statusKo(activeFiling.status)}
            tone={statusTone(activeFiling.status)}
          />
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-[14px] bg-paper animate-pulse border border-ink-5" />
          ))}
        </div>
      )}

      {/* Filing Table */}
      {!isLoading && filings.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-ink-4">
                <th className="text-left px-4 py-3 text-[11px] font-medium text-ink-3 uppercase tracking-wider">기간</th>
                <th className="text-left px-4 py-3 text-[11px] font-medium text-ink-3 uppercase tracking-wider">상태</th>
                <th className="text-right px-4 py-3 text-[11px] font-medium text-ink-3 uppercase tracking-wider">거래처</th>
                <th className="text-right px-4 py-3 text-[11px] font-medium text-ink-3 uppercase tracking-wider">항목</th>
              </tr>
            </thead>
            <tbody>
              {filings.map((f) => (
                <tr key={f.id} className="border-b border-paper-2 hover:bg-paper-2 transition-colors">
                  <td className="px-4 py-3">
                    <Link href={`/dashboard/filings/${f.id}`} className="font-medium text-ink hover:text-accent transition-colors">
                      {f.period}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(f.status)}>{statusKo(f.status)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right t-num text-ink-2">{f.total_clients}</td>
                  <td className="px-4 py-3 text-right t-num text-ink-2">{f.total_entries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Empty state */}
      {!isLoading && filings.length === 0 && (
        <Card className="text-center py-12">
          <div className="text-4xl mb-3 opacity-30">📋</div>
          <p className="text-[15px] font-medium text-ink-2 mb-1">아직 생성된 신고 기간이 없습니다</p>
          <p className="text-[13px] text-ink-3">위 입력란에서 기간을 입력하고 [새 기간 생성]을 눌러 시작하세요.</p>
        </Card>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "neutral" | "info" | "warning" | "success";
}) {
  return (
    <Card className="py-3 px-4">
      <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider mb-1">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-[22px] font-bold tracking-tight t-num">{value}</span>
        {unit && <span className="text-[13px] text-ink-3">{unit}</span>}
        {tone && !unit && (
          <Badge tone={tone}>{value}</Badge>
        )}
      </div>
    </Card>
  );
}

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
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
