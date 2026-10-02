"use client";

// 위하고 작업 — 이지원(자동화 노트북)이 위하고 T에서 하는 일을 거래처 × 소득구분 × 제작 단위로 보여준다.
// 진행 중인 작업은 현재 단계와 마지막 신호 경과 시간을 보여주고, 신호가 끊기면 "응답 없음"으로 경고한다.
// 칸을 누르면 단계 진행·실패 사유·시각을 본다. 재전송은 신고 상세의 ①/② 버튼에서 한다.

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useConfirm } from "@/components/confirm-dialog";
import { Badge, Button, Card, Modal } from "@/components/ui";
import { useFilings } from "@/lib/queries";
import { koreanPeriod } from "@/lib/format";
import { type RpaJob, type RpaJobKind, createWehagoUploadsSelective, listJobs } from "@/lib/rpa-api";

// 마지막 신호 후 이 시간이 지나면 멈춘 것으로 본다 (서버는 15분 뒤 FAILED 처리).
const STALL_SEC = 120;

const COLUMNS: { key: string; label: string; kind: RpaJobKind | null }[] = [
  { key: "WAGE", label: "근로", kind: "WEHAGO_PAYROLL_INPUT" },
  { key: "BUSINESS", label: "사업", kind: "WEHAGO_BUSINESS_INPUT" },
  { key: "OTHER", label: "기타", kind: "WEHAGO_OTHER_INPUT" },
  { key: "DAILY", label: "일용", kind: null }, // 자동화 없음 — 수동 입력
  { key: "PRODUCTION", label: "제작", kind: "MONTHLY_PRODUCTION" },
];

const STATUS_LABEL: Record<string, string> = {
  PENDING: "대기",
  RUNNING: "진행 중",
  SUCCEEDED: "완료",
  FAILED: "실패",
  CANCELED: "취소",
};

function silenceSec(job: RpaJob, nowMs: number): number | null {
  const last = job.last_progress_at ?? job.claimed_at;
  return last ? Math.max(0, Math.round((nowMs - new Date(last).getTime()) / 1000)) : null;
}

function isStalled(job: RpaJob, nowMs: number): boolean {
  if (job.status !== "RUNNING") return false;
  const s = silenceSec(job, nowMs);
  return s !== null && s >= STALL_SEC;
}

function ago(sec: number): string {
  return sec < 60 ? `${sec}초 전` : `${Math.floor(sec / 60)}분 전`;
}

function Cell({ job, nowMs, onOpen }: { job: RpaJob | undefined; nowMs: number; onOpen: (j: RpaJob) => void }) {
  if (!job) return <span className="text-gray-300">─</span>;
  const stalled = isStalled(job, nowMs);
  const sec = silenceSec(job, nowMs);
  const tone =
    job.status === "FAILED" || stalled
      ? "danger"
      : job.status === "RUNNING"
        ? "info"
        : job.status === "SUCCEEDED"
          ? "success"
          : "neutral";
  return (
    <button type="button" onClick={() => onOpen(job)} className="text-left">
      <Badge tone={tone}>{stalled ? "응답 없음" : STATUS_LABEL[job.status]}</Badge>
      {job.status === "RUNNING" && (
        <div className="mt-1 text-[11px] text-gray-500">
          {job.current_step ?? "시작 중"}
          {sec !== null && ` · ${ago(sec)}`}
        </div>
      )}
    </button>
  );
}

const STEP_STATE_LABEL: Record<string, string> = { done: "완료", running: "진행 중", failed: "실패" };

