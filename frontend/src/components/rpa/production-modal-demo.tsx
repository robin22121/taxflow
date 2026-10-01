"use client";

// 게이트 2 [제작] — 데모버전 로그인 전용 사본 (2026-10-02 사용자 요청).
//
// "이지원 버전"이 쓰는 production-modal.tsx는 그대로 둔다 — 프로세스 구현·오류수정을
// 실제 운영 화면에 영향 없이 반복할 수 있도록 별도 컴포넌트로 분리했다. 지금은 동작이
// 100% 동일(제작은 거래처 단위 외에 쪼갤 자연스러운 단위가 없어 §4-1 소득유형 선택과 달리
// 그대로 유지) — 이후 이 파일만 독립적으로 바꿔 나가면 된다.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createProductions, previewWehagoUploads } from "@/lib/rpa-api";
import { IncomeTypeChips } from "./wehago-send-modal";
import type { ProductionTarget } from "./production-modal";

export function ProductionModalDemo({
  filingId,
  targets,
  currentClientId,
  onClose,
}: {
  filingId: string;
  targets: ProductionTarget[];
  currentClientId: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data: preview } = useQuery({
    queryKey: ["rpa", "wehago-preview", filingId],
    queryFn: () => previewWehagoUploads(filingId),
  });
  const previewByClient = new Map((preview ?? []).map((p) => [p.client_id, p]));
  const sendable = targets.filter((t) => !t.blockedReason).map((t) => t.clientId);

  const [picked, setPicked] = useState<string[] | null>(null);
  const selected = (picked ?? sendable).filter((id) => sendable.includes(id));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setSending(true);
    setError(null);
    try {
      await createProductions(filingId, selected);
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
    <Modal open={true} onClose={onClose} size="lg" title="② 제작 (데모) — 거래처 선택"
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button disabled={selected.length === 0 || sending} onClick={confirm}>
          {sending ? "제작 중..." : `${selected.length}곳 제작`}
        </Button>
      </>}>
      <p className="mb-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12.5px] text-amber-800 leading-relaxed">
        이지원천은 <strong>근로소득(일용 포함)·사업소득·기타소득</strong>에 대한 신고 자동화만 지원합니다.
        중도퇴사자 정산·퇴직소득·연금소득·이자/배당소득 등이 있는 거래처는 위하고 T에 <strong>직접 입력</strong>한
        뒤 다시 이지원천에서 제작을 진행해 주세요.
      </p>

      <p className="text-[13px] text-gray-700 mb-3">
        선택한 거래처의 위하고 원천세·지방세 마감·전자신고 파일 제작 후 홈택스·위택스 신고까지
        자동화 PC가 진행합니다.
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
        <span className="text-gray-500">제작 가능 {sendable.length} / 전체 {targets.length}곳</span>
      </div>

      <div className="max-h-[40vh] overflow-y-auto divide-y divide-gray-100">
        {targets.map((t) => {
          const blocked = Boolean(t.blockedReason);
          const incomeTypes = previewByClient.get(t.clientId)?.income_types ?? [];
          return (
            <label key={t.clientId}
              className={`flex flex-col gap-1.5 py-2 px-1 ${blocked ? "cursor-not-allowed" : "cursor-pointer hover:bg-gray-50"}`}>
              <div className="flex items-center gap-2.5">
                <input type="checkbox" checked={!blocked && selected.includes(t.clientId)} disabled={blocked}
                  onChange={() => toggle(t.clientId)} className="h-3.5 w-3.5 accent-blue-600 disabled:opacity-40" />
                <span className={`flex-1 text-[13px] ${blocked ? "text-gray-500" : "text-gray-900"}`}>{t.clientName}</span>
                {t.blockedReason && <Badge tone="danger">{t.blockedReason}</Badge>}
              </div>
              {incomeTypes.length > 0 && (
                <div className="pl-6"><IncomeTypeChips types={incomeTypes} /></div>
              )}
            </label>
          );
        })}
      </div>
    </Modal>
  );
}
