"use client";

// 게이트 1 [위하고 전송] — 거래처를 골라 위하고 급여자료입력 작업을 등록한다 (plan/16 §4-1).
// 기본은 전송할 수 있는 전체 거래처, "보고 있는 거래처만"으로 좁힐 수 있다.
// 차단 사유: 화면이 아는 것(미승인·자료없음) + 서버 미리보기(사업자번호·사원코드·지급일·진행 중).
// 실제 전송 때 서버가 같은 검사를 다시 한다.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createWehagoUploads, previewWehagoUploads } from "@/lib/rpa-api";

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
    return { ...t, payDate: p?.pay_date ?? null, reason: t.blockedReason ?? p?.blocked_reason ?? null };
  });
  const sendable = rows.filter((r) => !r.reason).map((r) => r.clientId);

  // null = 아직 사용자가 고르지 않음 → 전송 가능한 전체
  const [picked, setPicked] = useState<string[] | null>(null);
  const selected = (picked ?? sendable).filter((id) => sendable.includes(id));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
              className={`flex items-center gap-2.5 py-2 px-1 ${blocked ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:bg-gray-50"}`}>
              <input type="checkbox" checked={!blocked && selected.includes(r.clientId)} disabled={blocked}
                onChange={() => toggle(r.clientId)} className="h-3.5 w-3.5 accent-blue-600" />
              <span className="flex-1 text-[13px] text-gray-900">{r.clientName}</span>
              {r.payDate && <span className="text-[11px] text-gray-500 tabular-nums">지급일 {r.payDate}</span>}
              {r.reason && <Badge tone="danger">{r.reason}</Badge>}
            </label>
          );
        })}
      </div>

      {rows.some((r) => r.reason === "급여지급일 미설정") && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          급여지급일은 거래처 상세 → 기본 세팅에서 설정합니다 (위하고 급여자료입력은 지급일로 조회).
        </p>
      )}
    </Modal>
  );
}