function JobDetail({ job }: { job: RpaJob }) {
  const steps = Object.entries(job.step_progress ?? {}).filter(([, v]) => typeof v === "string");
  return (
    <div className="space-y-3 text-[13px] text-gray-700">
      <div>
        {job.business_name} · {job.period ? koreanPeriod(job.period) : ""} · {STATUS_LABEL[job.status]}
      </div>
      <dl className="grid grid-cols-[72px_1fr] gap-y-1 text-[12px]">
        <dt className="text-gray-500">요청</dt>
        <dd>{new Date(job.created_at).toLocaleString("ko-KR")}</dd>
        <dt className="text-gray-500">시작</dt>
        <dd>{job.claimed_at ? new Date(job.claimed_at).toLocaleString("ko-KR") : "-"}</dd>
        <dt className="text-gray-500">종료</dt>
        <dd>{job.finished_at ? new Date(job.finished_at).toLocaleString("ko-KR") : "-"}</dd>
        {job.status === "RUNNING" && (
          <>
            <dt className="text-gray-500">현재 단계</dt>
            <dd>{job.current_step ?? "-"}</dd>
          </>
        )}
      </dl>
      {steps.length > 0 && (
        <div>
          <div className="text-[12px] font-semibold text-gray-900 mb-1">단계 진행</div>
          <ul className="space-y-0.5 text-[12px]">
            {steps.map(([k, v]) => (
              <li key={k}>
                {k} — {STEP_STATE_LABEL[String(v)] ?? String(v)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {job.result_message && (
        <div>
          <div className="text-[12px] font-semibold text-gray-900 mb-1">
            {job.status === "FAILED" ? "실패 사유" : "결과"}
          </div>
          <p className="whitespace-pre-wrap rounded bg-gray-50 p-2 text-[12px]">{job.result_message}</p>
        </div>
      )}
    </div>
  );
}

export default function WehagoJobsPage() {
  const { data: filings } = useFilings();
  const sorted = useMemo(
    () => [...(filings ?? [])].sort((a, b) => (a.period > b.period ? -1 : 1)),
    [filings],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const filingId = selected ?? sorted[0]?.id ?? "";

  const { data: jobs = [] } = useQuery({
    queryKey: ["rpa", "jobs", "wehago-jobs", filingId],
    queryFn: () => listJobs(filingId),
    enabled: Boolean(filingId),
    refetchInterval: 4000,
  });

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);

  const [detail, setDetail] = useState<RpaJob | null>(null);
  const [confirm, confirmDialog] = useConfirm();
  const queryClient = useQueryClient();
  const [resendError, setResendError] = useState<string | null>(null);

  // 실패한 입력(전송) 작업만 소득구분 단위로 다시 보낸다 — 성공한 다른 소득구분은 건드리지 않는다.
  const resendType = detail ? COLUMNS.find((c) => c.kind === detail.kind && c.key !== "PRODUCTION") : undefined;
  const canResend = detail?.status === "FAILED" && Boolean(detail.client_id) && resendType !== undefined;

  async function resend() {
    if (!detail?.client_id || !resendType) return;
    const ok = await confirm(
      `${detail.business_name}의 ${resendType.label}소득 자료만 다시 전송합니다.\n` +
        "이전 시도에서 위하고에 일부 저장됐을 수 있으니, 위하고 화면을 먼저 확인했는지 확인해 주세요.",
    );
    if (!ok) return;
    setResendError(null);
    try {
      const [result] = await createWehagoUploadsSelective(filingId, [
        { client_id: detail.client_id, income_types: [resendType.key] },
      ]);
      if (result?.skipped_reason) {
        setResendError(result.skipped_reason);
        return;
      }
      await queryClient.invalidateQueries({ queryKey: ["rpa", "jobs"] });
      setDetail(null);
    } catch (e) {
      setResendError(e instanceof Error ? e.message : "재전송에 실패했습니다.");
    }
  }

  // 거래처별로 종류마다 가장 최근 작업만 칸에 올린다.
  const rows = useMemo(() => {
    const byClient = new Map<string, { name: string; latest: Map<RpaJobKind, RpaJob> }>();
    const ordered = [...jobs].sort((a, b) => a.created_at.localeCompare(b.created_at));
    for (const job of ordered) {
      if (!job.client_id) continue;
      const row = byClient.get(job.client_id) ?? { name: job.business_name, latest: new Map() };
      row.latest.set(job.kind, job);
      byClient.set(job.client_id, row);
    }
    return [...byClient.entries()].map(([clientId, v]) => ({ clientId, ...v }));
  }, [jobs]);

  const running = jobs.filter((j) => j.status === "RUNNING");
  const pending = jobs.filter((j) => j.status === "PENDING").length;
  const stalledJobs = running.filter((j) => isStalled(j, nowMs));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">위하고 작업</h1>
          <p className="text-[13px] text-gray-500 mt-1">
            이지원이 위하고 T에서 진행하는 작업의 현재 단계와 실패 사유를 확인합니다.
          </p>
        </div>
        <select
          value={filingId}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-[13px]"
        >
          {sorted.map((f) => (
            <option key={f.id} value={f.id}>
              {koreanPeriod(f.period)} 귀속
            </option>
          ))}
        </select>
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[13px]">
          <span>
            진행 중 <b>{running.length}</b>건
          </span>
          <span>
            대기 <b>{pending}</b>건
          </span>
          {stalledJobs.length > 0 && (
            <span className="text-red-600">
              ⚠ {stalledJobs.length}건이 {Math.round(STALL_SEC / 60)}분 넘게 신호가 없습니다 — 이지원 노트북을 확인하세요.
            </span>
          )}
        </div>
        {running.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-[12px] text-gray-600">
            {running.map((j) => {
              const sec = silenceSec(j, nowMs);
              return (
                <li key={j.id}>
                  {j.business_name} — {j.current_step ?? "시작 중"}
                  {sec !== null && ` (마지막 신호 ${ago(sec)})`}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card className="overflow-x-auto">
        {rows.length === 0 ? (
          <div className="py-10 text-center text-[13px] text-gray-400">
            이 귀속월에 요청된 위하고 작업이 없습니다.
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-200 text-left text-[12px] text-gray-500">
                <th className="py-2 pr-4 font-medium">거래처</th>
                {COLUMNS.map((c) => (
                  <th key={c.key} className="py-2 pr-4 font-medium">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((row) => (
                <tr key={row.clientId}>
                  <td className="py-2.5 pr-4 text-gray-900">{row.name}</td>
                  {COLUMNS.map((c) => (
                    <td key={c.key} className="py-2.5 pr-4 align-top">
                      {c.kind === null ? (
                        <span className="text-[12px] text-gray-400">수동</span>
                      ) : (
                        <Cell job={row.latest.get(c.kind)} nowMs={nowMs} onOpen={setDetail} />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Modal
        open={detail !== null}
        onClose={() => {
          setDetail(null);
          setResendError(null);
        }}
        title="작업 상세"
        footer={canResend ? <Button onClick={resend}>이 항목만 재전송</Button> : undefined}
      >
        {detail && <JobDetail job={detail} />}
        {resendError && <p className="mt-3 text-[12px] text-red-600">{resendError}</p>}
      </Modal>
      {confirmDialog}
    </div>
  );
}
