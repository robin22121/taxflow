"use client";

import { use, useEffect, useMemo, useState } from "react";

import {
  useConfirmWithClient,
  useDeleteEntry,
  useFilingDashboard,
  useFilingEntries,
  useRequestCollection,
  useSendInvite,
  useSessionAttachments,
  useSubmitMessage,
  useUpdateEntry,
} from "@/lib/queries";
import { apiBlob, getToken } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, Textarea } from "@/components/ui";
import type { CollectionSession, PayrollEntry, SessionAttachment, SourceEvent } from "@/lib/types";

export default function FilingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading } = useFilingDashboard(id);
  const { data: entries } = useFilingEntries(id);
  const sendInvite = useSendInvite(id);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);

  if (isLoading || !data) return <p>로딩 중...</p>;

  const filing = data.filing;
  async function downloadExcel() {
    try {
      const blob = await apiBlob(`/api/v1/filings/${id}/payroll-excel`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `급여대장_${filing.period}.xlsx`;
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
            onClick={() => setShowBulkConfirm(true)}
            disabled={sendInvite.isPending}
          >
            {sendInvite.isPending ? "발송중..." : "자료요청 일괄전송"}
          </Button>
          <Button onClick={downloadExcel}>최종엑셀전송</Button>
        </div>

        {showBulkConfirm && (
          <Modal
            open={true}
            onClose={() => setShowBulkConfirm(false)}
            title="자료요청 일괄전송"
            footer={
              <>
                <Button variant="ghost" onClick={() => setShowBulkConfirm(false)}>
                  취소
                </Button>
                <Button
                  onClick={() => {
                    setShowBulkConfirm(false);
                    sendInvite.mutate();
                  }}
                >
                  확인
                </Button>
              </>
            }
          >
            <p className="text-sm text-gray-700 dark:text-gray-300">
              모든 거래처에 자료요청 안내문을 보냅니다. 진행하시겠습니까?
            </p>
          </Modal>
        )}
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
  const confirmWithClient = useConfirmWithClient(filingId);
  const requestCollection = useRequestCollection(filingId);
  const [text, setText] = useState("");
  const [senderName, setSenderName] = useState("");
  const [channel, setChannel] = useState("kakao");
  const [receivedDate, setReceivedDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [confirmResult, setConfirmResult] = useState<{
    sent: boolean;
    channel: string;
    error: string | null;
  } | null>(null);
  const [sourceModal, setSourceModal] = useState<SourceEvent | null>(null);

  return (
    <Card className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">{session.client_name} — 자료 입력 / 검증</h3>
        <div className="flex items-center gap-3 text-xs">
          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3000"}/r/${session.request_token}`}
            target="_blank"
            className="text-blue-600 hover:underline"
          >
            공개 입력 URL ↗
          </a>
          <Button
            variant="secondary"
            disabled={requestCollection.isPending}
            onClick={() => requestCollection.mutate(session.id)}
          >
            {requestCollection.isPending ? "발송중..." : "자료 요청 알림톡"}
          </Button>
          <Button
            variant="secondary"
            disabled={confirmWithClient.isPending || entries.length === 0}
            onClick={() => {
              setConfirmResult(null);
              confirmWithClient.mutate(
                { sessionId: session.id, channel: "auto" },
                {
                  onSuccess: (res) => setConfirmResult(res),
                  onError: (e) =>
                    setConfirmResult({
                      sent: false,
                      channel: "error",
                      error: (e as Error).message,
                    }),
                },
              );
            }}
            title={
              entries.length === 0
                ? "파싱된 항목이 있어야 발송 가능합니다"
                : "거래처에 AI 인식 결과를 같은 채널로 회신"
            }
          >
            {confirmWithClient.isPending
              ? "발송 중..."
              : "거래처에 인식 결과 확인 요청"}
          </Button>
        </div>
      </div>

      {confirmResult && (
        <div
          className={
            confirmResult.sent
              ? "text-xs text-green-700 dark:text-green-300"
              : "text-xs text-amber-700 dark:text-amber-300"
          }
        >
          {confirmResult.sent
            ? `✅ ${confirmResult.channel}로 발송 완료`
            : `⚠️ 발송 실패 (${confirmResult.channel}) — ${confirmResult.error ?? "알 수 없는 오류"}`}
        </div>
      )}

      <AttachmentPanel filingId={filingId} sessionId={session.id} />

      <div className="space-y-3 border-t border-gray-200 dark:border-gray-800 pt-3">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          거래처가 보낸 메시지 원본 입력
        </label>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-[11px] text-gray-500 mb-0.5">
              발신자 <span className="text-red-500">*</span>
            </label>
            <Input
              placeholder="홍길동 대표"
              value={senderName}
              onChange={(e) => setSenderName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-[11px] text-gray-500 mb-0.5">
              수신 경로 <span className="text-red-500">*</span>
            </label>
            <select
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              <option value="kakao">카카오톡</option>
              <option value="email">이메일</option>
              <option value="sms">문자(SMS)</option>
              <option value="voice">전화/음성</option>
              <option value="manual">직접 입력</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-gray-500 mb-0.5">
              보낸 날짜 <span className="text-red-500">*</span>
            </label>
            <Input
              type="date"
              value={receivedDate}
              onChange={(e) => setReceivedDate(e.target.value)}
            />
          </div>
        </div>
        <Textarea
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"예) 이번달 김연호 100, 박민수는 신규입사 150, 이영수는 퇴사했어요"}
        />
        <Button
          onClick={() => {
            if (!text.trim() || !senderName.trim() || !receivedDate) return;
            submit.mutate(
              {
                sessionId: session.id,
                text,
                channel,
                sender_name: senderName.trim(),
                received_date: receivedDate,
              },
              {
                onSuccess: () => setText(""),
                onError: (e) => alert((e as Error).message),
              },
            );
          }}
          disabled={
            submit.isPending ||
            !text.trim() ||
            !senderName.trim() ||
            !receivedDate
          }
        >
          {submit.isPending ? "AI 파싱 중..." : "AI 파싱 실행"}
        </Button>
      </div>

      {entries.length > 0 ? (
        <EntryTable
          filingId={filingId}
          entries={entries}
          onShowSource={setSourceModal}
        />
      ) : (
        <p className="text-sm text-gray-500">아직 파싱된 항목이 없습니다.</p>
      )}

      {sourceModal && (
        <SourceEventModal
          event={sourceModal}
          onClose={() => setSourceModal(null)}
        />
      )}
    </Card>
  );
}

function AttachmentPanel({ filingId, sessionId }: { filingId: string; sessionId: string }) {
  const { data: attachments } = useSessionAttachments(filingId, sessionId);
  const [zoomKey, setZoomKey] = useState<string | null>(null);

  if (!attachments || attachments.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-gray-200 dark:border-gray-800 pt-3">
      <div className="flex items-baseline justify-between">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          거래처가 보낸 원본 첨부 ({attachments.length}개)
        </h4>
        <span className="text-xs text-gray-500">
          AI 추출 결과가 원본과 일치하는지 확인하세요
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {attachments.map((a) => (
          <AttachmentThumb
            key={a.storage_key}
            filingId={filingId}
            sessionId={sessionId}
            att={a}
            onClick={() => setZoomKey(a.storage_key)}
          />
        ))}
      </div>
      {zoomKey && (
        <AttachmentZoomModal
          filingId={filingId}
          sessionId={sessionId}
          att={attachments.find((a) => a.storage_key === zoomKey)!}
          onClose={() => setZoomKey(null)}
        />
      )}
    </div>
  );
}

function AttachmentThumb({
  filingId,
  sessionId,
  att,
  onClick,
}: {
  filingId: string;
  sessionId: string;
  att: SessionAttachment;
  onClick: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const showInline = att.kind === "image";

  useEffect(() => {
    if (!showInline) return;
    let cancelled = false;
    let url: string | null = null;
    apiBlob(
      `/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`,
    )
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [filingId, sessionId, att.storage_key, showInline]);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col items-stretch text-left rounded-md border border-gray-200 dark:border-gray-800 overflow-hidden hover:border-blue-400 transition-colors"
    >
      <div className="aspect-square bg-gray-50 dark:bg-gray-900 flex items-center justify-center text-xs text-gray-500">
        {showInline && blobUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={blobUrl}
            alt={att.filename}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
          />
        ) : showInline && !blobUrl && !error ? (
          <span>로딩...</span>
        ) : error ? (
          <span className="text-red-600 px-2 text-center">{error}</span>
        ) : (
          <KindIcon kind={att.kind} />
        )}
      </div>
      <div className="px-2 py-1 text-xs truncate" title={att.filename}>
        {att.filename}
      </div>
      <div className="px-2 pb-1 text-[10px] text-gray-500">
        {att.kind} · {att.channel}
      </div>
    </button>
  );
}

function KindIcon({ kind }: { kind: string }) {
  const label = {
    pdf: "PDF",
    excel: "엑셀",
    csv: "CSV",
    audio: "음성",
    image: "이미지",
  }[kind] ?? kind;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="text-2xl">📎</div>
      <div className="text-xs font-medium">{label}</div>
    </div>
  );
}

function AttachmentZoomModal({
  filingId,
  sessionId,
  att,
  onClose,
}: {
  filingId: string;
  sessionId: string;
  att: SessionAttachment;
  onClose: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    apiBlob(
      `/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`,
    )
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [filingId, sessionId, att.storage_key]);

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={att.filename}
      footer={
        blobUrl ? (
          <a
            href={blobUrl}
            download={att.filename}
            className="text-sm text-blue-600 hover:underline"
          >
            다운로드
          </a>
        ) : null
      }
    >
      <div className="max-h-[70vh] overflow-auto flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded">
        {error ? (
          <p className="text-red-600 p-4">{error}</p>
        ) : !blobUrl ? (
          <p className="p-8 text-gray-500">로딩 중...</p>
        ) : att.kind === "image" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={blobUrl} alt={att.filename} className="max-w-full" />
        ) : att.kind === "pdf" ? (
          <iframe src={blobUrl} className="w-full h-[70vh]" title={att.filename} />
        ) : (
          <p className="p-4 text-sm text-gray-600">
            미리보기를 지원하지 않는 형식입니다. 다운로드 후 확인하세요.
          </p>
        )}
      </div>
    </Modal>
  );
}

