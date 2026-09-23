"use client";

// 화면 하단 자동화 작업바 — plan/17-certificate-issuance.md §4-9.
//
// 맨 왼쪽 [전체 작업 내역] + 진행중·미확인 작업 칩. 칩 클릭 → 상세 팝업,
// 끝난 작업은 [확인]을 누르면 바에서 사라지고 전체 내역에만 남는다.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { CertificateIssueModal } from "@/components/certificates/certificate-issue-modal";
import { Button, Modal } from "@/components/ui";
import { type RpaJob, acknowledgeJob, importProgress, listJobs, listUnacknowledgedJobs } from "@/lib/rpa-api";

type Tone = "wait" | "run" | "done" | "fail";

// MONTHLY_PRODUCTION 하위 단계 (backend RpaJob.step_progress 키)
const PRODUCTION_STEPS: { key: string; label: string }[] = [
  { key: "wehago_income_tax", label: "원천세 신고서 입력" },
  { key: "wehago_local_tax", label: "지방소득세 신고서 입력" },
  { key: "hometax", label: "홈택스 원천세 신고" },
  { key: "wetax", label: "위택스 지방세 신고" },
  { key: "published", label: "납부서 전송" },
];

const KIND_LABEL: Record<string, string> = {
  WEHAGO_PAYROLL_INPUT: "위하고 급여자료 입력",
  MONTHLY_PRODUCTION: "원천세 신고",
  CERTIFICATE_ISSUE: "증명서 발급",
  WEHAGO_MASTER_IMPORT_ALL: "위하고 전체 가져오기",
  WEHAGO_CLIENT_IMPORT: "위하고 가져오기",
};

function isFinished(job: RpaJob) {
  return job.status !== "PENDING" && job.status !== "RUNNING";
}

/** 칩에 보일 한 줄 상태 — 예) "원천세 신고서 입력중", "원천세 신고완료", "납부서 전송완료". */
export function jobStage(job: RpaJob): { text: string; tone: Tone } {
  const steps = job.step_progress ?? {};
  if (job.kind === "MONTHLY_PRODUCTION") {
    if (steps.published === "done") return { text: "납부서 전송완료", tone: "done" };
    if (job.status === "PENDING") return { text: "원천세 신고 대기", tone: "wait" };
    if (job.status === "RUNNING") {
      const current = PRODUCTION_STEPS.find((s) => steps[s.key] === "running");
      return { text: `${current?.label ?? "원천세 신고"}중`, tone: "run" };
    }
    if (job.status === "SUCCEEDED") return { text: "원천세 신고완료", tone: "done" };
    if (job.status === "FAILED") return { text: "원천세 신고 실패", tone: "fail" };
    return { text: "원천세 신고 취소", tone: "wait" };
  }
  if (job.kind === "CERTIFICATE_ISSUE" && steps.delivered === "done") return { text: "고객발송 완료", tone: "done" };
  if (job.kind === "WEHAGO_MASTER_IMPORT_ALL" && job.status === "RUNNING") {
    const { total, clients } = importProgress(job);
    return { text: `위하고 전체 가져오기 ${clients.length}${total ? `/${total}` : ""}곳`, tone: "run" };
  }
  const kind = KIND_LABEL[job.kind] ?? job.kind;
  switch (job.status) {
    case "PENDING": return { text: `${kind} 대기`, tone: "wait" };
    case "RUNNING": return { text: `${kind} 진행중`, tone: "run" };
    case "SUCCEEDED": return { text: `${kind} 완료`, tone: "done" };
    case "FAILED": return { text: `${kind} 실패`, tone: "fail" };
    default: return { text: `${kind} 취소`, tone: "wait" };
  }
}

const TONE_CLASS: Record<Tone, string> = {
  wait: "border-gray-200 bg-gray-50 text-gray-600",
  run: "border-blue-200 bg-blue-50 text-blue-700",
  done: "border-emerald-200 bg-emerald-50 text-emerald-700",
  fail: "border-red-200 bg-red-50 text-red-700",
};

const DOT_CLASS: Record<Tone, string> = {
  wait: "bg-gray-400",
  run: "bg-blue-500 animate-pulse",
  done: "bg-emerald-500",
  fail: "bg-red-500",
};

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ActivityBar() {
  const qc = useQueryClient();
  const [detail, setDetail] = useState<RpaJob | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [certJobId, setCertJobId] = useState<string | null>(null);

  const { data: jobs = [] } = useQuery({
    queryKey: ["rpa", "jobs", "unacknowledged"],
    queryFn: listUnacknowledgedJobs,
    refetchInterval: 5000,
  });

  const ack = useMutation({
    mutationFn: acknowledgeJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rpa", "jobs"] });
      setDetail(null);
    },
  });

  return (
    <>
      <div className="fixed bottom-0 inset-x-0 z-30 h-11 border-t border-gray-200 bg-white/95 backdrop-blur flex items-center gap-2 px-3 md:px-5">
        <button
          onClick={() => setShowAll(true)}
          className="shrink-0 px-2.5 py-1 rounded-full border border-gray-300 text-[12px] font-medium text-gray-700 hover:bg-gray-50"
        >
          전체 작업 내역
        </button>
        <div className="flex-1 min-w-0 flex items-center gap-1.5 overflow-x-auto">
          {jobs.length === 0 && <span className="text-[11.5px] text-gray-400">진행 중인 자동화 작업이 없습니다</span>}
          {jobs.map((job) => {
            const stage = jobStage(job);
            return (
              <button
                key={job.id}
                onClick={() => setDetail(job)}
                className={"shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[12px] font-medium " + TONE_CLASS[stage.tone]}
              >
                <span className={"w-1.5 h-1.5 rounded-full " + DOT_CLASS[stage.tone]} />
                <span>{job.business_name}</span>
                <span className="font-normal">{stage.text}</span>
              </button>
            );
          })}
        </div>
      </div>

      {detail && (
        <JobDetailModal
          job={detail}
          onClose={() => setDetail(null)}
          onAck={() => ack.mutate(detail.id)}
          acking={ack.isPending}
          onOpenCertificate={() => { setCertJobId(detail.id); setDetail(null); }}
        />
      )}
      {certJobId && <CertificateIssueModal jobId={certJobId} onClose={() => setCertJobId(null)} />}
      {showAll && <AllJobsModal onClose={() => setShowAll(false)} onPick={(job) => { setShowAll(false); setDetail(job); }} />}
    </>
  );
}

