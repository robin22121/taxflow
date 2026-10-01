"use client";

// 업무미처리내역 — 신고 진행 상황 중 아직 처리 안 된 항목을 한곳에 모아 보여준다.
// 각 항목 클릭 시 처리할 화면으로 바로 이동한다 (2026-10-02 추가 요청).
// 범위: 최신 신고기간의 미수신·자료없음·확인필요 거래처, 급여지급일 미설정 거래처,
// 아직 확인하지 않은 자동화 실패 작업. 미승인 명세서 건수는 신고 상세 화면에서 확인한다.

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { useFilingDashboard, useFilings } from "@/lib/queries";
import { listActivity, previewWehagoUploads } from "@/lib/rpa-api";
import { jobStage } from "@/components/rpa/activity-bar";
import { Badge, Card } from "@/components/ui";
import { koreanPeriod } from "@/lib/format";

export default function PendingTasksPage() {
  const { data: filings } = useFilings();
  const currentFiling = useMemo(
    () => [...(filings ?? [])].sort((a, b) => (a.period > b.period ? -1 : 1))[0] ?? null,
    [filings],
  );
  const filingId = currentFiling?.id ?? "";

  const { data: dashboard } = useFilingDashboard(filingId);
  const { data: preview } = useQuery({
    queryKey: ["rpa", "wehago-preview", filingId],
    queryFn: () => previewWehagoUploads(filingId),
    enabled: Boolean(filingId),
  });
  const { data: failedJobs = [] } = useQuery({
    queryKey: ["rpa", "jobs", "activity", "all", "failed"],
    queryFn: () => listActivity("all", { days: 14, unacknowledged: true }),
    refetchInterval: 10000,
  });

  const sessions = dashboard?.sessions ?? [];
  const sessionIssues = sessions
    .map((s) => {
      const unreceived = s.status === "PENDING" || s.status === "SENT";
      const reasons: string[] = [];
      if (unreceived) reasons.push("미수신");
      if (!unreceived && s.entry_count === 0) reasons.push("자료없음");
      if (s.has_anomalies) reasons.push("확인필요");
      return { ...s, reasons };
    })
    .filter((s) => s.reasons.length > 0);

  const paydayMissing = (preview ?? []).filter((p) => p.blocked_reason === "급여지급일 미설정");
  const failed = failedJobs.filter((j) => j.status === "FAILED");
  const totalCount = sessionIssues.length + paydayMissing.length + failed.length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">업무미처리내역</h1>
        <p className="text-[13px] text-gray-500 mt-1">
          {currentFiling ? `${koreanPeriod(currentFiling.period)} 귀속분 기준 ` : ""}
          항목을 클릭하면 처리할 화면으로 바로 이동합니다.
        </p>
      </div>

      {totalCount === 0 && (
        <Card className="text-center py-10 text-[13px] text-gray-400">처리할 업무가 없습니다.</Card>
      )}

      {currentFiling && sessionIssues.length > 0 && (
        <Card>
          <h2 className="text-[14px] font-semibold text-gray-900 mb-3">
            신고 자료 — {koreanPeriod(currentFiling.period)}
          </h2>
          <div className="divide-y divide-gray-100">
            {sessionIssues.map((s) => (
              <Link
                key={s.client_id}
                href={`/dashboard/filings/${filingId}?client_id=${s.client_id}`}
                className="flex items-center justify-between gap-2 py-2.5 -mx-1 px-1 rounded hover:bg-gray-50"
              >
                <span className="text-[13px] text-gray-900">{s.client_name}</span>
                <span className="flex gap-1.5 shrink-0">
                  {s.reasons.map((r) => (
                    <Badge key={r} tone={r === "미수신" ? "warning" : "danger"}>
                      {r}
                    </Badge>
                  ))}
                </span>
              </Link>
            ))}
          </div>
        </Card>
      )}

      {paydayMissing.length > 0 && (
        <Card>
          <h2 className="text-[14px] font-semibold text-gray-900 mb-3">급여지급일 미설정</h2>
          <div className="divide-y divide-gray-100">
            {paydayMissing.map((p) => {
              const client = sessions.find((s) => s.client_id === p.client_id);
              return (
                <Link
                  key={p.client_id}
                  href={`/dashboard/clients/${p.client_id}?checkPayday=1`}
                  className="flex items-center justify-between gap-2 py-2.5 -mx-1 px-1 rounded hover:bg-gray-50"
                >
                  <span className="text-[13px] text-gray-900">{client?.client_name ?? p.client_id}</span>
                  <Badge tone="danger">급여지급일 미설정</Badge>
                </Link>
              );
            })}
          </div>
        </Card>
      )}

      {failed.length > 0 && (
        <Card>
          <h2 className="text-[14px] font-semibold text-gray-900 mb-3">자동화 실패 작업</h2>
          <div className="divide-y divide-gray-100">
            {failed.map((job) => {
              const stage = jobStage(job);
              const href = job.client_id ? `/dashboard/clients/${job.client_id}` : null;
              const row = (
                <>
                  <span className="text-[13px] text-gray-900">
                    {job.business_name ?? job.requested_by_name ?? "자동화 작업"}
                  </span>
                  <Badge tone="danger">{stage.text}</Badge>
                </>
              );
              return href ? (
                <Link
                  key={job.id}
                  href={href}
                  className="flex items-center justify-between gap-2 py-2.5 -mx-1 px-1 rounded hover:bg-gray-50"
                >
                  {row}
                </Link>
              ) : (
                <div key={job.id} className="flex items-center justify-between gap-2 py-2.5 px-1">
                  {row}
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