function EntryTable({
  filingId,
  entries,
  onShowSource,
}: {
  filingId: string;
  entries: PayrollEntry[];
  onShowSource?: (event: SourceEvent) => void;
}) {
  const update = useUpdateEntry(filingId);
  const remove = useDeleteEntry(filingId);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<PayrollEntry>>({});

  const dupGroups = useMemo(() => {
    const map = new Map<string, PayrollEntry[]>();
    for (const e of entries) {
      const key = e.employee_id ?? `__name:${e.raw_name}`;
      const list = map.get(key) ?? [];
      list.push(e);
      map.set(key, list);
    }
    return map;
  }, [entries]);

  function dupInfoFor(e: PayrollEntry): { count: number; index: number } {
    const key = e.employee_id ?? `__name:${e.raw_name}`;
    const group = dupGroups.get(key) ?? [];
    const idx = group.findIndex((x) => x.id === e.id);
    return { count: group.length, index: idx + 1 };
  }

  function confirmDelete(e: PayrollEntry) {
    if (!window.confirm(`${e.raw_name} 항목을 삭제할까요?`)) return;
    remove.mutate(e.id, {
      onError: (err) => alert((err as Error).message),
    });
  }

  function startEdit(e: PayrollEntry) {
    setEditingId(e.id);
    setDraft({
      raw_name: e.raw_name,
      income_type: e.income_type,
      total_amount: e.total_amount,
      income_tax: e.income_tax,
      local_tax: e.local_tax,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft({});
  }

  function save(e: PayrollEntry) {
    const patch: Partial<PayrollEntry> = {};
    if (draft.raw_name !== undefined && draft.raw_name !== e.raw_name)
      patch.raw_name = draft.raw_name;
    if (draft.income_type !== undefined && draft.income_type !== e.income_type)
      patch.income_type = draft.income_type;
    if (draft.total_amount !== undefined && draft.total_amount !== e.total_amount)
      patch.total_amount = draft.total_amount;
    if (draft.income_tax !== undefined && draft.income_tax !== e.income_tax)
      patch.income_tax = draft.income_tax;
    if (draft.local_tax !== undefined && draft.local_tax !== e.local_tax)
      patch.local_tax = draft.local_tax;
    if (Object.keys(patch).length === 0) {
      cancelEdit();
      return;
    }
    update.mutate(
      { id: e.id, patch },
      { onSuccess: cancelEdit, onError: (err) => alert((err as Error).message) },
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs text-gray-500 border-b border-gray-200 dark:border-gray-800">
          <tr>
            <th className="text-left py-2 pr-3">상태</th>
            <th className="text-left py-2 pr-3">이름</th>
            <th className="text-left py-2 pr-3">소득구분</th>
            <th className="text-center py-2 pr-3">출처</th>
            <th className="text-right py-2 pr-3">총지급액</th>
            <th className="text-right py-2 pr-3">전월</th>
            <th className="text-right py-2 pr-3">소득세</th>
            <th className="text-right py-2 pr-3">지방세</th>
            <th className="text-center py-2 pr-3">승인</th>
            <th className="text-center py-2 pr-3">수정</th>
            <th className="text-left py-2">메모</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => {
            const isEditing = editingId === e.id;
            const dup = dupInfoFor(e);
            return (
              <tr
                key={e.id}
                onClick={() => !isEditing && startEdit(e)}
                className={
                  "border-b border-gray-100 dark:border-gray-900 cursor-pointer " +
                  (isEditing
                    ? "bg-blue-50 dark:bg-blue-950/30"
                    : dup.count > 1
                      ? "bg-amber-50/40 hover:bg-amber-50 dark:bg-amber-950/10 dark:hover:bg-amber-950/30"
                      : "hover:bg-gray-50 dark:hover:bg-gray-900/30")
                }
              >
                <td className="py-2 pr-3">
                  <div className="flex flex-col gap-0.5 items-start">
                    <MatchBadge status={e.match_status} />
                    {dup.count > 1 && (
                      <Badge tone="warning">중복 {dup.index}/{dup.count}</Badge>
                    )}
                  </div>
                </td>
                <td className="py-2 pr-3 font-medium">
                  {isEditing ? (
                    <input
                      className="w-24 px-1 py-0.5 border rounded text-sm"
                      value={draft.raw_name ?? ""}
                      onChange={(ev) => setDraft({ ...draft, raw_name: ev.target.value })}
                      onClick={(ev) => ev.stopPropagation()}
                    />
                  ) : (
                    e.raw_name
                  )}
                </td>
                <td className="py-2 pr-3">
                  {isEditing ? (
                    <select
                      className="px-1 py-0.5 border rounded text-sm"
                      value={draft.income_type ?? "WAGE"}
                      onChange={(ev) => setDraft({ ...draft, income_type: ev.target.value })}
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      <option value="WAGE">근로</option>
                      <option value="BUSINESS">사업</option>
                      <option value="OTHER">기타</option>
                      <option value="DAILY">일용</option>
                      <option value="RETIREMENT">퇴직</option>
                    </select>
                  ) : (
                    e.income_type
                  )}
                </td>
                <td
                  className="py-2 pr-3 text-center"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    if (e.source_event && onShowSource) onShowSource(e.source_event);
                  }}
                >
                  {e.source_event ? (
                    <button
                      className="text-[11px] text-blue-600 hover:underline leading-tight"
                      title="클릭하여 원본 메시지 보기"
                    >
                      {channelLabel(e.source_event.channel)}
                      <br />
                      <span className="text-gray-500">
                        {e.source_event.sender_name || "—"}
                      </span>
                    </button>
                  ) : (
                    <span className="text-[11px] text-gray-400">—</span>
                  )}
                </td>
                <td className="py-2 pr-3 text-right">
                  {isEditing ? (
                    <input
                      type="number"
                      className="w-24 px-1 py-0.5 border rounded text-sm text-right"
                      value={draft.total_amount ?? 0}
                      onChange={(ev) => setDraft({ ...draft, total_amount: Number(ev.target.value) || 0 })}
                      onClick={(ev) => ev.stopPropagation()}
                    />
                  ) : (
                    formatKrw(e.total_amount)
                  )}
                </td>
                <td
                  className={
                    "py-2 pr-3 text-right " +
                    (e.anomaly_notes?.large_change ? "text-amber-600 font-medium" : "text-gray-500")
                  }
                >
                  {e.prev_amount ? formatKrw(e.prev_amount) : "—"}
                </td>
                <td className="py-2 pr-3 text-right">
                  {isEditing ? (
                    <input
                      type="number"
                      className="w-20 px-1 py-0.5 border rounded text-sm text-right"
                      value={draft.income_tax ?? 0}
                      onChange={(ev) => setDraft({ ...draft, income_tax: Number(ev.target.value) || 0 })}
                      onClick={(ev) => ev.stopPropagation()}
                    />
                  ) : (
                    formatKrw(e.income_tax)
                  )}
                </td>
                <td className="py-2 pr-3 text-right">
                  {isEditing ? (
                    <input
                      type="number"
                      className="w-20 px-1 py-0.5 border rounded text-sm text-right"
                      value={draft.local_tax ?? 0}
                      onChange={(ev) => setDraft({ ...draft, local_tax: Number(ev.target.value) || 0 })}
                      onClick={(ev) => ev.stopPropagation()}
                    />
                  ) : (
                    formatKrw(e.local_tax)
                  )}
                </td>
                <td className="py-2 pr-3 text-center">
                  <input
                    type="checkbox"
                    checked={e.approved}
                    onClick={(ev) => ev.stopPropagation()}
                    onChange={(ev) =>
                      update.mutate({ id: e.id, patch: { approved: ev.target.checked } })
                    }
                  />
                </td>
                <td
                  className="py-2 pr-3 text-center"
                  onClick={(ev) => ev.stopPropagation()}
                >
                  {isEditing ? (
                    <div className="flex gap-1 justify-center">
                      <button
                        onClick={() => save(e)}
                        className="px-2 py-0.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                        disabled={update.isPending}
                      >
                        저장
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="px-2 py-0.5 text-xs border rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                      >
                        취소
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-2 justify-center">
                      <button
                        onClick={() => startEdit(e)}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => confirmDelete(e)}
                        className="text-xs text-red-600 hover:underline disabled:opacity-50"
                        disabled={remove.isPending}
                      >
                        삭제
                      </button>
                    </div>
                  )}
                </td>
                <td className="py-2 text-xs text-gray-500">
                  {e.anomaly_notes?.large_change
                    ? `전월 대비 ${(e.anomaly_notes.large_change as { ratio: number }).ratio}배 변동`
                    : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MatchBadge({ status }: { status: string }) {
  if (status === "MATCHED") return <Badge tone="success">기존직원</Badge>;
  if (status === "NEW_HIRE_SUSPECTED") return <Badge tone="info">신규</Badge>;
  if (status === "RESIGNATION_SUSPECTED") return <Badge tone="warning">퇴사</Badge>;
  return <Badge tone="warning">확인필요</Badge>;
}

function formatKrw(n: number | null | undefined): string {
  if (!n) return "—";
  return n.toLocaleString("ko-KR") + "원";
}

function channelLabel(ch: string | null): string {
  const map: Record<string, string> = {
    kakao: "카톡",
    email: "이메일",
    sms: "문자",
    voice: "전화",
    manual: "직접입력",
    public_url: "URL폼",
  };
  if (!ch) return "—";
  return map[ch] ?? ch;
}

function SourceEventModal({
  event,
  onClose,
}: {
  event: SourceEvent;
  onClose: () => void;
}) {
  return (
    <Modal open={true} onClose={onClose} title="원본 메시지 상세">
      <div className="space-y-3 text-sm">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="text-[11px] text-gray-500 mb-0.5">발신자</div>
            <div className="font-medium">{event.sender_name || "—"}</div>
          </div>
          <div>
            <div className="text-[11px] text-gray-500 mb-0.5">경로</div>
            <div className="font-medium">{channelLabel(event.channel)}</div>
          </div>
          <div>
            <div className="text-[11px] text-gray-500 mb-0.5">보낸 날짜</div>
            <div className="font-medium">{event.received_date || "—"}</div>
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">원본 텍스트</div>
          <pre className="whitespace-pre-wrap bg-gray-50 dark:bg-gray-900 rounded p-3 text-xs max-h-60 overflow-auto border border-gray-200 dark:border-gray-800">
            {event.raw_text || "(텍스트 없음)"}
          </pre>
        </div>
        {event.created_at && (
          <div className="text-[11px] text-gray-400">
            시스템 수신: {new Date(event.created_at).toLocaleString("ko-KR")}
          </div>
        )}
      </div>
    </Modal>
  );
}

void getToken; // ensure side-effects (browser-only file)
