"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";

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
import { Badge, Button, Modal } from "@/components/ui";
import type { CollectionSession, PayrollEntry, SessionAttachment, SourceEvent } from "@/lib/types";

/* ═══ Main Page ═══ */

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
  const [reviewOnly, setReviewOnly] = useState(false);
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);

  const allEntries = entries ?? [];
  const sessions = data?.sessions ?? [];

  useEffect(() => {
    if (sessions.length === 0) return;
    if (!activeSession || !sessions.find((s) => s.id === activeSession)) {
      setActiveSession(sessions[0].id);
    }
  }, [activeSession, sessions]);

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 rounded-[14px] bg-paper animate-pulse border border-ink-5" />
        ))}
      </div>
    );
  }

  const filing = data.filing;
  const selectedSession = sessions.find((s) => s.id === activeSession) ?? null;
  const selectedEntries = selectedSession
    ? allEntries.filter((e) => e.client_id === selectedSession.client_id)
    : [];
  const flaggedEntries = allEntries.filter(
    (e) =>
      (e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0 && !e.approved) ||
      e.match_status === "AMBIGUOUS",
  );

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
    <div className="-m-6 flex flex-col" style={{ height: "100dvh" }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-ink-4 bg-paper shrink-0">
        <div>
          <div className="flex items-center gap-2 text-xs text-ink-3 mb-0.5">
            <Link href="/dashboard" className="hover:underline">월별 신고</Link>
            <span>/</span>
            <span>{filing.period}</span>
          </div>
          <h1 className="text-lg font-bold tracking-tight">{filing.period} 원천세 신고</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ink-3">거래처 {filing.total_clients} · 항목 {filing.total_entries}</span>
          <Button variant="secondary" onClick={() => setShowBulkConfirm(true)} disabled={sendInvite.isPending}>
            {sendInvite.isPending ? "발송중..." : "자료요청 일괄전송"}
          </Button>
          <Button variant="secondary" onClick={downloadExcel}>위하고T 엑셀</Button>
          <Button>신고 완료 처리</Button>
        </div>
      </div>

      {/* Workflow strip */}
      <WorkflowStrip sessions={sessions} entries={allEntries} filingStatus={filing.status} />

      {/* Filter / toggle bar */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-ink-4 bg-paper shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xs text-ink-3">표시:</span>
          <TogglePill on={reviewOnly} onClick={() => setReviewOnly((v) => !v)}>
            확인필요만 보기
            {flaggedEntries.length > 0 && (
              <span className="tabular-nums font-bold opacity-85">{flaggedEntries.length}</span>
            )}
          </TogglePill>
          {!reviewOnly && selectedSession && (
            <span className="text-xs text-ink-3">
              선택: {selectedSession.client_name}
              {selectedEntries.filter((e) => e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0).length > 0 &&
                ` · 이상치 ${selectedEntries.filter((e) => e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0).length}건`}
            </span>
          )}
        </div>
        <span className="text-xs text-ink-3">AI 자동검증 ON · 임계치 ±30%</span>
      </div>

      {/* Body */}
      {reviewOnly ? (
        <ReviewOnlyMode filingId={id} entries={flaggedEntries} sessions={sessions} />
      ) : (
        <DefaultMode
          filingId={id}
          sessions={sessions}
          entries={allEntries}
          activeSession={activeSession}
          setActiveSession={setActiveSession}
          selectedSession={selectedSession}
          selectedEntries={selectedEntries}
        />
      )}

      {showBulkConfirm && (
        <Modal open={true} onClose={() => setShowBulkConfirm(false)} title="자료요청 일괄전송"
          footer={<>
            <Button variant="ghost" onClick={() => setShowBulkConfirm(false)}>취소</Button>
            <Button onClick={() => { setShowBulkConfirm(false); sendInvite.mutate(); }}>확인</Button>
          </>}>
          <p className="text-[13px] text-ink-2">모든 거래처에 자료요청 안내문을 보냅니다. 진행하시겠습니까?</p>
        </Modal>
      )}
    </div>
  );
}

/* ═══ Workflow Strip ═══ */

