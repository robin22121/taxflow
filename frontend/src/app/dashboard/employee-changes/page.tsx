"use client";

import { useState } from "react";

import { useEmployeeChanges, useReviewEmployeeChange } from "@/lib/queries";
import { Badge, Button, Card } from "@/components/ui";
import type { EmployeeChangeRequest } from "@/lib/types";

export default function EmployeeChangesPage() {
  const [scope, setScope] = useState<"PENDING" | "ALL">("PENDING");
  const { data, isLoading } = useEmployeeChanges(scope);
  const review = useReviewEmployeeChange();
  const [acting, setActing] = useState<string | null>(null);

  const rows = data ?? [];

  async function act(request: EmployeeChangeRequest, action: "approve" | "reject") {
    setActing(request.id);
    try {
      await review.mutateAsync({ requestId: request.id, action });
    } finally {
      setActing(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight text-gray-900">직원 변동 승인</h1>
          <p className="text-[12px] text-gray-500 mt-1">
            사장님이 포털에서 알린 입·퇴사입니다. 승인해야 직원 마스터에 반영됩니다.
          </p>
        </div>
        <div className="flex gap-1.5">
          {(["PENDING", "ALL"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setScope(value)}
              className={
                "px-3 py-1.5 rounded-full text-[12px] font-medium transition-colors " +
                (scope === value ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-100")
              }
            >
              {value === "PENDING" ? "대기 중" : "전체"}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-[14px] bg-white animate-pulse border border-gray-200" />
          ))}
        </div>
      )}

      {!isLoading && rows.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-[13px] text-gray-500">
            {scope === "PENDING" ? "대기 중인 변동 통보가 없습니다." : "통보 기록이 없습니다."}
          </p>
        </Card>
      )}

      <div className="space-y-2">
        {rows.map((row) => (
          <Card key={row.id} className="p-4">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge tone={row.change_type === "HIRE" ? "info" : "neutral"}>
                    {row.change_type === "HIRE" ? "입사" : "퇴사"}
                  </Badge>
                  <span className="text-[14px] font-bold text-gray-900">{row.name}</span>
                  <span className="text-[12px] text-gray-500">{row.client_name}</span>
                  {row.status !== "PENDING" && (
                    <Badge tone={row.status === "APPROVED" ? "success" : "danger"}>
                      {row.status === "APPROVED" ? "승인됨" : "반려됨"}
                    </Badge>
                  )}
                </div>
                <div className="text-[12px] text-gray-600 mt-1">
                  {row.change_type === "HIRE"
                    ? `입사일 ${row.hired_at ?? "미기재"}`
                    : `마지막 근무일 ${row.resigned_at ?? "미기재"}`}
                  {row.note ? ` · ${row.note}` : ""}
                </div>
                {row.change_type === "HIRE" && row.status === "PENDING" && (
                  <div className="text-[11px] text-amber-700 mt-1">
                    자격취득 신고는 입사일로부터 14일 이내입니다.
                  </div>
                )}
              </div>

              {row.status === "PENDING" && (
                <div className="flex gap-2 shrink-0">
                  <Button
                    variant="secondary"
                    onClick={() => act(row, "reject")}
                    disabled={acting === row.id}
                  >
                    반려
                  </Button>
                  <Button onClick={() => act(row, "approve")} disabled={acting === row.id}>
                    {acting === row.id ? "처리중..." : "승인"}
                  </Button>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
