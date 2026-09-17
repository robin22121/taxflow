"use client";

// 이지원천 3게이트 (전송·제작·발송 확정) 패널.
//
// plan/16-wehago-rpa.md §4·§7 반영. 사무소 로그인 사용자 누구나 3개 버튼을 눌러
// 게이트를 통과시킬 수 있다 (세무사·직원 권한 분리 없음).
//
// 아직 filing 페이지에 통합하지 않고 스탠드얼론 컴포넌트로 유지 (Task B 스캐폴드).
// 사용 예:
//   <RpaPanel filingId={filing.id} clientIds={selected.map(c => c.id)} />

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Card } from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  type FilingResult,
  type RpaJob,
  type RpaNotification,
  createProductions,
  createWehagoUploads,
  gateStage,
  indexJobsByClient,
  listJobs,
  listNotifications,
  markNotificationRead,
  publishFilingResult,
} from "@/lib/rpa-api";

type Props = {
  filingId: string;
  clientIds: string[];
  /** 접수증·납부서를 이 컴포넌트 위쪽에서 이미 조회했다면 넣어준다 (게이트 3 대상 표시용). */
  filingResults?: Record<string, FilingResult>;  // key = client_id
  onChange?: () => void;
};

const STAGE_LABEL: Record<ReturnType<typeof gateStage>, string> = {
  not_started: "전송 대기",
  sending: "위하고 자동입력 중",
  input_done: "자동입력 완료 · 제작 대기",
  producing: "제작 중 (원천세·지방세 마감 → 홈택스·위택스 신고)",
  production_done: "신고 완료 · 발송 확정 대기",
  published: "발송 확정 완료",
  failed: "실패 · 수동 처리 필요",
};

export function RpaPanel({ filingId, clientIds, filingResults, onChange }: Props) {
  const [jobs, setJobs] = useState<RpaJob[]>([]);
  const [notes, setNotes] = useState<RpaNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    const [j, n] = await Promise.all([listJobs(filingId), listNotifications(false)]);
    return { jobs: j, notes: n };
  }, [filingId]);

  // 초기 로드는 effect에서 진행하되 loading 상태를 effect body에서 setState하지 않도록
  // 결과가 도착한 뒤에만 setState 한다.
  useEffect(() => {
    let cancelled = false;
    fetchState()
      .then(({ jobs, notes }) => {
        if (cancelled) return;
        setJobs(jobs);
        setNotes(notes);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [fetchState]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { jobs, notes } = await fetchState();
      setJobs(jobs);
      setNotes(notes);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [fetchState]);

  const byClient = useMemo(() => indexJobsByClient(jobs), [jobs]);

  const stages = useMemo(() => {
    return clientIds.map((cid) => {
      const bucket = byClient[cid] ?? {};
      const result = filingResults?.[cid];
      return { clientId: cid, input: bucket.input, production: bucket.production, result, stage: gateStage(bucket.input, bucket.production, result) };
    });
  }, [clientIds, byClient, filingResults]);

  // 각 게이트에서 대상이 되는 client_ids
  const gate1Targets = stages.filter((s) => s.stage === "not_started").map((s) => s.clientId);
  const gate2Targets = stages.filter((s) => s.stage === "input_done").map((s) => s.clientId);
  const gate3Targets = stages
    .filter((s) => s.stage === "production_done" && s.result && !s.result.published_at)
    .map((s) => s.result!.id);

  async function withRefresh(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await refresh();
      onChange?.();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">위하고 자동화 (RPA)</h3>
        <button
          className="text-xs text-blue-600 hover:underline"
          onClick={() => refresh()}
          disabled={loading}
        >
          {loading ? "새로고침 중…" : "새로고침"}
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <Button
          variant="primary"
          disabled={gate1Targets.length === 0}
          onClick={() =>
            withRefresh(() => createWehagoUploads(filingId, gate1Targets))
          }
        >
          위하고 전송 ({gate1Targets.length})
        </Button>
        <Button
          variant="primary"
          disabled={gate2Targets.length === 0}
          onClick={() =>
            withRefresh(() => createProductions(filingId, gate2Targets))
          }
        >
          제작 ({gate2Targets.length})
        </Button>
        <Button
          variant="primary"
          disabled={gate3Targets.length === 0}
          onClick={() =>
            withRefresh(async () => {
              for (const id of gate3Targets) {
                await publishFilingResult(id);
              }
            })
          }
        >
          발송 확정 ({gate3Targets.length})
        </Button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-700">거래처</th>
              <th className="text-left px-3 py-2 font-medium text-gray-700">진행 단계</th>
              <th className="text-left px-3 py-2 font-medium text-gray-700">최근 회신</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {stages.map((s) => {
              const job = s.production ?? s.input;
              return (
                <tr key={s.clientId}>
                  <td className="px-3 py-2 text-gray-800">
                    {job?.business_name ?? s.clientId}
                  </td>
                  <td className="px-3 py-2 text-gray-800">{STAGE_LABEL[s.stage]}</td>
                  <td className="px-3 py-2 text-gray-500 truncate max-w-[280px]" title={job?.result_message ?? ""}>
                    {job?.result_message ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <NotificationsBlock notes={notes} onRead={async (id) => { await markNotificationRead(id); refresh(); }} />
    </Card>
  );
}

function NotificationsBlock({ notes, onRead }: { notes: RpaNotification[]; onRead: (id: string) => void }) {
  const unread = notes.filter((n) => !n.read_at);
  if (notes.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-gray-700">알림 ({unread.length} 안 읽음 / 총 {notes.length})</div>
      <ul className="space-y-1 max-h-52 overflow-auto">
        {notes.slice(0, 20).map((n) => (
          <li
            key={n.id}
            className={
              "rounded border px-3 py-2 text-xs " +
              (n.read_at ? "border-gray-200 bg-white text-gray-600" : "border-blue-200 bg-blue-50/40 text-gray-800")
            }
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="font-medium">{n.title}</div>
                <div className="whitespace-pre-wrap text-[11px] text-gray-600 mt-0.5">{n.body}</div>
              </div>
              {!n.read_at && (
                <button
                  className="text-[11px] text-blue-600 hover:underline shrink-0"
                  onClick={() => onRead(n.id)}
                >
                  읽음
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