function WorkflowStrip({ sessions, entries, filingStatus }: {
  sessions: CollectionSession[];
  entries: PayrollEntry[];
  filingStatus: string;
}) {
  const total = sessions.length || 1;
  const sent = sessions.filter((s) => s.status !== "PENDING" && s.status !== "DRAFT").length;
  const received = sessions.filter((s) => s.has_responses).length;
  const verified = sessions.filter((s) => {
    const se = entries.filter((e) => e.client_id === s.client_id);
    return se.length > 0 && se.every((e) => !e.anomaly_notes || Object.keys(e.anomaly_notes).length === 0 || e.approved);
  }).length;
  const approved = sessions.filter((s) => {
    const se = entries.filter((e) => e.client_id === s.client_id);
    return se.length > 0 && se.every((e) => e.approved);
  }).length;
  const filed = filingStatus === "FILED" || filingStatus === "COMPLETED" ? 1 : 0;

  const stages: [string, string, number, number][] = [
    ["1", "초대 발송", sent, total],
    ["2", "수신", received, total],
    ["3", "검증", verified, received || 1],
    ["4", "승인", approved, received || 1],
    ["5", "신고", filed, 1],
  ];

  return (
    <div className="flex items-center px-5 py-2.5 border-b border-ink-4 bg-paper shrink-0">
      {stages.map(([n, label, done, stageTotal], i) => {
        const pct = stageTotal ? Math.round((done / stageTotal) * 100) : 0;
        const isLast = i === stages.length - 1;
        return (
          <div key={n} className="flex items-center" style={{ flex: isLast ? "0 0 auto" : 1 }}>
            <div className="flex flex-col gap-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-ink-3 tabular-nums">{n}</span>
                <span className="text-[13px] font-semibold">{label}</span>
                <span className="text-xs text-ink-3 tabular-nums">{done}/{stageTotal}</span>
              </div>
              <div className="h-[3px] bg-paper-2 rounded-full overflow-hidden w-40">
                <div className="h-full bg-ink rounded-full transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
            {!isLast && <div className="flex-1 border-t border-dashed border-ink-4 mx-4 min-w-4" />}
          </div>
        );
      })}
    </div>
  );
}

/* ═══ Toggle Pill ═══ */

