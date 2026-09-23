"use client";

// 위하고 → 이지원천 가져오기 — 수임처 기본사항 + 사원 기본사항 (plan/16 §12).
//
// 1. 개별 가져오기: 사업자번호 1건. 누구나.
// 2. 전체 가져오기: 위하고의 모든 수임처. 사무소 관리자만 — 오래 걸리고 그동안 자동화 PC 가 다른 작업을 못 한다.
// 이미 있는 값은 덮지 않고 빈 칸만 채운다. 값이 다른 항목은 결과에 따로 보여준다.

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, Input, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { digitsOnly, formatBizNumber } from "@/lib/format";
import { useMe } from "@/lib/queries";
import {
  type ImportClientEntry,
  type RpaJob,
  createClientImport,
  createMasterImport,
  importProgress,
  listImports,
} from "@/lib/rpa-api";

const ACTIVE = new Set(["PENDING", "RUNNING"]);

const STATUS_TEXT: Record<string, string> = {
  PENDING: "자동화 PC 대기",
  RUNNING: "가져오는 중",
  SUCCEEDED: "완료",
  FAILED: "실패",
  CANCELED: "취소",
};

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : "요청에 실패했습니다.";
}

export function WehagoImportModal({
  onClose,
  initialBusinessNumber = "",
}: {
  onClose: () => void;
  initialBusinessNumber?: string;
}) {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: jobs = [] } = useQuery({
    queryKey: ["rpa", "imports"],
    queryFn: listImports,
    // 진행 중인 가져오기가 있을 때만 5초마다 새로 본다
    refetchInterval: (q) => ((q.state.data ?? []).some((j) => ACTIVE.has(j.status)) ? 5000 : false),
  });

  // 가져오기가 끝나면 거래처 목록을 새로 받는다
  const activeCount = jobs.filter((j) => ACTIVE.has(j.status)).length;
  const prevActive = useRef(activeCount);
  useEffect(() => {
    if (activeCount < prevActive.current) qc.invalidateQueries({ queryKey: ["clients"] });
    prevActive.current = activeCount;
  }, [activeCount, qc]);

  const [bn, setBn] = useState(initialBusinessNumber);
  const one = useMutation({
    mutationFn: () => createClientImport(digitsOnly(bn)),
    onSuccess: () => {
      setBn("");
      qc.invalidateQueries({ queryKey: ["rpa"] });
    },
  });

  const [agreed, setAgreed] = useState(false);
  const all = useMutation({
    mutationFn: createMasterImport,
    onSuccess: () => {
      setAgreed(false);
      qc.invalidateQueries({ queryKey: ["rpa"] });
    },
  });
  const allRunning = jobs.some((j) => j.kind === "WEHAGO_MASTER_IMPORT_ALL" && ACTIVE.has(j.status));

  return (
    <Modal open onClose={onClose} size="lg" title="위하고에서 가져오기">
      <div className="space-y-5 text-[13px]">
        <p className="text-gray-500">
          위하고 T 의 수임처 기본사항(상호·사업자번호·대표자·업태·종목·주소)과 사원 기본사항(사원코드·이름·주민번호·입퇴사일·부서·직급)을
          자동화 PC 가 가져옵니다. 이지원천에 이미 있는 값은 덮어쓰지 않고 빈 칸만 채우며, 값이 다른 항목은 결과에 표시합니다.
          사원코드는 위하고 급여 업로드에 쓰이므로 위하고 값으로 맞춥니다.
        </p>

        {/* 1. 개별 */}
        <section className="space-y-2">
          <h3 className="text-[13px] font-semibold text-gray-900">개별 수임처 가져오기</h3>
          <div className="flex gap-2">
            <Input
              placeholder="사업자번호 (예: 224-02-38407)"
              value={bn}
              onChange={(e) => setBn(e.target.value)}
              maxLength={12}
              className="max-w-xs"
            />
            <Button
              onClick={() => one.mutate()}
              disabled={digitsOnly(bn).length !== 10 || one.isPending || allRunning}
              className="shrink-0"
            >
              가져오기
            </Button>
          </div>
          {allRunning && <p className="text-[12px] text-gray-400">전체 가져오기가 끝난 뒤 사용할 수 있습니다.</p>}
          {one.isError && <p className="text-[12px] text-red-600">{errorText(one.error)}</p>}
        </section>

        {/* 2. 전체 */}
        <section className="space-y-2">
          <h3 className="text-[13px] font-semibold text-gray-900">전체 수임처 가져오기</h3>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1.5 text-[12px] text-amber-900">
            <p className="font-semibold">시간이 오래 걸립니다 — 사무소 관리자 허가 후 실행하세요.</p>
            <ul className="list-disc pl-4 space-y-0.5">
              <li>위하고에 등록된 모든 수임처를 하나씩 열어 가져오므로 수임처 수에 따라 수십 분~수 시간 걸립니다.</li>
              <li>그동안 자동화 PC 는 위하고 급여 전송 등 다른 작업을 하지 않습니다. 업무 시간 외(야간·주말) 실행을 권장합니다.</li>
              <li>수임처마다 바로 저장되므로 중간에 멈춰도 끝난 수임처는 남습니다.</li>
            </ul>
          </div>
          {me?.is_admin ? (
            <div className="flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-[12px] text-gray-700">
                <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                관리자로서 위 내용을 확인했고 전체 가져오기를 허가합니다.
              </label>
              <Button
                variant="secondary"
                onClick={() => all.mutate()}
                disabled={!agreed || all.isPending || allRunning}
                className="shrink-0"
              >
                전체 가져오기 시작
              </Button>
            </div>
          ) : (
            <p className="text-[12px] text-gray-500">전체 가져오기는 사무소 관리자만 실행할 수 있습니다. 관리자에게 요청하세요.</p>
          )}
          {all.isError && <p className="text-[12px] text-red-600">{errorText(all.error)}</p>}
        </section>

        {/* 최근 가져오기 */}
        <section className="space-y-2">
          <h3 className="text-[13px] font-semibold text-gray-900">최근 가져오기</h3>
          {jobs.length === 0 && <p className="text-[12px] text-gray-400">아직 가져온 적이 없습니다.</p>}
          <div className="space-y-2 max-h-[40vh] overflow-y-auto">
            {jobs.map((j) => <ImportJobRow key={j.id} job={j} />)}
          </div>
        </section>
      </div>
    </Modal>
  );
}

