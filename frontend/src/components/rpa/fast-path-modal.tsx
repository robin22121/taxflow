"use client";

// 전월 동일 페스트패스 모달 — plan/01-workflow-roadmap.md §1.3
//
// [진입 → 프리뷰 → (델타 ±2% 이내) 원클릭 커밋] 흐름을 한 다이얼로그 안에 담는다.
// 정상 케이스는 요약 카드만 보고 [신고 진행] 누르면 자동 승인,
// 델타 초과 시 [상세 검토로 이동] 버튼으로 기존 검토·승인 화면 폴백.

import { useEffect, useState } from "react";

import { Badge, Button, Modal } from "@/components/ui";
import {
  type FastPathSummary,
  useFastPathCommit,
  useFastPathPreview,
} from "@/lib/queries";

const fmtWon = new Intl.NumberFormat("ko-KR");

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  return fmtWon.format(n);
}

function DeltaBadge({ summary }: { summary: FastPathSummary }) {
  if (summary.within_threshold) {
    return (
      <Badge tone="success">
        델타 {summary.delta_pct.toFixed(2)}% (임계치 ±{summary.threshold_pct}%)
      </Badge>
    );
  }
  return (
    <Badge tone="danger">
      델타 {summary.delta_pct.toFixed(2)}% &gt; 임계치 ±{summary.threshold_pct}% — 상세 검토 필요
    </Badge>
  );
}

function SummaryCard({ summary }: { summary: FastPathSummary }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] font-semibold text-gray-900">{summary.client_name}</div>
          <div className="text-[11px] text-gray-500">
            {summary.prev_period} → {summary.curr_period}
          </div>
        </div>
        <DeltaBadge summary={summary} />
      </div>
      <div className="grid grid-cols-2 gap-3 text-[12px]">
        <div>
          <div className="text-gray-500">인원</div>
          <div className="text-[15px] font-semibold text-gray-900">
            {summary.person_count}명
            {summary.resigned_excluded > 0 && (
              <span className="ml-1 text-[11px] text-gray-500">
                (퇴사자 {summary.resigned_excluded}명 제외)
              </span>
            )}
          </div>
        </div>
        <div>
          <div className="text-gray-500">총지급액</div>
          <div className="text-[15px] font-semibold text-gray-900">{fmt(summary.total_pay)}원</div>
        </div>
        <div>
          <div className="text-gray-500">원천세 합계</div>
          <div className="text-[15px] font-semibold text-gray-900">
            {fmt(summary.withholding_curr)}원
            <span className="ml-1.5 text-[11px] font-normal text-gray-500">
              (전월 {fmt(summary.withholding_prev)}원)
            </span>
          </div>
        </div>
        <div>
          <div className="text-gray-500">지방소득세 합계</div>
          <div className="text-[15px] font-semibold text-gray-900">
            {fmt(summary.local_tax_curr)}원
            <span className="ml-1.5 text-[11px] font-normal text-gray-500">
              (전월 {fmt(summary.local_tax_prev)}원)
            </span>
          </div>
        </div>
      </div>
      {summary.blocker && (
        <p className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          ⚠️ {summary.blocker}
        </p>
      )}
    </div>
  );
}

export function FastPathModal({
  open,
  onClose,
  filingId,
  clientId,
  clientName,
  onCommitted,
}: {
  open: boolean;
  onClose: () => void;
  filingId: string;
  clientId: string;
  clientName: string;
  onCommitted: () => void;
}) {
  const preview = useFastPathPreview(filingId, clientId);
  const commit = useFastPathCommit(filingId, clientId);
  const [summary, setSummary] = useState<FastPathSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setSummary(null);
      setError(null);
      return;
    }
    setError(null);
    preview.mutate(undefined, {
      onSuccess: (data) => setSummary(data),
      onError: (e) => setError((e as Error).message),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, filingId, clientId]);

  function runCommit() {
    if (!summary || !summary.within_threshold || !summary.can_commit) return;
    setError(null);
    commit.mutate(undefined, {
      onSuccess: () => {
        onCommitted();
        onClose();
      },
      onError: (e) => setError((e as Error).message),
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`전월 동일 신고 — ${clientName}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={commit.isPending}>
            닫기
          </Button>
          {summary && summary.within_threshold && summary.can_commit && (
            <Button onClick={runCommit} disabled={commit.isPending}>
              {commit.isPending ? "저장 중..." : "신고 진행 (원클릭 승인)"}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-3 min-w-[420px]">
        {preview.isPending && (
          <p className="text-[13px] text-gray-500">전월 자료 불러오는 중...</p>
        )}
        {error && (
          <p className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-[12px] text-red-800">
            {error}
          </p>
        )}
        {summary && (
          <>
            <SummaryCard summary={summary} />
            {!summary.within_threshold && (
              <p className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
                원천세 델타가 임계치를 초과합니다. 상세 검토 화면에서 개별 항목을 확인하세요.
                이 창을 닫고 하단 <strong>전월자료 불러오기</strong> 버튼으로 진행하면 검토 화면으로 이어집니다.
              </p>
            )}
            {summary.within_threshold && summary.can_commit && (
              <p className="text-[11.5px] text-gray-500 leading-5">
                [신고 진행]을 누르면 위 {summary.person_count}건이 <strong>자동 승인</strong>됩니다.
                이후 상단 <strong>① 위하고 전송</strong>·<strong>② 제작</strong> 버튼으로 신고를 이어가세요.
              </p>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
