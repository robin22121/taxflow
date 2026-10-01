"use client";

// 게이트 1 [위하고 전송] — 거래처를 골라 위하고 급여자료입력 작업을 등록한다 (plan/16 §4-1).
// 기본은 전송할 수 있는 전체 거래처, "보고 있는 거래처만"으로 좁힐 수 있다.
// 차단 사유: 화면이 아는 것(미승인·자료없음) + 서버 미리보기(사업자번호·사원코드·지급일·진행 중).
// 실제 전송 때 서버가 같은 검사를 다시 한다.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createWehagoUploads, previewWehagoUploads, type IncomeTypeStatus } from "@/lib/rpa-api";

const INCOME_TYPE_LABEL: Record<IncomeTypeStatus["income_type"], string> = {
  WAGE: "근로",
  BUSINESS: "사업",
  OTHER: "기타",
  DAILY: "일용",
};

/** 차단 사유 배지 클릭 시 보여줄 상세 설명 — 서버는 사유 문자열만 주므로 화면에서 매칭한다. */
function explainReason(reason: string): string {
  if (reason === "사업자번호 없음") {
    return "이 거래처엔 사업자번호가 등록돼 있지 않습니다. 위하고 T 수임처와 대조할 수 없어 전송할 수 없습니다 — 거래처 상세에서 사업자번호를 먼저 입력하세요.";
  }
  if (reason.startsWith("위하고 사원코드 없는 사원 있음")) {
    return "괄호 안 소득유형에 속한 직원 중 위하고 사원코드가 비어 있는 사람이 있습니다. 위하고 급여자료입력은 이 코드로 사원을 찾기 때문에, 코드가 없으면 어떤 위하고 사원에 급여를 연결할지 알 수 없어 거래처 전체 전송을 막습니다 — 직원 상세에서 위하고 사원코드를 입력하세요.";
  }
  if (reason === "이미 전송 대기·진행 중") {
    return "이 거래처는 이미 위하고 전송 작업이 대기·진행 중입니다. 같은 자료가 중복으로 올라가지 않도록 그 작업이 끝날 때까지 새로 전송할 수 없습니다.";
  }
  if (reason === "급여지급일 미설정") {
    return "급여지급일은 거래처 상세 → 기본 세팅에서 설정합니다. 위하고 급여자료입력은 지급일로 조회하기 때문에 지급일이 없으면 전송할 화면을 찾을 수 없습니다.";
  }
  if (reason.includes("자동화 미지원")) {
    return "원천징수이행상황신고서는 근로·사업·기타·일용소득을 합산한 신고서 한 장이라, 자동화가 없는 소득이 섞인 거래처는 전체를 전송할 수 없습니다. 해당 소득은 위하고에 직접 입력한 뒤 진행하세요.";
  }
  return reason;
}

/** 소득유형 4칸 — 선택 체크박스가 아니라 상태 표시다. 전송은 거래처 단위로 원자적이다 (plan/16 §4-1).
 * 제작 모달(production-modal.tsx)도 같은 칩을 재사용한다. */
export function IncomeTypeChips({ types }: { types: IncomeTypeStatus[] }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {types.map((t) => {
        const label = INCOME_TYPE_LABEL[t.income_type];
        if (t.count === 0) {
          return (
            <span key={t.income_type} className="px-1.5 py-0.5 rounded text-[12px] bg-gray-100 text-gray-500">
              {label} 자료없음
            </span>
          );
        }
        if (!t.automated) {
          return (
            <span key={t.income_type} className="px-1.5 py-0.5 rounded text-[12px] font-medium bg-amber-50 text-amber-800 border border-amber-300">
              {label} {t.count}건 · 자동화 미지원
            </span>
          );
        }
        if (t.unapproved_count > 0) {
          return (
            <span key={t.income_type} className="px-1.5 py-0.5 rounded text-[12px] font-medium bg-red-50 text-red-700 border border-red-300">
              {label} {t.unapproved_count}/{t.count} 미승인
            </span>
          );
        }
        if (t.filing_complete) {
          return (
            <span key={t.income_type} className="px-1.5 py-0.5 rounded text-[12px] font-medium bg-green-50 text-green-700 border border-green-300">
              {label} {t.count}건 완료
            </span>
          );
        }
        return (
          <span
            key={t.income_type}
            className="px-1.5 py-0.5 rounded text-[12px] font-medium bg-blue-50 text-blue-700 border border-blue-300"
            title="자료입력은 끝났지만 명세서 추가입력(제작·마감)까지는 아직입니다"
          >
            {label} {t.count}건 · 자료입력 완료
          </span>
        );
      })}
    </div>
  );
}

export type SendTarget = { clientId: string; clientName: string; blockedReason: string | null };

