"use client";

import Link from "next/link";
import { useState } from "react";

import { useCreateFiling, useFilings } from "@/lib/queries";
import { Badge, Button, Card, Input } from "@/components/ui";

export default function DashboardHomePage() {
  const { data, isLoading } = useFilings();
  const createFiling = useCreateFiling();
  const [period, setPeriod] = useState(currentPeriod());

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">월별 신고</h1>
          <p className="text-sm text-gray-500">기간을 선택해 자료 수집을 시작하세요.</p>
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

      {isLoading && <p>로딩 중...</p>}

      <div className="grid gap-3">
        {(data ?? []).map((f) => (
          <Link key={f.id} href={`/dashboard/filings/${f.id}`}>
            <Card className="flex items-center justify-between hover:border-blue-400 transition-colors">
              <div>
                <div className="text-lg font-medium">{f.period}</div>
                <div className="text-xs text-gray-500">
                  거래처 {f.total_clients} · 항목 {f.total_entries}
                </div>
              </div>
              <Badge tone={statusTone(f.status)}>{statusKo(f.status)}</Badge>
            </Card>
          </Link>
        ))}
        {data?.length === 0 && (
          <Card>
            <p className="text-sm text-gray-500">아직 생성된 신고 기간이 없습니다.</p>
          </Card>
        )}
      </div>
    </div>
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
