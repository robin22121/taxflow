"use client";

import { use, useState } from "react";

import {
  useFilingDashboard,
  useFilingEntries,
  useRequestCollection,
  useSendInvite,
  useSubmitMessage,
  useUpdateEntry,
} from "@/lib/queries";
import { apiBlob, getToken } from "@/lib/api";
import { Badge, Button, Card, Textarea } from "@/components/ui";
import type { CollectionSession, PayrollEntry } from "@/lib/types";

export default function FilingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading } = useFilingDashboard(id);
  const { data: entries } = useFilingEntries(id);
  const requestCollection = useRequestCollection(id);
  const sendInvite = useSendInvite(id);
  const [activeSession, setActiveSession] = useState<string | null>(null);

  if (isLoading || !data) return <p>로딩 중...</p>;

  const filing = data.filing;
  async function downloadFile(path: string, filename: string) {
    try {
      const blob = await apiBlob(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function downloadExcel() {
    try {
      const blob = await apiBlob(`/api/v1/filings/${id}/wehago-excel`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `wehago_${filing.period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{filing.period} 원천세</h1>
          <p className="text-sm text-gray-500">
            거래처 {filing.total_clients} · 항목 {filing.total_entries}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => sendInvite.mutate()}
            disabled={sendInvite.isPending}
          >
            {sendInvite.isPending ? "발송중..." : "초대장 발송 (카톡+이메일)"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => requestCollection.mutate()}
            disabled={requestCollection.isPending}
          >
            {requestCollection.isPending ? "발송중..." : "자료 요청 알림톡"}
          </Button>
          <Button onClick={downloadExcel}>위하고T 엑셀 다운로드</Button>
          <Button
            variant="secondary"
            onClick={() => downloadFile(`/api/v1/filings/${id}/statement-wage`, `간이지급명세서_근로_${filing.period}.xlsx`)}
          >
            근로소득 명세서
          </Button>
          <Button
            variant="secondary"
            onClick={() => downloadFile(`/api/v1/filings/${id}/statement-business`, `간이지급명세서_사업_${filing.period}.xlsx`)}
          >
            사업소득 명세서
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.sessions.map((s) => (
          <SessionCard
            key={s.id}
            session={s}
            active={activeSession === s.id}
            onClick={() => setActiveSession(activeSession === s.id ? null : s.id)}
          />
        ))}
      </div>

      {activeSession && (
        <SessionDetail
          filingId={id}
          session={data.sessions.find((s) => s.id === activeSession)!}
          entries={(entries ?? []).filter((e) => e.client_id === data.sessions.find((s) => s.id === activeSession)?.client_id)}
        />
      )}

      {!activeSession && entries && entries.length > 0 && (
        <Card>
          <h3 className="font-medium mb-3">전체 항목</h3>
          <EntryTable filingId={id} entries={entries} />
        </Card>
      )}
    </div>
  );
}

function SessionCard({
  session,
  active,
  onClick,
}: {
  session: CollectionSession;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "text-left rounded-lg border p-4 shadow-sm transition-colors " +
        (active
          ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
          : "border-gray-200 bg-white hover:border-blue-400 dark:border-gray-800 dark:bg-gray-950")
      }
    >
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium">{session.client_name}</div>
        <SessionStatusBadge session={session} />
      </div>
      <div className="text-xs text-gray-500">
        {session.has_responses ? `${session.entry_count}개 항목` : "미수신"}
      </div>
    </button>
  );
}

function SessionStatusBadge({ session }: { session: CollectionSession }) {
  if (session.has_anomalies) return <Badge tone="warning">검증 필요</Badge>;
  if (session.status === "RECEIVED" || session.status === "APPROVED")
    return <Badge tone="success">수신완료</Badge>;
  if (session.status === "SENT") return <Badge tone="info">대기중</Badge>;
  if (session.status === "NEEDS_REVIEW") return <Badge tone="warning">검증 필요</Badge>;
  return <Badge>대기</Badge>;
}

function SessionDetail({
  filingId,
  session,
  entries,
}: {
  filingId: string;
  session: CollectionSession;
  entries: PayrollEntry[];
}) {
  const submit = useSubmitMessage(filingId);
  const [text, setText] = useState("");

  return (
    <Card className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">{session.client_name} — 자료 입력 / 검증</h3>
        <a
          href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3000"}/r/${session.request_token}`}
          target="_blank"
          className="text-xs text-blue-600 hover:underline"
        >
          공개 입력 URL 열기 ↗
        </a>
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          거래처가 보낸 카톡/이메일 텍스트를 붙여넣고 AI 파싱 실행
        </label>
        <Textarea
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"예) 이번달 김연호 100, 박민수는 신규입사 150, 이영수는 퇴사했어요"}
        />
        <Button
          onClick={() => {
            if (!text.trim()) return;
            submit.mutate(
              { sessionId: session.id, text },
              {
                onSuccess: () => setText(""),
                onError: (e) => alert((e as Error).message),
              },
            );
          }}
          disabled={submit.isPending || !text.trim()}
        >
          {submit.isPending ? "AI 파싱 중..." : "AI 파싱 실행"}
        </Button>
      </div>

      {entries.length > 0 ? (
        <EntryTable filingId={filingId} entries={entries} />
      ) : (
        <p className="text-sm text-gray-500">아직 파싱된 항목이 없습니다.</p>
      )}
    </Card>
  );
}

function EntryTable({ filingId, entries }: { filingId: string; entries: PayrollEntry[] }) {
  const update = useUpdateEntry(filingId);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs text-gray-500 border-b border-gray-200 dark:border-gray-800">
          <tr>
            <th className="text-left py-2 pr-3">상태</th>
            <th className="text-left py-2 pr-3">이름</th>
            <th className="text-left py-2 pr-3">소득구분</th>
            <th className="text-right py-2 pr-3">총지급액</th>
            <th className="text-right py-2 pr-3">전월</th>
            <th className="text-right py-2 pr-3">소득세</th>
            <th className="text-right py-2 pr-3">지방세</th>
            <th className="text-center py-2 pr-3">승인</th>
            <th className="text-left py-2">메모</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-b border-gray-100 dark:border-gray-900">
              <td className="py-2 pr-3"><MatchBadge status={e.match_status} /></td>
              <td className="py-2 pr-3 font-medium">{e.raw_name}</td>
              <td className="py-2 pr-3">{e.income_type}</td>
              <td className="py-2 pr-3 text-right">{formatKrw(e.total_amount)}</td>
              <td className={"py-2 pr-3 text-right " + (e.anomaly_notes?.large_change ? "text-amber-600 font-medium" : "text-gray-500")}>
                {e.prev_amount ? formatKrw(e.prev_amount) : "—"}
              </td>
              <td className="py-2 pr-3 text-right">{formatKrw(e.income_tax)}</td>
              <td className="py-2 pr-3 text-right">{formatKrw(e.local_tax)}</td>
              <td className="py-2 pr-3 text-center">
                <input
                  type="checkbox"
                  checked={e.approved}
                  onChange={(ev) =>
                    update.mutate({ id: e.id, patch: { approved: ev.target.checked } })
                  }
                />
              </td>
              <td className="py-2 text-xs text-gray-500">
                {e.anomaly_notes?.large_change
                  ? `전월 대비 ${(e.anomaly_notes.large_change as { ratio: number }).ratio}배 변동`
                  : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MatchBadge({ status }: { status: string }) {
  if (status === "MATCHED") return <Badge tone="success">매칭</Badge>;
  if (status === "NEW_HIRE_SUSPECTED") return <Badge tone="info">신규 의심</Badge>;
  if (status === "RESIGNATION_SUSPECTED") return <Badge tone="warning">퇴사 의심</Badge>;
  return <Badge tone="warning">모호</Badge>;
}

function formatKrw(n: number | null | undefined): string {
  if (!n) return "—";
  return n.toLocaleString("ko-KR") + "원";
}

void getToken; // ensure side-effects (browser-only file)
