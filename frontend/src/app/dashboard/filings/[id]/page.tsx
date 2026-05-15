"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import {
  useClients,
  useDeleteEntry,
  useFilingDashboard,
  useFilingEntries,
  useRequestCollection,
  useSendInvite,
  useSessionAttachments,
  useSubmitMessage,
  useUpdateEntry,
} from "@/lib/queries";
import { api, apiBlob, getToken } from "@/lib/api";
import { Badge, BezelCard, Button, Eyebrow, Modal } from "@/components/ui";
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
  const requestCollection = useRequestCollection(id);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);
  const [bulkPassword, setBulkPassword] = useState("");
  const [showSelectedRequestConfirm, setShowSelectedRequestConfirm] = useState(false);
  const [showExcelPopup, setShowExcelPopup] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);

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
          <div key={i} className="h-20 rounded-[14px] bg-gray-50 animate-pulse border border-gray-200" />
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

  // Deadline calculation
  const deadlineDay = 10;
  const [year, month] = filing.period.split("-").map(Number);
  const deadlineDate = new Date(month === 12 ? year + 1 : year, month === 12 ? 0 : month, deadlineDay);
  const daysLeft = Math.ceil((deadlineDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));

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

  async function downloadExcelForClient() {
    if (!selectedSession) return;
    try {
      const blob = await apiBlob(`/api/v1/filings/${id}/payroll-excel?client_id=${selectedSession.client_id}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `급여대장_${selectedSession.client_name}_${filing.period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <div className="-m-6 flex flex-col" style={{ height: "calc(100dvh - 48px)" }}>
      {/* Compact header — aligned with 3-pane columns on desktop, stacks on mobile */}
      <div className="flex flex-col md:flex-row md:h-10 border-b border-gray-200 bg-white shrink-0">
        {/* Left col — matches session list width */}
        <div className="hidden md:flex w-[240px] shrink-0 items-center gap-2 px-4 border-r border-gray-200">
          <span className={`text-[11px] font-semibold shrink-0 ${daysLeft <= 5 ? "text-red-600" : "text-gray-400"}`}>
            마감 D{daysLeft > 0 ? `-${daysLeft}` : daysLeft === 0 ? "-Day" : `+${Math.abs(daysLeft)}`} · {deadlineDate.getMonth() + 1}/{deadlineDate.getDate()}
          </span>
          <h1 className="text-[13px] font-bold tracking-tight truncate">
            <Link href="/dashboard" className="hover:text-blue-600 transition-colors">
              {Number(filing.period.split("-")[1])}월 원천세 신고
            </Link>
          </h1>
        </div>
        {/* Mobile-only top row */}
        <div className="flex md:hidden items-center justify-between px-3 py-2 gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <button onClick={() => setShowSidebar((v) => !v)} className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50" aria-label="거래처 목록">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <h1 className="text-[13px] font-bold tracking-tight truncate">
              <Link href="/dashboard" className="hover:text-blue-600 transition-colors">
                {Number(filing.period.split("-")[1])}월 원천세 신고
              </Link>
            </h1>
            <span className={`text-[11px] font-semibold shrink-0 ${daysLeft <= 5 ? "text-red-600" : "text-gray-400"}`}>
              D{daysLeft > 0 ? `-${daysLeft}` : daysLeft === 0 ? "-Day" : `+${Math.abs(daysLeft)}`}
            </span>
          </div>
        </div>
        {/* Center col — matches AI table */}
        <div className="flex-1 min-w-0 flex items-center justify-between px-3 md:px-4 py-1.5 md:py-0">
          <div className="flex items-center gap-2 md:gap-3 min-w-0">
            {!reviewOnly && selectedSession && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-600 border border-blue-100">
                {selectedSession.client_name}
              </span>
            )}
            {reviewOnly && (
              <button onClick={() => setReviewOnly(false)} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 text-red-600 border border-red-100 hover:bg-red-100 transition-colors cursor-pointer">
                확인필요만 보기 ✕
              </button>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
            <Button variant="secondary" onClick={() => setShowBulkConfirm(true)} disabled={sendInvite.isPending} className="!text-[12px] !px-2.5 !py-1 hidden sm:inline-flex">
              {sendInvite.isPending ? "발송중..." : "전체 업체 자료요청"}
            </Button>
            <Button variant="secondary" onClick={() => { if (selectedSession) setShowSelectedRequestConfirm(true); else alert("업체를 선택해주세요."); }} disabled={requestCollection.isPending} className="!text-[12px] !px-2.5 !py-1 hidden sm:inline-flex">
              {requestCollection.isPending ? "발송중..." : "선택업체 자료요청"}
            </Button>
            <div className="relative">
              <Button variant="ghost" onClick={() => setShowExcelPopup((v) => !v)} className="!text-[12px] !px-2.5 !py-1">엑셀다운로드</Button>
              {showExcelPopup && (<>
                <div className="fixed inset-0 z-40" onClick={() => setShowExcelPopup(false)} />
                <div className="absolute right-0 top-full mt-1 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1">
                  <button onClick={() => { setShowExcelPopup(false); downloadExcel(); }} className="w-full text-left px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50">전체 다운로드</button>
                  <button onClick={() => { setShowExcelPopup(false); downloadExcelForClient(); }} disabled={!selectedSession} className="w-full text-left px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50 disabled:opacity-40">선택 ({selectedSession?.client_name ?? "업체명"}) 다운로드</button>
                </div>
              </>)}
            </div>
          </div>
        </div>
        {/* Right col — matches original docs width (desktop only) */}
        <div className="hidden md:block w-[280px] shrink-0 border-l border-gray-200" />
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
          reviewOnly={reviewOnly}
          setReviewOnly={setReviewOnly}
          flaggedCount={flaggedEntries.length}
          showSidebar={showSidebar}
          setShowSidebar={setShowSidebar}
        />
      )}

      {showBulkConfirm && (
        <Modal open={true} onClose={() => { setShowBulkConfirm(false); setBulkPassword(""); }} title="전체 업체 자료요청"
          footer={<>
            <Button variant="ghost" onClick={() => { setShowBulkConfirm(false); setBulkPassword(""); }}>취소</Button>
            <Button disabled={!bulkPassword} onClick={() => { setShowBulkConfirm(false); setBulkPassword(""); sendInvite.mutate(); }}>발송</Button>
          </>}>
          <p className="text-[13px] text-gray-700 mb-3">모든 거래처에 자료요청 안내문을 이메일과 문자로 보냅니다.</p>
          <label className="block text-[12px] font-medium text-gray-600 mb-1">비밀번호 확인</label>
          <input type="password" value={bulkPassword} onChange={(e) => setBulkPassword(e.target.value)} placeholder="비밀번호를 입력하세요"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-[13px] outline-none focus:border-blue-500" />
        </Modal>
      )}

      {showSelectedRequestConfirm && selectedSession && (
        <Modal open={true} onClose={() => setShowSelectedRequestConfirm(false)} title="선택업체 자료요청"
          footer={<>
            <Button variant="ghost" onClick={() => setShowSelectedRequestConfirm(false)}>취소</Button>
            <Button onClick={() => { setShowSelectedRequestConfirm(false); requestCollection.mutate(selectedSession.id); }}>확인</Button>
          </>}>
          <p className="text-[13px] text-gray-700"><strong>{selectedSession.client_name}</strong>에 자료요청 안내문을 이메일과 문자로 보냅니다. 진행하시겠습니까?</p>
        </Modal>
      )}
    </div>
  );
}

/* ═══ Toggle Pill ═══ */

function TogglePill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all cursor-pointer ${
        on ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
      }`}
    >
      <span className={`relative inline-block w-[22px] h-3 rounded-full transition-colors ${on ? "bg-white/25" : "bg-gray-200"}`}>
        <span className={`absolute top-[1px] w-[10px] h-[10px] rounded-full bg-white shadow-sm transition-all ${on ? "left-[11px]" : "left-[1px]"}`} />
      </span>
      {children}
    </button>
  );
}

/* ═══ Default 3-Pane Mode ═══ */

function DefaultMode({ filingId, sessions, entries, activeSession, setActiveSession, selectedSession, selectedEntries, reviewOnly, setReviewOnly, flaggedCount, showSidebar, setShowSidebar }: {
  filingId: string;
  sessions: CollectionSession[];
  entries: PayrollEntry[];
  activeSession: string | null;
  setActiveSession: (id: string | null) => void;
  selectedSession: CollectionSession | null;
  selectedEntries: PayrollEntry[];
  reviewOnly: boolean;
  setReviewOnly: (v: boolean | ((prev: boolean) => boolean)) => void;
  flaggedCount: number;
  showSidebar: boolean;
  setShowSidebar: (v: boolean) => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "review" | "waiting">("all");
  const [highlightEventId, setHighlightEventId] = useState<string | null>(null);

  const isReview = (s: CollectionSession) => {
    const se = entries.filter((e) => e.client_id === s.client_id);
    return se.length > 0 && se.some((e) => {
      if (e.approved) return false;
      if (e.match_status === "UNCONFIRMED") return true;
      const notes = e.anomaly_notes;
      return (notes && Object.keys(notes).length > 0) || e.match_status === "AMBIGUOUS";
    });
  };
  const isWaiting = (s: CollectionSession) => !s.has_responses;

  const filtered = sessions.filter((s) => {
    if (search && !s.client_name.toLowerCase().includes(search.toLowerCase())) return false;
    if (filter === "review") return isReview(s);
    if (filter === "waiting") return isWaiting(s);
    return true;
  });

  const reviewCount = sessions.filter(isReview).length;
  const waitingCount = sessions.filter(isWaiting).length;

  return (
    <div className="flex flex-1 min-h-0 bg-gray-50 relative">
      {/* Mobile overlay backdrop */}
      {showSidebar && (
        <div className="fixed inset-0 bg-black/30 z-20 md:hidden" onClick={() => setShowSidebar(false)} />
      )}
      {/* LEFT — Session list */}
      <div className={`${showSidebar ? "translate-x-0" : "-translate-x-full"} md:translate-x-0 fixed md:static inset-y-0 left-0 z-30 md:z-auto w-[260px] md:w-[240px] border-r border-gray-200 bg-white flex flex-col shrink-0 transition-transform duration-200 ease-in-out`}>
        <div className="px-3 pt-3 pb-2 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[14px] font-semibold">거래처 {sessions.length}</span>
            <TogglePill on={reviewOnly} onClick={() => setReviewOnly((v: boolean) => !v)}>
              확인필요만 보기
            </TogglePill>
          </div>
          <div className="inline-flex items-center p-0.5 rounded-full bg-gray-50 border border-gray-200 text-[11px]">
            {([["all", `전체`], ["review", `확인 ${reviewCount}`], ["waiting", `대기 ${waitingCount}`]] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-2 py-1 rounded-full font-medium transition-all ${filter === key ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-700"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="거래처 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs placeholder:text-gray-400 outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
          {filtered.map((s) => (
            <SessionItem key={s.id} session={s} entries={entries} active={s.id === activeSession} onClick={() => { setActiveSession(s.id); setShowSidebar(false); }} />
          ))}
        </div>
      </div>

      {/* CENTER — AI table */}
      <div className="flex-1 min-w-0 bg-white flex flex-col">
        {selectedSession ? (
          <RightPane key={selectedSession.id} filingId={filingId} session={selectedSession} entries={selectedEntries}
            highlightEventId={highlightEventId} onHighlight={setHighlightEventId} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">AI 추출 결과</div>
        )}
      </div>

      {/* RIGHT — Original docs (hidden on mobile) */}
      <div className="hidden md:flex w-[280px] border-l border-gray-200 bg-white flex-col shrink-0">
        {selectedSession ? (
          <CenterPane key={selectedSession.id} filingId={filingId} session={selectedSession} entries={selectedEntries}
            highlightEventId={highlightEventId} onHighlight={setHighlightEventId} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">원본 자료</div>
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
  const unconfirmed = se.filter((e) => e.match_status === "UNCONFIRMED").length;
  const review = se.filter(
    (e) => {
      if (e.approved) return false;
      if (e.match_status === "UNCONFIRMED") return true;
      const notes = e.anomaly_notes;
      return (notes && Object.keys(notes).length > 0) || e.match_status === "AMBIGUOUS";
    },
  ).length;

  const status = (() => {
    if (review > 0) return "확인필요";
    if (se.length > 0 && se.every((e) => e.approved)) return "완료";
    if (se.length > 0) return "검토중";
    if (session.status === "SENT") return "수신대기";
    return "대기";
  })();

  const isDotted = status === "수신대기" || status === "대기";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-[12px] transition-all ${
        active
          ? "bg-blue-50 border border-blue-300 shadow-[0_1px_0_rgba(37,99,235,0.06),0_8px_22px_-14px_rgba(37,99,235,0.15)]"
          : "border border-transparent hover:bg-gray-50"
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1 min-w-0">
          {review > 0 && <span className="w-[7px] h-[7px] rounded-full bg-red-500 shrink-0 shadow-[0_0_0_3px_rgba(185,28,28,0.10)]" />}
          {isDotted && review === 0 && <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${active ? "bg-blue-500" : "bg-gray-300"}`} />}
          {!isDotted && review === 0 && <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${active ? "bg-blue-500" : "bg-green-500"}`} />}
          <span className="text-[13px] font-semibold truncate">{session.client_name}</span>
      </div>
      <div className="flex gap-1.5 text-[11.5px] text-gray-500">
        {se.length > 0 && <span className="tabular-nums">{se.length}명</span>}
        {newHire > 0 && <><span className="opacity-50">·</span><span className="tabular-nums">신규 {newHire}</span></>}
        {resigned > 0 && <><span className="opacity-50">·</span><span className="tabular-nums">퇴사 {resigned}</span></>}
        {unconfirmed > 0 && <><span className="opacity-50">·</span><span className="tabular-nums text-amber-600 font-bold">미확인 {unconfirmed}</span></>}
        {review > 0 && <><span className="opacity-50">·</span><span className="tabular-nums text-red-600 font-bold">확인 {review}</span></>}
        {se.length === 0 && <span>미수신</span>}
      </div>
    </button>
  );
}

/* ═══ Center Pane (Original Docs) ═══ */

function CenterPane({ filingId, session, entries, highlightEventId, onHighlight }: {
  filingId: string;
  session: CollectionSession;
  entries: PayrollEntry[];
  highlightEventId: string | null;
  onHighlight: (id: string | null) => void;
}) {
  const qc = useQueryClient();
  const { data: attachments } = useSessionAttachments(filingId, session.id);
  const submit = useSubmitMessage(filingId);
  const requestCollection = useRequestCollection(filingId);
  const [showInput, setShowInput] = useState(false);
  const [text, setText] = useState("");
  const [senderName, setSenderName] = useState("");
  const [channel, setChannel] = useState("kakao");
  const [receivedDate, setReceivedDate] = useState(new Date().toISOString().slice(0, 10));
  const [zoomKey, setZoomKey] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SessionAttachment | null>(null);
  const [deletedKeys, setDeletedKeys] = useState<Set<string>>(new Set());
  const [deleteEventTarget, setDeleteEventTarget] = useState<SourceEvent | null>(null);
  const [deletedEventIds, setDeletedEventIds] = useState<Set<string>>(new Set());

  const sourceTexts = useMemo(() => {
    const seen = new Set<string>();
    return entries
      .filter((e) => e.source_event?.raw_text)
      .map((e) => e.source_event!)
      .filter((se) => {
        if (seen.has(se.id)) return false;
        seen.add(se.id);
        return true;
      })
      .filter((se) => !deletedEventIds.has(se.id));
  }, [entries, deletedEventIds]);

  const visibleAttachments = (attachments ?? []).filter((a) => !deletedKeys.has(a.storage_key));
  const publicUrl = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3000"}/r/${session.request_token}`;

  return (
    <>
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">원본 자료</span>
          <div className="text-[13px] font-semibold mt-0.5">{session.client_name}</div>
        </div>
        <div className="flex gap-1.5 text-[10px]">
          <a href={publicUrl} target="_blank" className="text-blue-600 hover:underline">URL</a>
          <span className="text-gray-300">|</span>
          <button onClick={() => requestCollection.mutate(session.id)} disabled={requestCollection.isPending} className="text-blue-600 hover:underline disabled:opacity-50">
            {requestCollection.isPending ? "발송중..." : "자료요청"}
          </button>
          <span className="text-gray-300">|</span>
          <button onClick={() => setShowInput((v) => !v)} className="text-blue-600 hover:underline">수동입력</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {visibleAttachments.length > 0 && (
          <div className="grid grid-cols-3 gap-1.5">
            {visibleAttachments.map((a) => (
              <div key={a.storage_key}
                className={`rounded-lg transition-all ${highlightEventId === a.event_id ? "ring-2 ring-blue-400" : ""}`}
                onClick={() => onHighlight(highlightEventId === a.event_id ? null : a.event_id)}>
                <AttachmentThumb filingId={filingId} sessionId={session.id} att={a}
                  onClick={() => setZoomKey(a.storage_key)}
                  onDelete={() => setDeleteTarget(a)} />
              </div>
            ))}
          </div>
        )}

        {sourceTexts.map((se) => (
          <div key={se.id}
            onClick={() => onHighlight(highlightEventId === se.id ? null : se.id)}
            className={`group relative p-2 rounded-lg border cursor-pointer transition-all ${
              highlightEventId === se.id
                ? "bg-blue-50 border-blue-400 ring-1 ring-blue-400"
                : "bg-gray-50 border-gray-200 hover:border-gray-300"
            }`}>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">텍스트</span>
              <button onClick={(ev) => { ev.stopPropagation(); setDeleteEventTarget(se); }}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] text-red-500 hover:text-red-700">삭제</button>
            </div>
            <div className="text-[12px] leading-relaxed text-gray-700 whitespace-pre-wrap mt-1 max-h-32 overflow-y-auto">{se.raw_text}</div>
          </div>
        ))}

        {visibleAttachments.length === 0 && sourceTexts.length === 0 && (
          <div className="text-center py-6 text-xs text-gray-400">수신된 자료 없음</div>
        )}

        {showInput && (
          <div className="space-y-2 border-t border-gray-200 pt-2">
            <label className="block text-xs font-medium text-gray-700">수동 입력</label>
            <input placeholder="발신자명" value={senderName} onChange={(e) => setSenderName(e.target.value)}
              className="w-full rounded-md border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-blue-500" />
            <div className="flex gap-1.5">
              <select value={channel} onChange={(e) => setChannel(e.target.value)}
                className="flex-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs">
                <option value="kakao">카카오톡</option>
                <option value="email">이메일</option>
                <option value="sms">문자</option>
                <option value="voice">전화</option>
                <option value="manual">직접</option>
              </select>
              <input type="date" value={receivedDate} onChange={(e) => setReceivedDate(e.target.value)}
                className="flex-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs" />
            </div>
            <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="메시지 원본을 붙여넣으세요..."
              className="w-full rounded-md border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-blue-500 resize-none" />
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

      {deleteTarget && (
        <DeleteAttachmentModal
          filename={deleteTarget.filename}
          onClose={() => setDeleteTarget(null)}
          onConfirm={(deletedBy) => {
            setDeletedKeys((prev) => new Set([...prev, deleteTarget.storage_key]));
            setDeleteTarget(null);
            api(`/api/v1/filings/${filingId}/sessions/${session.id}/attachments?key=${encodeURIComponent(deleteTarget.storage_key)}&deleted_by=${encodeURIComponent(deletedBy)}`, { method: "DELETE" })
              .then(() => {
                qc.invalidateQueries({ queryKey: ["filings", filingId, "sessions", session.id, "attachments"] });
                qc.invalidateQueries({ queryKey: ["filings", filingId, "entries"] });
              })
              .catch(() => {});
          }}
        />
      )}

      {deleteEventTarget && (
        <DeleteAttachmentModal
          filename={`텍스트 메시지 (${(deleteEventTarget.raw_text ?? "").slice(0, 20)}...)`}
          onClose={() => setDeleteEventTarget(null)}
          onConfirm={(deletedBy) => {
            setDeletedEventIds((prev) => new Set([...prev, deleteEventTarget.id]));
            setDeleteEventTarget(null);
            api(`/api/v1/filings/${filingId}/sessions/${session.id}/events/${deleteEventTarget.id}?deleted_by=${encodeURIComponent(deletedBy)}`, { method: "DELETE" })
              .then(() => {
                qc.invalidateQueries({ queryKey: ["filings", filingId, "entries"] });
                qc.invalidateQueries({ queryKey: ["filings", filingId, "dashboard"] });
              })
              .catch(() => {});
          }}
        />
      )}
    </>
  );
}

/* ═══ Right Pane (AI Table) ═══ */

function RightPane({ filingId, session, entries, highlightEventId, onHighlight }: {
  filingId: string;
  session: CollectionSession;
  entries: PayrollEntry[];
  highlightEventId: string | null;
  onHighlight: (id: string | null) => void;
}) {
  const update = useUpdateEntry(filingId);
  const remove = useDeleteEntry(filingId);
  const { data: clients } = useClients();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<PayrollEntry>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const clientDetail = clients?.find((c) => c.id === session.client_id);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleSelectAll() {
    if (selected.size === entries.length) setSelected(new Set());
    else setSelected(new Set(entries.map((e) => e.id)));
  }
  function bulkDelete() {
    if (selected.size === 0) return;
    if (!window.confirm(`선택된 ${selected.size}건을 삭제하시겠습니까?`)) return;
    selected.forEach((id) => remove.mutate(id));
    setSelected(new Set());
  }

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
      <div className="px-4 py-3 border-b border-gray-100 shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[10.5px] font-semibold uppercase tracking-widest text-gray-500">AI 추출 결과</span>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[15px] font-semibold">{session.client_name} · {entries.length}명</span>
              {entries.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-600 border border-blue-100">
                  {entries.filter((e) => e.approved).length}/{entries.length} 승인
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-1.5">
            {selected.size > 0 && (
              <>
                <Button variant="primary" className="text-xs px-3 py-1.5"
                  onClick={() => {
                    selected.forEach((id) => {
                      const entry = entries.find((e) => e.id === id);
                      if (entry && !entry.approved) update.mutate({ id, patch: { approved: true } });
                    });
                    setSelected(new Set());
                  }}
                  disabled={update.isPending}>
                  {update.isPending ? "승인중..." : `일괄 승인 (${selected.size})`}
                </Button>
                <Button variant="danger" className="text-xs px-3 py-1.5" onClick={bulkDelete} disabled={remove.isPending}>
                  {remove.isPending ? "삭제중..." : `일괄 삭제 (${selected.size})`}
                </Button>
              </>
            )}
          </div>
        </div>
        {clientDetail && (
          <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-500 overflow-x-auto">
            {clientDetail.business_number && <span>사업자 <strong className="text-gray-700">{clientDetail.business_number}</strong></span>}
            {clientDetail.representative && <><span className="text-gray-300">|</span><span>대표 <strong className="text-gray-700">{clientDetail.representative}</strong></span></>}
            {clientDetail.contact_phone && <><span className="text-gray-300">|</span><span><strong className="text-gray-700">{clientDetail.contact_phone}</strong></span></>}
            {clientDetail.contact_email && <><span className="text-gray-300">|</span><span><strong className="text-gray-700">{clientDetail.contact_email}</strong></span></>}
            {clientDetail.is_corporation !== undefined && <><span className="text-gray-300">|</span><span>{clientDetail.is_corporation ? "법인" : "개인"}</span></>}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {entries.length > 0 ? (
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-gray-200">
                <th className="w-8 py-2.5 pl-4">
                  <input type="checkbox" checked={entries.length > 0 && selected.size === entries.length}
                    onChange={toggleSelectAll} title="전체 선택" className="h-3.5 w-3.5 accent-blue-600" />
                </th>
                <th className="text-left py-2.5 pl-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">직원 · 구분</th>
                <th className="text-right py-2.5 pr-3.5 text-[11px] font-medium text-gray-500 uppercase tracking-wider">전월</th>
                <th className="text-right py-2.5 pr-3.5 text-[11px] font-medium text-gray-500 uppercase tracking-wider">이번달</th>
                <th className="text-right py-2.5 pr-3.5 text-[11px] font-medium text-gray-500 uppercase tracking-wider">변동</th>
                <th className="text-right py-2.5 pr-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">액션</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const isEditing = editingId === e.id;
                const hasFlag = !!(e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0 && !e.approved);
                const fieldChanges = (e.anomaly_notes?.field_changes ?? null) as Record<string, { prev: number; curr: number }> | null;
                const diff = computeDiff(e);
                return (
                  <tr key={e.id}
                    onClick={() => e.collection_event_id && onHighlight(highlightEventId === e.collection_event_id ? null : e.collection_event_id)}
                    className={`border-b border-gray-50 transition-colors cursor-pointer ${
                      highlightEventId && e.collection_event_id === highlightEventId
                        ? "bg-blue-50 ring-1 ring-inset ring-blue-300"
                        : hasFlag ? "bg-red-50/60" : isEditing ? "bg-blue-50/60" : "hover:bg-gray-50"
                    }`}>
                    <td className="py-3 pl-4">
                      <input type="checkbox" checked={selected.has(e.id)} onChange={() => toggleSelect(e.id)} onClick={(ev) => ev.stopPropagation()} className="h-3.5 w-3.5 accent-blue-600" />
                    </td>
                    <td className="py-3 pl-2">
                      {isEditing ? (
                        <div className="space-y-1">
                          <input className="w-24 px-1.5 py-1 border border-gray-300 rounded text-sm" value={draft.raw_name ?? ""} onChange={(ev) => setDraft({ ...draft, raw_name: ev.target.value })} />
                          <select className="px-1.5 py-1 border border-gray-300 rounded text-sm" value={draft.income_type ?? "WAGE"} onChange={(ev) => setDraft({ ...draft, income_type: ev.target.value })}>
                            <option value="WAGE">근로</option><option value="BUSINESS">사업</option><option value="OTHER">기타</option><option value="DAILY">일용</option><option value="RETIREMENT">퇴직</option>
                          </select>
                        </div>
                      ) : (
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-[13px] text-gray-900 tracking-tight">{e.raw_name}</span>
                            {e.approved && <span className="text-[10px] text-green-600">✓</span>}
                          </div>
                          <div className="text-[11px] text-gray-500 mt-0.5">{e.a_code ?? "A01"} · {incomeLabel(e.income_type)}</div>
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-3.5 text-right text-gray-500 tabular-nums">{e.prev_amount ? formatKrw(e.prev_amount) : "—"}</td>
                    <td className="py-3 pr-3.5 text-right tabular-nums font-semibold">
                      {isEditing ? (
                        <input type="number" className="w-24 px-1.5 py-1 border border-gray-300 rounded text-sm text-right" value={draft.total_amount ?? 0}
                          onChange={(ev) => setDraft({ ...draft, total_amount: Number(ev.target.value) || 0 })} />
                      ) : (
                        <div>
                          <span className={hasFlag ? "text-red-600 font-bold" : "text-gray-900"}>{formatKrw(e.total_amount)}</span>
                          {fieldChanges && (
                            <div className="flex flex-wrap gap-0.5 mt-0.5 justify-end">
                              {Object.keys(fieldChanges).map((k) => (
                                <span key={k} className="text-[9px] px-1 py-px rounded bg-red-100 text-red-600 font-medium" title={`전월 ${formatKrw(fieldChanges[k].prev)} → ${formatKrw(fieldChanges[k].curr)}`}>
                                  {FIELD_LABELS[k] ?? k}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-3.5 text-right">
                      {diff ? (
                        <DiffPill diff={diff} hasFlag={hasFlag} />
                      ) : e.match_status === "NEW_HIRE_SUSPECTED" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-600">신규</span>
                      ) : e.match_status === "RESIGNATION_SUSPECTED" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-600">퇴사</span>
                      ) : e.match_status === "UNCONFIRMED" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-600">미확인</span>
                      ) : (
                        <span className="text-[11px] text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-right" onClick={(ev) => ev.stopPropagation()}>
                      {isEditing ? (
                        <div className="flex gap-1 justify-end">
                          <button onClick={() => save(e)} className="px-2 py-1 text-[11px] bg-blue-600 text-white rounded-full font-medium" disabled={update.isPending}>저장</button>
                          <button onClick={cancelEdit} className="px-2 py-1 text-[11px] border border-gray-300 rounded-full hover:bg-gray-50">취소</button>
                        </div>
                      ) : (
                        <div className="flex gap-1 justify-end">
                          <button onClick={() => startEdit(e)} className="px-2 py-1 text-[11px] text-blue-600 border border-blue-200 rounded-full hover:bg-blue-50">수정</button>
                          <button onClick={() => { if (window.confirm(`${e.raw_name} 삭제?`)) remove.mutate(e.id); }}
                            className="px-2 py-1 text-[11px] text-red-600 border border-red-200 rounded-full hover:bg-red-50">삭제</button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">아직 파싱된 항목이 없습니다</div>
        )}
      </div>
    </>
  );
}

/* ═══ Diff Pill ═══ */

function DiffPill({ diff, hasFlag }: { diff: string; hasFlag: boolean }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums ${
      hasFlag ? "bg-red-50 text-red-600" : "bg-gray-100 text-gray-500"
    }`}>
      {diff}
    </span>
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
  const [filterType, setFilterType] = useState<"all" | "anomaly" | "name" | "unconfirmed">("all");

  const hasAnomaly = (e: PayrollEntry) => !!(e.anomaly_notes?.large_change || e.anomaly_notes?.abnormal_amount);
  const unconfirmedCount = entries.filter((e) => e.match_status === "UNCONFIRMED").length;

  const filteredEntries = entries.filter((e) => {
    if (filterType === "anomaly") return hasAnomaly(e);
    if (filterType === "name") return e.match_status === "AMBIGUOUS";
    if (filterType === "unconfirmed") return e.match_status === "UNCONFIRMED";
    return true;
  });

  const anomalyCount = entries.filter(hasAnomaly).length;
  const nameCount = entries.filter((e) => e.match_status === "AMBIGUOUS").length;

  if (total === 0) {
    return <div className="flex-1 flex items-center justify-center bg-gray-50 text-sm text-gray-400">확인이 필요한 항목이 없습니다</div>;
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-50">
      <div className="flex items-center justify-between px-6 py-3.5 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-[10.5px] font-semibold uppercase tracking-widest text-red-600">확인필요 큐</span>
            <div className="text-[20px] font-bold tracking-tight">{total}건 남음</div>
          </div>
          <div className="h-9 w-px bg-gray-200" />
          <div className="flex items-center gap-1.5">
            {([["all", `전체 ${total}`], ["unconfirmed", `미확인 ${unconfirmedCount}`], ["anomaly", `이상치 ${anomalyCount}`], ["name", `이름매칭 ${nameCount}`]] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilterType(key)}
                className={`px-2.5 py-1 rounded-full text-[12px] font-medium transition-all ${
                  filterType === key ? "bg-gray-900 text-white" : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">처리</span>
          <div className="w-[120px] h-1.5 bg-gray-100 border border-gray-200 rounded-full overflow-hidden">
            <div className="h-full bg-gray-900 rounded-full transition-all" style={{ width: `${total ? (processed / total) * 100 : 0}%` }} />
          </div>
          <span className="text-sm tabular-nums"><b>{processed}</b> <span className="text-gray-500">/ {total}</span></span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-3.5">
        {filteredEntries.map((e, idx) => {
          const clientName = sessions.find((s) => s.client_id === e.client_id)?.client_name ?? "—";
          const prev = e.prev_amount ?? 0;
          const curr = e.total_amount;
          const pctChange = prev ? Math.round(((curr - prev) / prev) * 100) : null;
          const anomalyType = e.match_status === "UNCONFIRMED"
            ? "미확인"
            : e.anomaly_notes?.abnormal_amount
              ? "비정상 금액"
              : e.anomaly_notes?.large_change
                ? `이상치 ${pctChange != null && pctChange > 0 ? "+" : ""}${pctChange}%`
                : e.match_status === "AMBIGUOUS" ? "이름매칭" : "확인필요";
          const reason = e.match_status === "UNCONFIRMED"
            ? `전월에 ₩${(e.prev_amount ?? 0).toLocaleString()} 지급. 이번달 자료에 없음 — 계속근무 시 정확한 급여를, 퇴사 시 퇴사일을 확인하세요.`
            : e.anomaly_notes?.abnormal_amount
              ? (e.anomaly_notes.abnormal_amount as { reason?: string }).reason ?? "금액을 확인해주세요."
              : e.anomaly_notes?.large_change
                ? `전월 대비 임계치(±30%) 초과. 변동 비율: ${pctChange}%`
                : e.match_status === "AMBIGUOUS"
                  ? "기존 직원 목록에서 정확히 매칭되는 이름을 찾지 못했습니다."
                  : "확인이 필요한 항목입니다.";

          if (e.approved) {
            return (
              <div key={e.id} className="rounded-[14px] border border-gray-200 bg-white p-4 opacity-60">
                <div className="flex items-center gap-3">
                  <span className="text-xs tabular-nums text-gray-500">{idx + 1} / {total}</span>
                  <span className="text-xs font-semibold text-gray-500">{clientName} · {e.raw_name}</span>
                  <Badge tone="success">승인됨</Badge>
                </div>
              </div>
            );
          }

          return (
            <BezelCard key={e.id}>
              <div className="p-5 space-y-4">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {/* Ring progress */}
                    <RingProgress current={idx + 1} total={total} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11.5px] font-semibold bg-red-50 text-red-600">
                          {anomalyType}
                        </span>
                        <span className="text-xs text-gray-500">{clientName}</span>
                      </div>
                      <div className="text-[20px] font-bold tracking-tight mt-1">{e.raw_name}</div>
                    </div>
                  </div>
                  <div className="flex gap-1.5">
                    <Button variant="ghost" className="text-xs px-2.5 py-1">건너뛰기</Button>
                    <Button variant="danger" className="text-xs px-2.5 py-1">거부</Button>
                    <Button className="text-xs px-2.5 py-1" onClick={() => update.mutate({ id: e.id, patch: { approved: true } })} disabled={update.isPending}>
                      승인하고 다음
                    </Button>
                  </div>
                </div>

                {/* Prev vs Current comparison */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-[10.5px] font-semibold uppercase tracking-widest text-gray-500 mb-1 block">전월</span>
                    <div className="rounded-[12px] border border-gray-200 bg-gray-50 p-4">
                      <div className="text-[22px] font-bold tabular-nums text-gray-500 tracking-tight">
                        {prev ? `₩ ${prev.toLocaleString()}` : "—"}
                      </div>
                    </div>
                  </div>
                  <div>
                    <span className="text-[10.5px] font-semibold uppercase tracking-widest text-red-600 mb-1 block">이번달 · AI 추출</span>
                    <div className="rounded-[12px] border border-red-200/60 bg-red-50/40 p-4">
                      <div className="flex items-center justify-between">
                        <div className="text-[22px] font-bold tabular-nums text-red-600 tracking-tight">₩ {curr.toLocaleString()}</div>
                        {pctChange != null && (
                          <div className="text-lg font-bold tabular-nums text-red-600">{pctChange > 0 ? "+" : ""}{pctChange}%</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Reason */}
                <div className="rounded-[12px] bg-gray-50 border border-gray-200 p-3.5">
                  <span className="text-[10.5px] font-semibold uppercase tracking-widest text-gray-500 mb-1 block">판단 근거</span>
                  <div className="text-[13px] text-gray-700 leading-relaxed">{reason}</div>
                </div>

                {/* Quick actions */}
                <div className="flex items-center gap-2">
                  <span className="text-[10.5px] font-semibold uppercase tracking-widest text-gray-500">빠른 수정</span>
                  {prev > 0 && (
                    <button onClick={() => update.mutate({ id: e.id, patch: { total_amount: prev, approved: true } })}
                      className="px-3 py-1.5 rounded-full border border-gray-200 text-xs font-medium hover:bg-gray-50 transition-colors" disabled={update.isPending}>
                      전월값 사용
                    </button>
                  )}
                  <button className="px-3 py-1.5 rounded-full border border-gray-200 text-xs font-medium hover:bg-gray-50 transition-colors">직접 입력...</button>
                </div>
              </div>
            </BezelCard>
          );
        })}
      </div>
    </div>
  );
}

/* ═══ Ring Progress ═══ */

function RingProgress({ current, total }: { current: number; total: number }) {
  const pct = Math.round((current / total) * 100);
  return (
    <div
      className="w-9 h-9 rounded-full grid place-items-center text-[10.5px] font-bold relative"
      style={{
        background: `conic-gradient(#101112 ${pct}%, #F4F4F6 0)`,
      }}
    >
      <span className="absolute inset-1 bg-white rounded-full" />
      <span className="relative z-10">{current}/{total}</span>
    </div>
  );
}

/* ═══ Attachment Components ═══ */

function AttachmentThumb({ filingId, sessionId, att, onClick, onDelete }: {
  filingId: string; sessionId: string; att: SessionAttachment; onClick: () => void; onDelete?: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const showInline = att.kind === "image";

  useEffect(() => {
    if (!showInline) return;
    let cancelled = false;
    let url: string | null = null;
    apiBlob(`/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`)
      .then((blob) => { if (cancelled) return; url = URL.createObjectURL(blob); setBlobUrl(url); })
      .catch(() => !cancelled && setLoadFailed(true));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [filingId, sessionId, att.storage_key, showInline]);

  return (
    <div className="group relative rounded-lg border border-gray-200 overflow-hidden hover:border-blue-400 transition-colors">
      <button type="button" onClick={onClick} className="w-full flex flex-col items-stretch text-left">
        <div className="aspect-[4/3] bg-gray-50 flex items-center justify-center text-xs text-gray-400">
          {showInline && blobUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={blobUrl} alt={att.filename} className="w-full h-full object-cover" />
          ) : showInline && !blobUrl && !loadFailed ? (
            <span className="text-gray-300 text-[10px]">...</span>
          ) : loadFailed ? (
            <div className="flex flex-col items-center gap-1 text-gray-400">
              <span className="text-lg">🚫</span>
              <span className="text-[9px]">파일 유실</span>
            </div>
          ) : (
            <KindIcon kind={att.kind} />
          )}
        </div>
        <div className="px-1.5 py-1 text-[10px] truncate text-gray-700">{att.filename}</div>
      </button>
      {onDelete && (
        <button type="button" onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
          title="삭제">
          ✕
        </button>
      )}
    </div>
  );
}

function KindIcon({ kind }: { kind: string }) {
  const label = { pdf: "PDF", excel: "엑셀", csv: "CSV", audio: "음성", image: "이미지" }[kind] ?? kind;
  return <div className="flex flex-col items-center gap-1"><div className="text-2xl">📎</div><div className="text-xs font-medium">{label}</div></div>;
}

function DeleteAttachmentModal({ filename, onClose, onConfirm }: {
  filename: string; onClose: () => void; onConfirm: (deletedBy: string) => void;
}) {
  const [name, setName] = useState("");
  return (
    <Modal open={true} onClose={onClose} title="첨부파일 삭제"
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button variant="danger" disabled={!name.trim()} onClick={() => onConfirm(name.trim())}>삭제</Button>
      </>}>
      <div className="space-y-3 text-[13px]">
        <p className="text-gray-700"><b>{filename}</b> 파일을 삭제합니다.</p>
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">담당자 이름 <span className="text-red-600">*</span></label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" autoFocus
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] outline-none focus:border-blue-500" />
        </div>
      </div>
    </Modal>
  );
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
      footer={blobUrl ? <a href={blobUrl} download={att.filename} className="text-sm text-blue-600 hover:underline">다운로드</a> : null}>
      <div className="max-h-[70vh] overflow-auto flex items-center justify-center bg-gray-50 rounded">
        {error ? <p className="text-red-500 p-4">{error}</p>
          : !blobUrl ? <p className="p-8 text-gray-400">로딩 중...</p>
          : att.kind === "image" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={blobUrl} alt={att.filename} className="max-w-full" />
          ) : att.kind === "pdf" ? (
            <iframe src={blobUrl} className="w-full h-[70vh]" title={att.filename} />
          ) : (
            <p className="p-4 text-sm text-gray-600">미리보기 미지원. 다운로드 후 확인하세요.</p>
          )}
      </div>
    </Modal>
  );
}

/* ═══ Utilities ═══ */

function formatKrw(n: number | null | undefined): string {
  if (!n) return "—";
  return "₩ " + n.toLocaleString("ko-KR");
}

function channelLabel(ch: string | null): string {
  if (!ch) return "—";
  return { kakao: "카톡", email: "이메일", sms: "문자", voice: "전화", manual: "직접입력", public_url: "URL폼" }[ch] ?? ch;
}

const FIELD_LABELS: Record<string, string> = {
  national_pension: "국민연금",
  health_insurance: "건강보험",
  employment_insurance: "고용보험",
  longterm_care: "장기요양",
  income_tax: "소득세",
  local_tax: "지방소득세",
  meal_amount: "식대",
  car_amount: "자가운전",
  childcare_amount: "육아수당",
  bonus_amount: "상여",
};

function incomeLabel(type: string): string {
  return { WAGE: "일반근로", BUSINESS: "사업소득", OTHER: "기타소득", DAILY: "일용근로", RETIREMENT: "퇴직소득" }[type] ?? type;
}

function computeDiff(e: PayrollEntry): string | null {
  if (!e.prev_amount || e.prev_amount === 0) return null;
  if (e.total_amount === e.prev_amount) return "동일";
  const pct = Math.round(((e.total_amount - e.prev_amount) / e.prev_amount) * 100);
  return pct > 0 ? `+${pct}%` : `${pct}%`;
}

void getToken;