function TogglePill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer ${
        on ? "bg-accent text-white border-accent" : "bg-paper text-ink-2 border-ink-4 hover:border-ink-3"
      }`}
    >
      <span className={`relative inline-block w-[22px] h-3 rounded-full transition-colors ${on ? "bg-white/35" : "bg-ink-4"}`}>
        <span className={`absolute top-[1px] w-[10px] h-[10px] rounded-full bg-white transition-all ${on ? "left-[11px]" : "left-[1px]"}`} />
      </span>
      {children}
    </button>
  );
}

/* ═══ Default 3-Pane Mode ═══ */

function DefaultMode({ filingId, sessions, entries, activeSession, setActiveSession, selectedSession, selectedEntries }: {
  filingId: string;
  sessions: CollectionSession[];
  entries: PayrollEntry[];
  activeSession: string | null;
  setActiveSession: (id: string | null) => void;
  selectedSession: CollectionSession | null;
  selectedEntries: PayrollEntry[];
}) {
  const [search, setSearch] = useState("");
  const filtered = search
    ? sessions.filter((s) => s.client_name.toLowerCase().includes(search.toLowerCase()))
    : sessions;

  return (
    <div className="flex flex-1 min-h-0">
      {/* LEFT — Session list */}
      <div className="w-64 border-r border-ink-4 bg-paper flex flex-col shrink-0">
        <div className="px-3 pt-3 pb-2 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold">거래처 {sessions.length}</span>
            <span className="text-xs text-ink-3">확인 {sessions.filter((s) => s.has_anomalies).length}</span>
          </div>
          <input
            type="text"
            placeholder="거래처 검색…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-ink-4 bg-paper px-2.5 py-1.5 text-xs placeholder:text-ink-3 outline-none focus:border-accent"
          />
        </div>
        <div className="flex-1 overflow-y-auto px-1.5 pb-3 space-y-0.5">
          {filtered.map((s) => (
            <SessionItem key={s.id} session={s} entries={entries} active={s.id === activeSession} onClick={() => setActiveSession(s.id)} />
          ))}
        </div>
      </div>

      {/* CENTER — Original docs */}
      <div className="w-[300px] border-r border-ink-4 bg-paper flex flex-col shrink-0">
        {selectedSession ? (
          <CenterPane key={selectedSession.id} filingId={filingId} session={selectedSession} entries={selectedEntries} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-ink-3">좌측에서 거래처를 선택하세요</div>
        )}
      </div>

      {/* RIGHT — AI table */}
      <div className="flex-1 min-w-0 flex flex-col">
        {selectedSession ? (
          <RightPane key={selectedSession.id} filingId={filingId} session={selectedSession} entries={selectedEntries} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-ink-3">거래처를 선택하면 AI 추출 결과가 표시됩니다</div>
        )}
      </div>
    </div>
  );
}

/* ═══ Session List Item ═══ */

function SessionItem({ session, entries, active, onClick }: {
  session: CollectionSession;
  entries: PayrollEntry[];
  active: boolean;
  onClick: () => void;
}) {
  const se = entries.filter((e) => e.client_id === session.client_id);
  const newHire = se.filter((e) => e.match_status === "NEW_HIRE_SUSPECTED").length;
  const resigned = se.filter((e) => e.match_status === "RESIGNATION_SUSPECTED").length;
  const review = se.filter(
    (e) => (e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0 && !e.approved) || e.match_status === "AMBIGUOUS",
  ).length;

  const status = (() => {
    if (review > 0) return "확인필요";
    if (se.length > 0 && se.every((e) => e.approved)) return "완료";
    if (se.length > 0) return "검토중";
    if (session.status === "SENT") return "수신대기";
    return "대기";
  })();

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-[10px] transition-all ${
        active ? "bg-paper-2 border border-ink-3" : "border border-transparent hover:bg-paper-2"
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          {review > 0 && <span className="w-1.5 h-1.5 rounded-full bg-alert shrink-0" />}
          <span className="text-[13px] font-semibold truncate">{session.client_name}</span>
        </div>
        <span className="text-[11px] text-ink-3 shrink-0">{status}</span>
      </div>
      <div className="flex gap-1.5 text-[11px] text-ink-3">
        {se.length > 0 && <span className="tabular-nums">{se.length}명</span>}
        {newHire > 0 && <><span>·</span><span className="tabular-nums">신규 {newHire}</span></>}
        {resigned > 0 && <><span>·</span><span className="tabular-nums">퇴사 {resigned}</span></>}
        {review > 0 && <><span>·</span><span className="tabular-nums text-alert font-semibold">확인 {review}</span></>}
        {se.length === 0 && <span>미수신</span>}
      </div>
    </button>
  );
}

/* ═══ Center Pane (Original Docs) ═══ */

function CenterPane({ filingId, session, entries }: {
  filingId: string;
  session: CollectionSession;
  entries: PayrollEntry[];
}) {
  const { data: attachments } = useSessionAttachments(filingId, session.id);
  const submit = useSubmitMessage(filingId);
  const requestCollection = useRequestCollection(filingId);
  const [showInput, setShowInput] = useState(false);
  const [text, setText] = useState("");
  const [senderName, setSenderName] = useState("");
  const [channel, setChannel] = useState("kakao");
  const [receivedDate, setReceivedDate] = useState(new Date().toISOString().slice(0, 10));
  const [zoomKey, setZoomKey] = useState<string | null>(null);

  const sourceTexts = useMemo(() => {
    const seen = new Set<string>();
    return entries
      .filter((e) => e.source_event?.raw_text)
      .map((e) => e.source_event!)
      .filter((se) => {
        if (seen.has(se.id)) return false;
        seen.add(se.id);
        return true;
      });
  }, [entries]);

  const publicUrl = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3000"}/r/${session.request_token}`;

  return (
    <>
      <div className="flex items-center justify-between px-3.5 py-3 border-b border-ink-4 shrink-0">
        <div>
          <div className="text-[13px] font-semibold">원본 자료</div>
          <div className="text-[11px] text-ink-3">
            {session.client_name}
            {sourceTexts.length > 0 && ` · ${channelLabel(sourceTexts[0].channel)} ${sourceTexts[0].received_date || ""}`}
          </div>
        </div>
        <div className="flex gap-1.5 text-[11px]">
          <a href={publicUrl} target="_blank" className="text-accent hover:underline">URL↗</a>
          <span className="text-ink-4">|</span>
          <button onClick={() => requestCollection.mutate(session.id)} disabled={requestCollection.isPending} className="text-accent hover:underline disabled:opacity-50">
            {requestCollection.isPending ? "발송중..." : "자료요청"}
          </button>
          <span className="text-ink-4">|</span>
          <button onClick={() => setShowInput((v) => !v)} className="text-accent hover:underline">수동입력</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {attachments && attachments.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {attachments.map((a) => (
              <AttachmentThumb key={a.storage_key} filingId={filingId} sessionId={session.id} att={a} onClick={() => setZoomKey(a.storage_key)} />
            ))}
          </div>
        )}

        {sourceTexts.map((se) => (
          <div key={se.id} className="p-3 rounded-lg bg-paper-2">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-xs">🤖</span>
              <span className="text-xs font-semibold">AI 텍스트 추출</span>
            </div>
            <div className="text-[13px] leading-relaxed text-ink-2 whitespace-pre-wrap">{se.raw_text}</div>
          </div>
        ))}

        {(!attachments || attachments.length === 0) && sourceTexts.length === 0 && (
          <div className="text-center py-8 text-sm text-ink-3">아직 수신된 자료가 없습니다</div>
        )}

        {showInput && (
          <div className="space-y-2 border-t border-ink-4 pt-3">
            <label className="block text-xs font-medium text-ink-2">메시지 원본 입력</label>
            <input placeholder="발신자명" value={senderName} onChange={(e) => setSenderName(e.target.value)}
              className="w-full rounded-md border border-ink-4 bg-paper px-2.5 py-1.5 text-xs outline-none focus:border-accent" />
            <div className="flex gap-1.5">
              <select value={channel} onChange={(e) => setChannel(e.target.value)}
                className="flex-1 rounded-md border border-ink-4 bg-paper px-2 py-1.5 text-xs">
                <option value="kakao">카카오톡</option>
                <option value="email">이메일</option>
                <option value="sms">문자</option>
                <option value="voice">전화</option>
                <option value="manual">직접</option>
              </select>
              <input type="date" value={receivedDate} onChange={(e) => setReceivedDate(e.target.value)}
                className="flex-1 rounded-md border border-ink-4 bg-paper px-2 py-1.5 text-xs" />
            </div>
            <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="메시지 원본을 붙여넣으세요..."
              className="w-full rounded-md border border-ink-4 bg-paper px-2.5 py-1.5 text-xs outline-none focus:border-accent resize-none" />
            <Button className="w-full" onClick={() => {
              if (!text.trim() || !senderName.trim()) return;
              submit.mutate(
                { sessionId: session.id, text, channel, sender_name: senderName.trim(), received_date: receivedDate },
                { onSuccess: () => { setText(""); setShowInput(false); }, onError: (e) => alert((e as Error).message) },
              );
            }} disabled={submit.isPending || !text.trim() || !senderName.trim()}>
              {submit.isPending ? "AI 파싱 중..." : "AI 파싱 실행"}
            </Button>
          </div>
        )}
      </div>

      {zoomKey && attachments && (
        <AttachmentZoomModal filingId={filingId} sessionId={session.id} att={attachments.find((a) => a.storage_key === zoomKey)!} onClose={() => setZoomKey(null)} />
      )}
    </>
  );
}

