"use client";

// 게이트 1 [위하고 전송] — 데모버전 로그인 전용 소득유형 단위 선택 전송 (2026-10-02 사용자 요청).
//
// "이지원 버전"이 쓰는 wehago-send-modal.tsx(거래처 단위 원자적 전송, plan/16 §4-1)는
// 그대로 둔다 — 여기는 근로/사업/기타 소득유형마다 체크박스를 두어 선택한 것만 보낼 수
// 있는 별도 화면이다. 백엔드도 별도 경로(POST /wehago-uploads/selective)를 쓴다.
//
// 체크박스 상태:
//   준비됨(ready)    — 자료 있음·전원 승인·아직 전송 전 → 체크박스, 기본 체크
//   전송완료(done)   — 게이트1(+게이트2) 까지 이미 끝남   → 체크박스 비활성(기본 체크), "재전송 허용"을
//                       눌러야 다시 체크 해제·전송 가능 (오전송 방지, 교정 재전송 경로는 남겨둠)
//   미승인(unapproved) / 자료없음(empty) / 자동화 미지원(unautomated) → 체크박스 자체를 그리지 않고
//       사유만 보여준다 (선택 불가능한 걸 비활성 체크박스로 보여주는 것보다 명확하다는 판단, 검토 의견 반영)

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  createWehagoUploadsSelective,
  previewWehagoUploads,
  type IncomeTypeStatus,
  type WehagoSelectiveUploadResult,
  type WehagoUploadPreview,
} from "@/lib/rpa-api";
import type { SendTarget } from "./wehago-send-modal";

const INCOME_TYPE_LABEL: Record<IncomeTypeStatus["income_type"], string> = {
  WAGE: "근로", BUSINESS: "사업", OTHER: "기타", DAILY: "일용",
};

type Reason = "ready" | "done" | "unapproved" | "empty" | "unautomated";

function classify(s: IncomeTypeStatus): Reason {
  if (s.count === 0) return "empty";
  if (!s.automated) return "unautomated";
  if (s.unapproved_count > 0) return "unapproved";
  if (s.filing_complete) return "done";
  return "ready";
}

function itemKey(clientId: string, incomeType: string) {
  return `${clientId}:${incomeType}`;
}

type Row = {
  clientId: string;
  clientName: string;
  clientBlocked: string | null;
  payDate: string | null;
  incomeTypes: IncomeTypeStatus[];
};

function buildRows(targets: SendTarget[], preview: WehagoUploadPreview[]): Row[] {
  const byClient = new Map(preview.map((p) => [p.client_id, p]));
  return targets.map((t) => {
    const p = byClient.get(t.clientId);
    return {
      clientId: t.clientId,
      clientName: t.clientName,
      clientBlocked: t.blockedReason,
      payDate: p?.pay_date ?? null,
      incomeTypes: p?.income_types ?? [],
    };
  });
}

export function WehagoSendModalDemo({
  filingId,
  targets,
  currentClientId,
  onClose,
}: {
  filingId: string;
  targets: SendTarget[];
  currentClientId: string | null;
  onClose: () => void;
}) {
  const { data: preview, isLoading } = useQuery({
    queryKey: ["rpa", "wehago-preview", filingId],
    queryFn: () => previewWehagoUploads(filingId),
  });

  return (
    <Modal open={true} onClose={onClose} size="lg" title="① 위하고 전송 (데모) — 소득유형 선택">
      {isLoading || !preview ? (
        <p className="py-4 text-center text-[12px] text-gray-400">확인 중...</p>
      ) : (
        <SelectiveBody
          filingId={filingId}
          currentClientId={currentClientId}
          rows={buildRows(targets, preview)}
          onClose={onClose}
        />
      )}
    </Modal>
  );
}