function ImportJobRow({ job }: { job: RpaJob }) {
  const [open, setOpen] = useState(false);
  const { total, clients } = importProgress(job);
  const done = clients.length;
  const failed = clients.filter((c) => c.status === "FAILED").length;
  const conflicts = clients.reduce((n, c) => n + (c.conflicts?.length ?? 0), 0);
  const isAll = job.kind === "WEHAGO_MASTER_IMPORT_ALL";

  return (
    <div className="rounded-lg border border-gray-200">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full px-3 py-2 text-left hover:bg-gray-50">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-gray-900">
            {isAll ? "전체 수임처" : job.business_name}
            {!isAll && job.business_number && (
              <span className="ml-1.5 text-gray-400 t-num">{formatBizNumber(job.business_number)}</span>
            )}
          </span>
          <span className="text-[12px] text-gray-500">
            {STATUS_TEXT[job.status] ?? job.status}
            {isAll && ` · ${done}${total ? `/${total}` : ""}곳`}
            {failed > 0 && <span className="text-red-600"> · 실패 {failed}</span>}
            {conflicts > 0 && <span className="text-amber-700"> · 차이 {conflicts}</span>}
          </span>
        </div>
        {isAll && total ? (
          <div className="mt-1.5 h-1.5 rounded bg-gray-100 overflow-hidden">
            <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, (done / total) * 100)}%` }} />
          </div>
        ) : null}
      </button>
      {open && (
        <div className="border-t border-gray-100 px-3 py-2 space-y-2">
          {job.result_message && <p className="text-[12px] text-gray-600 whitespace-pre-wrap">{job.result_message}</p>}
          {clients.length === 0 && <p className="text-[12px] text-gray-400">아직 결과가 없습니다.</p>}
          {clients.map((c) => <ImportClientResult key={c.business_number} entry={c} />)}
        </div>
      )}
    </div>
  );
}

function ImportClientResult({ entry }: { entry: ImportClientEntry }) {
  if (entry.status === "FAILED") {
    return (
      <div className="text-[12px]">
        <span className="font-medium text-gray-900">{entry.business_name}</span>{" "}
        <span className="text-red-600">실패 — {entry.message}</span>
      </div>
    );
  }
  return (
    <div className="text-[12px] space-y-1">
      <div>
        <span className="font-medium text-gray-900">{entry.business_name}</span>{" "}
        <span className="text-gray-500">
          {entry.client_created ? "새 거래처 등록" : "기존 거래처"} · 사원 {entry.employees ?? 0}명
          (신규 {entry.employees_created ?? 0} · 갱신 {entry.employees_updated ?? 0})
        </span>
      </div>
      {(entry.conflicts ?? []).length > 0 && (
        <table className="w-full text-[11px] border border-amber-200 bg-amber-50/50">
          <thead>
            <tr className="text-amber-800">
              <th className="text-left px-2 py-1 font-medium">대상</th>
              <th className="text-left px-2 py-1 font-medium">항목</th>
              <th className="text-left px-2 py-1 font-medium">이지원천 (유지)</th>
              <th className="text-left px-2 py-1 font-medium">위하고</th>
            </tr>
          </thead>
          <tbody>
            {entry.conflicts!.map((c, i) => (
              <tr key={i} className="border-t border-amber-100 text-gray-700">
                <td className="px-2 py-1">{c.target}</td>
                <td className="px-2 py-1">{c.field}</td>
                <td className="px-2 py-1">{c.current}</td>
                <td className="px-2 py-1">{c.wehago}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