/* ═══ Right Pane (AI Table) ═══ */

function RightPane({ filingId, session, entries }: {
  filingId: string;
  session: CollectionSession;
  entries: PayrollEntry[];
}) {
  const update = useUpdateEntry(filingId);
  const remove = useDeleteEntry(filingId);
  const confirmWithClient = useConfirmWithClient(filingId);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<PayrollEntry>>({});
  const [confirmResult, setConfirmResult] = useState<{ sent: boolean; channel: string; error: string | null } | null>(null);

  function startEdit(e: PayrollEntry) {
    setEditingId(e.id);
    setDraft({ raw_name: e.raw_name, income_type: e.income_type, total_amount: e.total_amount, income_tax: e.income_tax, local_tax: e.local_tax });
  }
  function cancelEdit() { setEditingId(null); setDraft({}); }
  function save(e: PayrollEntry) {
    const patch: Partial<PayrollEntry> = {};
    if (draft.raw_name !== undefined && draft.raw_name !== e.raw_name) patch.raw_name = draft.raw_name;
    if (draft.income_type !== undefined && draft.income_type !== e.income_type) patch.income_type = draft.income_type;
    if (draft.total_amount !== undefined && draft.total_amount !== e.total_amount) patch.total_amount = draft.total_amount;
    if (draft.income_tax !== undefined && draft.income_tax !== e.income_tax) patch.income_tax = draft.income_tax;
    if (draft.local_tax !== undefined && draft.local_tax !== e.local_tax) patch.local_tax = draft.local_tax;
    if (Object.keys(patch).length === 0) { cancelEdit(); return; }
    update.mutate({ id: e.id, patch }, { onSuccess: cancelEdit, onError: (err) => alert((err as Error).message) });
  }

  return (
    <>
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-4 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold">AI 추출 결과</span>
          {entries.length > 0 && <span className="text-xs text-ink-3">{entries.filter((e) => e.approved).length}/{entries.length} 승인</span>}
        </div>
        <div className="flex gap-1.5">
          <Button variant="secondary" className="text-xs px-2.5 py-1.5"
            disabled={confirmWithClient.isPending || entries.length === 0}
            onClick={() => {
              setConfirmResult(null);
              confirmWithClient.mutate(
                { sessionId: session.id, channel: "auto" },
                { onSuccess: (res) => setConfirmResult(res), onError: (e) => setConfirmResult({ sent: false, channel: "error", error: (e as Error).message }) },
              );
            }}>
            {confirmWithClient.isPending ? "발송중..." : "확인요청"}
          </Button>
          <Button className="text-xs px-2.5 py-1.5"
            onClick={() => entries.filter((e) => !e.approved).forEach((e) => update.mutate({ id: e.id, patch: { approved: true } }))}
            disabled={entries.every((e) => e.approved)}>
            일괄 승인
          </Button>
        </div>
      </div>

      {confirmResult && (
        <div className={`px-4 py-1.5 text-xs border-b border-ink-4 ${confirmResult.sent ? "text-accent" : "text-alert"}`}>
          {confirmResult.sent ? `✅ ${confirmResult.channel}로 발송 완료` : `⚠️ 발송 실패 — ${confirmResult.error ?? "알 수 없는 오류"}`}
        </div>
      )}

      <div className="flex-1 overflow-auto">
        {entries.length > 0 ? (
          <table className="w-full text-[13px]">
            <thead className="text-[12px] text-ink-2 font-medium border-b-2 border-ink-4 sticky top-0 bg-paper">
              <tr>
                <th className="w-7 py-2.5 pl-4">
                  <input type="checkbox" checked={entries.length > 0 && entries.every((e) => e.approved)}
                    onChange={() => {
                      const all = entries.every((e) => e.approved);
                      entries.forEach((e) => { if (e.approved !== !all) update.mutate({ id: e.id, patch: { approved: !all } }); });
                    }} />
                </th>
                <th className="text-left py-2.5 pl-2">직원 · 구분</th>
                <th className="text-right py-2.5 pr-4">전월</th>
                <th className="text-right py-2.5 pr-4">이번달</th>
                <th className="text-right py-2.5 pr-4">변동</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const isEditing = editingId === e.id;
                const hasFlag = !!(e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0 && !e.approved);
                const diff = computeDiff(e);
                return (
                  <tr key={e.id} onClick={() => !isEditing && startEdit(e)}
                    className={`border-b border-ink-5 cursor-pointer transition-colors ${hasFlag ? "bg-red-50" : isEditing ? "bg-blue-50" : "hover:bg-gray-50"}`}>
                    <td className="py-3 pl-4" onClick={(ev) => ev.stopPropagation()}>
                      <input type="checkbox" checked={e.approved} onChange={(ev) => update.mutate({ id: e.id, patch: { approved: ev.target.checked } })} className="h-4 w-4" />
                    </td>
                    <td className="py-3 pl-2">
                      {isEditing ? (
                        <div className="space-y-1" onClick={(ev) => ev.stopPropagation()}>
                          <input className="w-24 px-1.5 py-1 border border-gray-300 rounded text-sm" value={draft.raw_name ?? ""} onChange={(ev) => setDraft({ ...draft, raw_name: ev.target.value })} />
                          <select className="px-1.5 py-1 border border-gray-300 rounded text-sm" value={draft.income_type ?? "WAGE"} onChange={(ev) => setDraft({ ...draft, income_type: ev.target.value })}>
                            <option value="WAGE">근로</option><option value="BUSINESS">사업</option><option value="OTHER">기타</option><option value="DAILY">일용</option><option value="RETIREMENT">퇴직</option>
                          </select>
                        </div>
                      ) : (
                        <div>
                          <div className="font-bold text-[13px] text-gray-900">{e.raw_name}</div>
                          <div className="text-[12px] text-gray-500">{e.a_code ?? "A01"} · {incomeLabel(e.income_type)}</div>
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-right text-gray-500 tabular-nums">{e.prev_amount ? formatKrw(e.prev_amount) : "—"}</td>
                    <td className="py-3 pr-4 text-right tabular-nums font-semibold">
                      {isEditing ? (
                        <input type="number" className="w-24 px-1.5 py-1 border border-gray-300 rounded text-sm text-right" value={draft.total_amount ?? 0}
                          onChange={(ev) => setDraft({ ...draft, total_amount: Number(ev.target.value) || 0 })} onClick={(ev) => ev.stopPropagation()} />
                      ) : (
                        <span className={hasFlag ? "text-red-600 font-bold" : "text-gray-900"}>{formatKrw(e.total_amount)}</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-right">
                      {isEditing ? (
                        <div className="flex gap-1 justify-end" onClick={(ev) => ev.stopPropagation()}>
                          <button onClick={() => save(e)} className="px-2.5 py-1 text-[12px] bg-blue-600 text-white rounded-md font-medium" disabled={update.isPending}>저장</button>
                          <button onClick={cancelEdit} className="px-2.5 py-1 text-[12px] border border-gray-300 rounded-md hover:bg-gray-50">취소</button>
                          <button onClick={() => { if (window.confirm(`${e.raw_name} 삭제?`)) { remove.mutate(e.id); cancelEdit(); } }}
                            className="px-2.5 py-1 text-[12px] text-red-600 border border-red-200 rounded-md hover:bg-red-50">삭제</button>
                        </div>
                      ) : diff ? (
                        <span className={`text-[12px] font-bold tabular-nums ${hasFlag ? "text-red-600" : "text-gray-400"}`}>{diff}</span>
                      ) : e.match_status === "NEW_HIRE_SUSPECTED" ? (
                        <span className="text-[12px] text-blue-600 font-bold">신규</span>
                      ) : e.match_status === "RESIGNATION_SUSPECTED" ? (
                        <span className="text-[12px] text-gray-500 font-semibold">퇴사</span>
                      ) : (
                        <span className="text-[12px] text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-ink-3">아직 파싱된 항목이 없습니다</div>
        )}
      </div>
    </>
  );
}

/* ═══ Review Only Mode ═══ */

function ReviewOnlyMode({ filingId, entries, sessions }: {
  filingId: string;
  entries: PayrollEntry[];
  sessions: CollectionSession[];
}) {
  const update = useUpdateEntry(filingId);
  const total = entries.length;
  const processed = entries.filter((e) => e.approved).length;

  if (total === 0) {
    return <div className="flex-1 flex items-center justify-center bg-paper-2 text-sm text-ink-3">확인이 필요한 항목이 없습니다</div>;
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-paper-2">
      <div className="flex items-center justify-between px-6 py-3 border-b border-ink-4 bg-paper shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-base font-bold text-alert">확인필요 {total}건</span>
          <span className="text-xs text-ink-3">이상치 {entries.filter((e) => e.anomaly_notes?.large_change).length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-[120px] h-1 bg-paper-2 border border-ink-4 rounded-full overflow-hidden">
            <div className="h-full bg-ink rounded-full transition-all" style={{ width: `${total ? (processed / total) * 100 : 0}%` }} />
          </div>
          <span className="text-xs tabular-nums"><b>{processed}</b> / {total} 처리</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-3">
        {entries.map((e, idx) => {
          const clientName = sessions.find((s) => s.client_id === e.client_id)?.client_name ?? "—";
          const prev = e.prev_amount ?? 0;
          const curr = e.total_amount;
          const pctChange = prev ? Math.round(((curr - prev) / prev) * 100) : null;
          const anomalyType = e.anomaly_notes?.large_change
            ? `이상치 ${pctChange != null && pctChange > 0 ? "+" : ""}${pctChange}%`
            : e.match_status === "AMBIGUOUS" ? "이름매칭" : "확인필요";
          const reason = e.anomaly_notes?.large_change
            ? `전월 대비 임계치(±30%) 초과. 변동 비율: ${pctChange}%`
            : e.match_status === "AMBIGUOUS"
              ? "기존 직원 목록에서 정확히 매칭되는 이름을 찾지 못했습니다."
              : "확인이 필요한 항목입니다.";

          if (e.approved) {
            return (
              <div key={e.id} className="rounded-[14px] border border-ink-4 bg-paper p-4 opacity-60">
                <div className="flex items-center gap-3">
                  <span className="text-xs tabular-nums text-ink-3">{idx + 1} / {total}</span>
                  <span className="text-xs font-semibold text-ink-3">{clientName} · {e.raw_name}</span>
                  <Badge tone="success">승인됨</Badge>
                </div>
              </div>
            );
          }

          return (
            <div key={e.id} className="rounded-[14px] border border-ink-4 bg-paper p-4 space-y-3 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs tabular-nums text-ink-3">{idx + 1} / {total}</span>
                  <span className="h-3 w-px bg-ink-4" />
                  <span className="text-xs text-alert font-semibold">{anomalyType}</span>
                  <span className="text-xs text-ink-3">{clientName} · {e.raw_name}</span>
                </div>
                <div className="flex gap-1.5">
                  <Button variant="ghost" className="text-xs px-2.5 py-1">건너뛰기</Button>
                  <Button variant="danger" className="text-xs px-2.5 py-1">거부</Button>
                  <Button className="text-xs px-2.5 py-1" onClick={() => update.mutate({ id: e.id, patch: { approved: true } })} disabled={update.isPending}>
                    승인 · 다음
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-ink-3 mb-1">전월</div>
                  <div className="rounded-lg border border-ink-4 p-3">
                    <div className="text-xl font-bold tabular-nums text-ink-3">{prev ? `₩ ${prev.toLocaleString()}` : "—"}</div>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-alert mb-1">이번달 · AI 추출</div>
                  <div className="rounded-lg border border-alert/30 bg-alert-50/30 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xl font-bold tabular-nums text-alert">₩ {curr.toLocaleString()}</div>
                      {pctChange != null && (
                        <div className="text-lg font-bold tabular-nums text-alert">{pctChange > 0 ? "+" : ""}{pctChange}%</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-lg bg-paper-2 p-3">
                <div className="text-xs font-semibold mb-0.5">판단 근거</div>
                <div className="text-[13px] text-ink-2">{reason}</div>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-ink-3">빠른 수정:</span>
                {prev > 0 && (
                  <button onClick={() => update.mutate({ id: e.id, patch: { total_amount: prev, approved: true } })}
                    className="px-2.5 py-1 rounded-full border border-ink-4 text-xs hover:bg-paper-2 transition-colors" disabled={update.isPending}>
                    전월값 사용
                  </button>
                )}
                <button className="px-2.5 py-1 rounded-full border border-ink-4 text-xs hover:bg-paper-2 transition-colors">직접 입력…</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ═══ Attachment Components ═══ */

function AttachmentThumb({ filingId, sessionId, att, onClick }: {
  filingId: string; sessionId: string; att: SessionAttachment; onClick: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const showInline = att.kind === "image";

  useEffect(() => {
    if (!showInline) return;
    let cancelled = false;
    let url: string | null = null;
    apiBlob(`/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`)
      .then((blob) => { if (cancelled) return; url = URL.createObjectURL(blob); setBlobUrl(url); })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [filingId, sessionId, att.storage_key, showInline]);

  return (
    <button type="button" onClick={onClick}
      className="group flex flex-col items-stretch text-left rounded-lg border border-ink-4 overflow-hidden hover:border-accent transition-colors">
      <div className="aspect-square bg-paper-2 flex items-center justify-center text-xs text-ink-3">
        {showInline && blobUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={blobUrl} alt={att.filename} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
        ) : showInline && !blobUrl && !error ? (
          <span>로딩...</span>
        ) : error ? (
          <span className="text-alert px-2 text-center">{error}</span>
        ) : (
          <KindIcon kind={att.kind} />
        )}
      </div>
      <div className="px-2 py-1 text-[11px] truncate">{att.filename}</div>
    </button>
  );
}

function KindIcon({ kind }: { kind: string }) {
  const label = { pdf: "PDF", excel: "엑셀", csv: "CSV", audio: "음성", image: "이미지" }[kind] ?? kind;
  return <div className="flex flex-col items-center gap-1"><div className="text-2xl">📎</div><div className="text-xs font-medium">{label}</div></div>;
}

function AttachmentZoomModal({ filingId, sessionId, att, onClose }: {
  filingId: string; sessionId: string; att: SessionAttachment; onClose: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    apiBlob(`/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`)
      .then((blob) => { if (cancelled) return; url = URL.createObjectURL(blob); setBlobUrl(url); })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [filingId, sessionId, att.storage_key]);

  return (
    <Modal open={true} onClose={onClose} title={att.filename}
      footer={blobUrl ? <a href={blobUrl} download={att.filename} className="text-sm text-accent hover:underline">다운로드</a> : null}>
      <div className="max-h-[70vh] overflow-auto flex items-center justify-center bg-paper-2 rounded">
        {error ? <p className="text-alert p-4">{error}</p>
          : !blobUrl ? <p className="p-8 text-ink-3">로딩 중...</p>
          : att.kind === "image" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={blobUrl} alt={att.filename} className="max-w-full" />
          ) : att.kind === "pdf" ? (
            <iframe src={blobUrl} className="w-full h-[70vh]" title={att.filename} />
          ) : (
            <p className="p-4 text-sm text-ink-2">미리보기 미지원. 다운로드 후 확인하세요.</p>
          )}
      </div>
    </Modal>
  );
}

function SourceEventModal({ event, onClose }: { event: SourceEvent; onClose: () => void }) {
  return (
    <Modal open={true} onClose={onClose} title="원본 메시지 상세">
      <div className="space-y-3 text-sm">
        <div className="grid grid-cols-3 gap-3">
          <div><div className="text-[11px] text-ink-3 mb-0.5">발신자</div><div className="font-medium">{event.sender_name || "—"}</div></div>
          <div><div className="text-[11px] text-ink-3 mb-0.5">경로</div><div className="font-medium">{channelLabel(event.channel)}</div></div>
          <div><div className="text-[11px] text-ink-3 mb-0.5">보낸 날짜</div><div className="font-medium">{event.received_date || "—"}</div></div>
        </div>
        <div>
          <div className="text-[11px] text-ink-3 mb-1">원본 텍스트</div>
          <pre className="whitespace-pre-wrap bg-paper-2 rounded p-3 text-xs max-h-60 overflow-auto border border-ink-4">{event.raw_text || "(텍스트 없음)"}</pre>
        </div>
      </div>
    </Modal>
  );
}

/* ═══ Utilities ═══ */

function formatKrw(n: number | null | undefined): string {
  if (!n) return "—";
  return n.toLocaleString("ko-KR") + "원";
}

function channelLabel(ch: string | null): string {
  if (!ch) return "—";
  return { kakao: "카톡", email: "이메일", sms: "문자", voice: "전화", manual: "직접입력", public_url: "URL폼" }[ch] ?? ch;
}

function incomeLabel(type: string): string {
  return { WAGE: "일반근로", BUSINESS: "사업소득", OTHER: "기타소득", DAILY: "일용근로", RETIREMENT: "퇴직소득" }[type] ?? type;
}

function computeDiff(e: PayrollEntry): string | null {
  if (!e.prev_amount || e.prev_amount === 0) return null;
  if (e.total_amount === e.prev_amount) return "—";
  const pct = Math.round(((e.total_amount - e.prev_amount) / e.prev_amount) * 100);
  return pct > 0 ? `+${pct}%` : `${pct}%`;
}

void getToken;