function SelectiveBody({
  filingId,
  currentClientId,
  rows,
  onClose,
}: {
  filingId: string;
  currentClientId: string | null;
  rows: Row[];
  onClose: () => void;
}) {
  const qc = useQueryClient();

  // 처음 열렸을 때 기본값 — 준비됨·전송완료 둘 다 기본 체크 (전송완료는 비활성 상태로).
  const [selected, setSelected] = useState<Set<string>>(() => {
    const next = new Set<string>();
    for (const r of rows) {
      if (r.clientBlocked) continue;
      for (const s of r.incomeTypes) {
        const reason = classify(s);
        if (reason === "ready" || reason === "done") next.add(itemKey(r.clientId, s.income_type));
      }
    }
    return next;
  });
  const [unlocked, setUnlocked] = useState<Set<string>>(new Set());
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<WehagoSelectiveUploadResult[] | null>(null);

  function interactive(reason: Reason, key: string) {
    return reason === "ready" || (reason === "done" && unlocked.has(key));
  }

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  const allInteractiveKeys = rows.flatMap((r) =>
    r.clientBlocked
      ? []
      : r.incomeTypes
          .filter((s) => interactive(classify(s), itemKey(r.clientId, s.income_type)))
          .map((s) => itemKey(r.clientId, s.income_type)),
  );
  // 실제로 전송될 항목 — selected에는 잠긴(전송완료·재전송 미허용) 항목도 기본 체크로
  // 들어있지만, "재전송 허용"을 누르지 않은 잠긴 항목은 화면엔 체크로 보여도 전송 대상이
  // 아니다. allInteractiveKeys와의 교집합만 실제 제출 대상 — 버튼 개수·전송 둘 다 이 값을 쓴다.
  const submittableKeys = allInteractiveKeys.filter((k) => selected.has(k));

  function toggleAll() {
    setSelected((prev) => {
      const allOn = allInteractiveKeys.every((k) => prev.has(k));
      const next = new Set(prev);
      allInteractiveKeys.forEach((k) => (allOn ? next.delete(k) : next.add(k)));
      return next;
    });
  }

  function selectCurrentClientOnly() {
    if (!currentClientId) return;
    setSelected((prev) => {
      const next = new Set(prev);
      allInteractiveKeys.forEach((k) => {
        if (k.startsWith(`${currentClientId}:`)) next.add(k); else next.delete(k);
      });
      return next;
    });
  }

  async function send() {
    setSending(true);
    setError(null);
    try {
      const byClient = new Map<string, string[]>();
      for (const key of submittableKeys) {
        const [clientId, incomeType] = key.split(":");
        if (!byClient.has(clientId)) byClient.set(clientId, []);
        byClient.get(clientId)!.push(incomeType);
      }
      const selections = [...byClient.entries()].map(([client_id, income_types]) => ({
        client_id, income_types,
      }));
      const res = await createWehagoUploadsSelective(filingId, selections);
      setResults(res);
      qc.invalidateQueries({ queryKey: ["rpa"] });
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  if (results) {
    const created = results.filter((r) => r.job);
    const skipped = results.filter((r) => !r.job);
    return (
      <div className="space-y-3 text-[13px]">
        {created.length > 0 && (
          <p className="rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-[12px] text-green-700">
            {created.length}건 등록했습니다 — 이 창을 닫아도 계속 진행됩니다.
          </p>
        )}
        {skipped.length > 0 && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-[12px] text-red-700 space-y-0.5">
            {skipped.map((r, i) => (
              <p key={i}>
                {rows.find((row) => row.clientId === r.client_id)?.clientName ?? r.client_id} ·{" "}
                {INCOME_TYPE_LABEL[r.income_type as IncomeTypeStatus["income_type"]] ?? r.income_type}: {r.skipped_reason}
              </p>
            ))}
          </div>
        )}
        <div className="flex justify-end">
          <Button onClick={onClose}>확인</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-[13px]">
      <p className="text-gray-700">
        선택한 소득유형만 자동화 PC가 <strong>위하고 급여자료입력</strong>에 올립니다. 거래처 단위가
        아니라 소득유형 단위로 독립 전송됩니다 — 데모버전 전용 화면입니다.
      </p>

      {error && (
        <p className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-[12px] text-red-700 whitespace-pre-wrap">{error}</p>
      )}

      <div className="flex items-center justify-between border-b border-gray-200 pb-2 text-[12px]">
        <div className="flex items-center gap-3">
          <button type="button" disabled={allInteractiveKeys.length === 0} onClick={toggleAll}
            className="font-medium text-blue-600 hover:text-blue-700 disabled:text-gray-300">
            전체 선택/해제
          </button>
          {currentClientId && allInteractiveKeys.some((k) => k.startsWith(`${currentClientId}:`)) && (
            <button type="button" onClick={selectCurrentClientOnly}
              className="font-medium text-blue-600 hover:text-blue-700">
              보고 있는 거래처만
            </button>
          )}
        </div>
        <span className="text-gray-500">선택됨 {submittableKeys.length} / 선택 가능 {allInteractiveKeys.length}</span>
      </div>

      <div className="max-h-[45vh] overflow-y-auto divide-y divide-gray-100">
        {rows.map((r) => (
          <div key={r.clientId} className="py-2 px-1">
            <div className="flex items-center gap-2.5 mb-1.5">
              <span className="flex-1 text-[13px] font-medium text-gray-900">{r.clientName}</span>
              {r.payDate && <span className="text-[11px] text-gray-500 tabular-nums">지급일 {r.payDate}</span>}
              {r.clientBlocked && <Badge tone="danger">{r.clientBlocked}</Badge>}
            </div>
            {!r.clientBlocked && (
              <div className="pl-1 flex flex-wrap gap-2">
                {r.incomeTypes.map((s) => {
                  const reason = classify(s);
                  const key = itemKey(r.clientId, s.income_type);
                  const label = INCOME_TYPE_LABEL[s.income_type];
                  if (reason === "empty") {
                    return <span key={key} className="px-1.5 py-0.5 rounded text-[12px] bg-gray-100 text-gray-500">{label} 자료없음</span>;
                  }
                  if (reason === "unautomated") {
                    return <span key={key} className="px-1.5 py-0.5 rounded text-[12px] bg-gray-100 text-gray-500">{label} 자동화 미지원</span>;
                  }
                  if (reason === "unapproved") {
                    return <span key={key} className="px-1.5 py-0.5 rounded text-[12px] font-medium bg-red-50 text-red-700 border border-red-300">{label} {s.unapproved_count}/{s.count} 미승인</span>;
                  }
                  const locked = reason === "done" && !unlocked.has(key);
                  return (
                    <label key={key}
                      className={`flex items-center gap-1 px-1.5 py-0.5 rounded border text-[12px] font-medium ${
                        reason === "done" ? "bg-emerald-50 text-emerald-700 border-emerald-300" : "bg-blue-50 text-blue-700 border-blue-300"
                      } ${locked ? "cursor-not-allowed opacity-80" : "cursor-pointer"}`}>
                      <input type="checkbox" checked={selected.has(key)} disabled={locked}
                        onChange={() => toggle(key)} className="h-3 w-3 accent-blue-600 disabled:opacity-40" />
                      {label} {s.count}건 {reason === "done" ? "전송완료" : "승인완료"}
                      {locked && (
                        <button type="button"
                          onClick={(e) => { e.preventDefault(); e.stopPropagation(); setUnlocked((prev) => new Set(prev).add(key)); }}
                          className="ml-0.5 text-[11px] underline text-emerald-800 hover:text-emerald-900">
                          재전송 허용
                        </button>
                      )}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button disabled={submittableKeys.length === 0 || sending} onClick={send}>
          {sending ? "전송 중..." : `${submittableKeys.length}개 항목 전송`}
        </Button>
      </div>
    </div>
  );
}
