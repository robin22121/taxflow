"use client";

// 게이트 2 [제작] — 위하고 입력이 끝난 거래처를 골라 마감·전자신고 작업을 등록한다 (plan/16 §4-4).
// 진행 전에 이지원천 자동화 범위(근로·사업·기타소득)를 벗어나는 소득이 있으면
// 위하고에 직접 입력해 달라는 확인 안내를 반드시 보여준다.

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createProductions } from "@/lib/rpa-api";

export type ProductionTarget = { clientId: string; clientName: string; blockedReason: string | null };

export function ProductionModal({
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
    <Modal open={true} onClose={onClose} size="lg" title="② 제작 — 거래처 선택"
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
          return (
            <label key={t.clientId}
              className={`flex items-center gap-2.5 py-2 px-1 ${blocked ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:bg-gray-50"}`}>
              <input type="checkbox" checked={!blocked && selected.includes(t.clientId)} disabled={blocked}
                onChange={() => toggle(t.clientId)} className="h-3.5 w-3.5 accent-blue-600" />
              <span className="flex-1 text-[13px] text-gray-900">{t.clientName}</span>
              {t.blockedReason && <Badge tone="danger">{t.blockedReason}</Badge>}
            </label>
          );
        })}
      </div>
    </Modal>
  );
}