export function WehagoSendModal({
  filingId,
  targets,
  currentClientId,
  onClose,
}: {
  filingId: string;
  /** 신고의 거래처 — blockedReason 은 화면에서 이미 아는 차단 사유 (미승인·자료없음) */
  targets: SendTarget[];
  currentClientId: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data: preview, isLoading } = useQuery({
    queryKey: ["rpa", "wehago-preview", filingId],
    queryFn: () => previewWehagoUploads(filingId),
  });
  const byClient = new Map((preview ?? []).map((p) => [p.client_id, p]));
  const rows = targets.map((t) => {
    const p = byClient.get(t.clientId);
    return {
      ...t,
      payDate: p?.pay_date ?? null,
      reason: t.blockedReason ?? p?.blocked_reason ?? null,
      incomeTypes: p?.income_types ?? [],
    };
  });
  const sendable = rows.filter((r) => !r.reason).map((r) => r.clientId);

  // null = 아직 사용자가 고르지 않음 → 전송 가능한 전체
  const [picked, setPicked] = useState<string[] | null>(null);
  const selected = (picked ?? sendable).filter((id) => sendable.includes(id));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailReason, setDetailReason] = useState<string | null>(null);

  async function send() {
    setSending(true);
    setError(null);
    try {
      await createWehagoUploads(filingId, selected);
      qc.invalidateQueries({ queryKey: ["rpa"] });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  const toggle = (id: string) =>
    setPicked(selected.includes(id) ? selected.filter((c) => c !== id) : [...selected, id]);

  return (
    <>
    <Modal open={true} onClose={onClose} size="lg" title="① 위하고 전송 — 거래처 선택"
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button disabled={selected.length === 0 || sending || isLoading} onClick={send}>
          {sending ? "전송 중..." : `${selected.length}곳 전송`}
        </Button>
      </>}>
      <p className="text-[13px] text-gray-700 mb-3">
        선택한 거래처의 급여대장을 자동화 PC가 <strong>위하고 급여자료입력</strong>에 올리고,
        저장 후 지급액·비과세를 대조해 결과를 알려 드립니다.
      </p>

      {error && (
        <p className="mb-3 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-[12px] text-red-700 whitespace-pre-wrap">{error}</p>
      )}

      <div className="flex items-center justify-between border-b border-gray-200 pb-2 mb-1 text-[12px]">
        <div className="flex items-center gap-3">
          <button type="button" disabled={sendable.length === 0}
            onClick={() => setPicked(selected.length === sendable.length ? [] : sendable)}
            className="font-medium text-blue-600 hover:text-blue-700 disabled:text-gray-300">
            {sendable.length > 0 && selected.length === sendable.length ? "전체 해제" : "전체 선택"}
          </button>
          {currentClientId && sendable.includes(currentClientId) && (
            <button type="button" onClick={() => setPicked([currentClientId])}
              className="font-medium text-blue-600 hover:text-blue-700">
              보고 있는 거래처만
            </button>
          )}
        </div>
        <span className="text-gray-500">전송 가능 {sendable.length} / 전체 {rows.length}곳</span>
      </div>

      <div className="max-h-[45vh] overflow-y-auto divide-y divide-gray-100">
        {isLoading && <p className="py-4 text-center text-[12px] text-gray-400">확인 중...</p>}
        {!isLoading && rows.map((r) => {
          const blocked = Boolean(r.reason);
          return (
            <label key={r.clientId}
              className={`flex flex-col gap-1.5 py-2 px-1 ${blocked ? "cursor-not-allowed" : "cursor-pointer hover:bg-gray-50"}`}>
              <div className="flex items-center gap-2.5">
                <input type="checkbox" checked={!blocked && selected.includes(r.clientId)} disabled={blocked}
                  onChange={() => toggle(r.clientId)} className="h-3.5 w-3.5 accent-blue-600 disabled:opacity-40" />
                <span className={`flex-1 text-[13px] ${blocked ? "text-gray-500" : "text-gray-900"}`}>{r.clientName}</span>
                {r.payDate && <span className="text-[11px] text-gray-500 tabular-nums">지급일 {r.payDate}</span>}
                {r.reason && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDetailReason(r.reason);
                    }}
                    className="cursor-pointer"
                  >
                    <Badge tone="danger">{r.reason} · 자세히</Badge>
                  </button>
                )}
              </div>
              {r.incomeTypes.length > 0 && (
                <div className="pl-6"><IncomeTypeChips types={r.incomeTypes} /></div>
              )}
            </label>
          );
        })}
      </div>

      {rows.some((r) => r.reason === "급여지급일 미설정") && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          급여지급일은 거래처 상세 → 기본 세팅에서 설정합니다 (위하고 급여자료입력은 지급일로 조회).
        </p>
      )}
      {rows.some((r) => r.reason?.includes("자동화 미지원")) && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          원천징수이행상황신고서는 근로·사업·기타·일용소득을 합산한 신고서 한 장이라, 자동화가 없는
          소득이 섞인 거래처는 전체를 전송할 수 없습니다. 해당 소득은 위하고에 직접 입력한 뒤 진행하세요.
        </p>
      )}
    </Modal>

    {detailReason && (
      <Modal open={true} onClose={() => setDetailReason(null)} title="전송 불가 사유"
        footer={<Button onClick={() => setDetailReason(null)}>확인</Button>}>
        <p className="text-[13px] font-medium text-gray-900 mb-2">{detailReason}</p>
        <p className="text-[13px] text-gray-700 leading-relaxed">{explainReason(detailReason)}</p>
      </Modal>
    )}
    </>
  );
}