function JobDetailModal({ job, onClose, onAck, acking, onOpenCertificate }: {
  job: RpaJob; onClose: () => void; onAck: () => void; acking: boolean; onOpenCertificate: () => void;
}) {
  const stage = jobStage(job);
  const steps = job.step_progress ?? {};
  const shownSteps = PRODUCTION_STEPS.filter((s) => s.key in steps);
  const canAck = isFinished(job) && !job.acknowledged_at;

  return (
    <Modal
      open
      onClose={onClose}
      title={`${job.business_name} · ${KIND_LABEL[job.kind] ?? job.kind}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>닫기</Button>
        {job.kind === "CERTIFICATE_ISSUE" && (
          <Button variant="secondary" onClick={onOpenCertificate}>{isFinished(job) ? "다음 작업" : "진행 보기"}</Button>
        )}
        {canAck && <Button onClick={onAck} disabled={acking}>{acking ? "처리중..." : "확인"}</Button>}
      </>}
    >
      <div className="space-y-3 text-[12.5px]">
        <div className={"inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border font-medium " + TONE_CLASS[stage.tone]}>
          <span className={"w-1.5 h-1.5 rounded-full " + DOT_CLASS[stage.tone]} />
          {stage.text}
        </div>
        <dl className="grid grid-cols-[84px_1fr] gap-y-1.5 text-gray-700">
          <dt className="text-gray-400">사업자번호</dt><dd>{job.business_number ?? "—"}</dd>
          {job.period && <><dt className="text-gray-400">귀속월</dt><dd>{job.period}</dd></>}
          <dt className="text-gray-400">요청</dt><dd>{fmt(job.created_at)}</dd>
          <dt className="text-gray-400">시작</dt><dd>{fmt(job.claimed_at)}</dd>
          <dt className="text-gray-400">종료</dt><dd>{fmt(job.finished_at)}</dd>
        </dl>
        {shownSteps.length > 0 && (
          <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
            {shownSteps.map((s) => (
              <div key={s.key} className="flex items-center justify-between px-3 py-1.5">
                <span className="text-gray-700">{s.label}</span>
                <span className="text-[11px] text-gray-500">{STEP_STATE[String(steps[s.key])] ?? String(steps[s.key])}</span>
              </div>
            ))}
          </div>
        )}
        {job.result_message && (
          <p className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2 text-gray-600 whitespace-pre-wrap">{job.result_message}</p>
        )}
        {!isFinished(job) && <p className="text-[11.5px] text-gray-400">진행 중인 작업은 끝난 뒤에 확인 처리할 수 있습니다.</p>}
      </div>
    </Modal>
  );
}

const STEP_STATE: Record<string, string> = {
  pending: "대기",
  running: "진행중",
  done: "완료",
  failed: "실패",
};

function AllJobsModal({ onClose, onPick }: { onClose: () => void; onPick: (job: RpaJob) => void }) {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["rpa", "jobs", "all"],
    queryFn: () => listJobs(),
  });

  return (
    <Modal open onClose={onClose} size="lg" title="전체 작업 내역"
      footer={<Button variant="ghost" onClick={onClose}>닫기</Button>}>
      {isLoading ? (
        <p className="text-[12.5px] text-gray-400">불러오는 중...</p>
      ) : !jobs?.length ? (
        <p className="text-[12.5px] text-gray-400">아직 자동화 작업이 없습니다.</p>
      ) : (
        <div className="max-h-[60vh] overflow-y-auto -mx-1">
          <table className="w-full text-[12px]">
            <thead className="text-gray-400 text-left sticky top-0 bg-white">
              <tr><th className="px-2 py-1.5 font-medium">요청</th><th className="px-2 py-1.5 font-medium">거래처</th><th className="px-2 py-1.5 font-medium">귀속월·종류</th><th className="px-2 py-1.5 font-medium">상태</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {jobs.map((job) => {
                const stage = jobStage(job);
                return (
                  <tr key={job.id} onClick={() => onPick(job)} className="cursor-pointer hover:bg-gray-50">
                    <td className="px-2 py-1.5 text-gray-500 whitespace-nowrap">{fmt(job.created_at)}</td>
                    <td className="px-2 py-1.5 text-gray-800">{job.business_name}</td>
                    <td className="px-2 py-1.5 text-gray-500">{job.period ?? KIND_LABEL[job.kind] ?? ""}</td>
                    <td className="px-2 py-1.5">
                      <span className={"inline-flex items-center gap-1 px-2 py-0.5 rounded-full border " + TONE_CLASS[stage.tone]}>
                        <span className={"w-1.5 h-1.5 rounded-full " + DOT_CLASS[stage.tone]} />{stage.text}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
