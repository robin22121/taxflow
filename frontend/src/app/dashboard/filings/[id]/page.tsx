"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import {
  useClients,
  useDeleteEntry,
  useFilingDashboard,
  useFilingEntries,
  useInsuranceSummary,
  useRequestCollection,
  useSendInvite,
  useSessionAttachments,
  useSessionTimeline,
  useSubmitMessage,
  useUpdateEntry,
} from "@/lib/queries";
import { api, apiBlob, getToken } from "@/lib/api";
import { Badge, BezelCard, Button, Eyebrow, Modal } from "@/components/ui";
import type { CollectionSession, InsuranceTarget, PayrollEntry, SessionAttachment, SessionTimelineEvent, SourceEvent } from "@/lib/types";

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

  async function downloadInsurance(
    kind: "acquisition" | "loss" | "change" | "combined",
    label: string,
  ) {
    try {
      const blob = await apiBlob(`/api/v1/filings/${id}/insurance-${kind}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `4대보험_${label}_${filing.period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function downloadPayslips() {
    try {
      const blob = await apiBlob(`/api/v1/filings/${id}/payslips`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `급여명세서_${filing.period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  // 통합 다운로드: 무조건 전체 거래처 신고자료. 미수신/미확인/의심 시 경고.
  // 원천세 = 일괄신고 단일 파일, 4대보험 = 단일 파일(3시트 분리).
  async function downloadUnified() {
    const unreceived = sessions.filter(
      (s) => s.status === "PENDING" || s.status === "SENT",
    );
    const anomalySessions = sessions.filter((s) => s.has_anomalies);
    const suspectEntries = allEntries.filter(
      (e) =>
        e.match_status === "UNCONFIRMED" ||
        e.match_status === "AMBIGUOUS" ||
        (e.anomaly_notes &&
          Object.keys(e.anomaly_notes).length > 0 &&
          !e.approved),
    );
    const probs: string[] = [];
    if (unreceived.length)
      probs.push(
        `미수신 거래처 ${unreceived.length}곳: ${unreceived.map((s) => s.client_name).join(", ")}`,
      );
    if (anomalySessions.length)
      probs.push(`이상치/확인필요 거래처 ${anomalySessions.length}곳`);
    if (suspectEntries.length)
      probs.push(`미확인·의심 항목 ${suspectEntries.length}건`);
    if (probs.length > 0) {
      const ok = window.confirm(
        `⚠️ 미해결 사항이 있습니다:\n\n- ${probs.join("\n- ")}\n\n` +
          "그래도 전체 거래처의 신고자료(원천세 + 4대보험)를 다운로드하시겠습니까?",
      );
      if (!ok) return;
    }
    await downloadExcel(); // 원천세 일괄신고 — 단일 파일
    await downloadInsurance("combined", "통합"); // 4대보험 — 단일 파일(3시트 분리)
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
            <Button variant="secondary" onClick={downloadUnified} className="!text-[12px] !px-2.5 !py-1">통합 다운로드 (원천세+4대보험)</Button>
            <Button variant="ghost" onClick={downloadPayslips} className="!text-[12px] !px-2.5 !py-1">급여명세서</Button>
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
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">고객 소통 내역</div>
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
  const { data: timeline } = useSessionTimeline(filingId, session.id);
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
  const [expandedTimelineIds, setExpandedTimelineIds] = useState<Set<string>>(new Set());
  const toggleTimelineExpanded = useCallback((id: string) => {
    setExpandedTimelineIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

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
      <div className="flex items-center justify-between px-3 pt-2.5 pb-2 shrink-0">
        <div>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">고객 소통 내역</span>
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
        {timeline && timeline.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 px-0.5">소통 타임라인</div>
            {timeline.map((t: SessionTimelineEvent) => {
              const isExpanded = expandedTimelineIds.has(t.id);
              const hasBody = !!(t.sender_name || t.detail);
              return (
                <div
                  key={t.id}
                  onClick={() => hasBody && toggleTimelineExpanded(t.id)}
                  className={`flex items-start gap-2 px-2 py-1.5 rounded-md bg-gray-50 border border-gray-100 transition-colors ${
                    hasBody ? "cursor-pointer hover:bg-gray-100" : ""
                  }`}
                >
                  <span className={`mt-px shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
                    t.direction === "out" ? "bg-blue-50 text-blue-600"
                      : t.direction === "in" ? "bg-green-50 text-green-600"
                      : "bg-gray-100 text-gray-500"
                  }`}>
                    {t.direction === "out" ? "프로덕트→고객" : t.direction === "in" ? "고객사→서버" : "시스템"}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[11.5px] text-gray-700">
                      <span className="tabular-nums text-gray-400">
                        {t.at ? new Date(t.at).toLocaleDateString("ko-KR", { month: "long", day: "numeric" }) : ""}
                      </span>
                      <span className="font-medium">{t.label}</span>
                      {t.channel && <span className="text-gray-400">· {t.channel}</span>}
                    </div>
                    {hasBody && (
                      <div className={`text-[11px] text-gray-500 mt-0.5 ${
                        isExpanded ? "whitespace-pre-wrap break-words" : "truncate"
                      }`}>
                        {t.sender_name ? `${t.sender_name} · ` : ""}{t.detail}
                      </div>
                    )}
                  </div>
                  {hasBody && (
                    <span className={`mt-0.5 shrink-0 text-[9px] text-gray-300 transition-transform ${isExpanded ? "rotate-90" : ""}`}>▶</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
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
        <AttachmentZoomModal key={zoomKey} filingId={filingId} sessionId={session.id} att={attachments.find((a) => a.storage_key === zoomKey)!} onClose={() => setZoomKey(null)} />
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
  const [drafts, setDrafts] = useState<Record<string, Partial<PayrollEntry>>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<"wht" | "insurance">("wht");
  const clientDetail = clients?.find((c) => c.id === session.client_id);

  // Initialize drafts for pending entries
  const pendingEntries = entries.filter((e) => !e.approved);
  const approvedEntries = entries.filter((e) => e.approved);

  const getDraft = useCallback((e: PayrollEntry): Partial<PayrollEntry> => {
    return drafts[e.id] ?? {
      raw_name: e.raw_name, income_type: e.income_type, total_amount: e.total_amount,
      bonus_amount: e.bonus_amount ?? 0, meal_amount: e.meal_amount, car_amount: e.car_amount, childcare_amount: e.childcare_amount,
      national_pension: e.national_pension, health_insurance: e.health_insurance, employment_insurance: e.employment_insurance, longterm_care: e.longterm_care,
      income_tax: e.income_tax, local_tax: e.local_tax,
    };
  }, [drafts]);

  function setDraftFor(id: string, d: Partial<PayrollEntry>) {
    setDrafts((prev) => ({ ...prev, [id]: d }));
  }

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

  const DETAIL_FIELDS: (keyof PayrollEntry)[] = [
    "raw_name", "income_type", "total_amount", "bonus_amount", "meal_amount", "car_amount", "childcare_amount",
    "national_pension", "health_insurance", "employment_insurance", "longterm_care", "income_tax", "local_tax",
  ];

  function approveEntry(e: PayrollEntry) {
    const d = getDraft(e);
    const patch: Partial<PayrollEntry> = { approved: true };
    for (const f of DETAIL_FIELDS) {
      if (d[f] !== undefined && d[f] !== e[f]) (patch as Record<string, unknown>)[f] = d[f];
    }
    update.mutate({ id: e.id, patch }, {
      onSuccess: () => setDrafts((prev) => { const next = { ...prev }; delete next[e.id]; return next; }),
      onError: (err) => alert((err as Error).message),
    });
  }

  function saveApprovedEdit(e: PayrollEntry) {
    const d = getDraft(e);
    const patch: Partial<PayrollEntry> = {};
    for (const f of DETAIL_FIELDS) {
      if (d[f] !== undefined && d[f] !== e[f]) (patch as Record<string, unknown>)[f] = d[f];
    }
    if (Object.keys(patch).length === 0) { setExpandedId(null); return; }
    update.mutate({ id: e.id, patch }, {
      onSuccess: () => { setExpandedId(null); setDrafts((prev) => { const next = { ...prev }; delete next[e.id]; return next; }); },
      onError: (err) => alert((err as Error).message),
    });
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
                  {update.isPending ? "승인중..." : selected.size === 1 ? "승인" : `일괄 승인 (${selected.size})`}
                </Button>
                <Button variant="danger" className="text-xs px-3 py-1.5" onClick={bulkDelete} disabled={remove.isPending}>
                  {remove.isPending ? "삭제중..." : selected.size === 1 ? "삭제" : `일괄 삭제 (${selected.size})`}
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
        <div className="flex gap-1 mt-2.5">
          <button onClick={() => setTab("wht")}
            className={`px-3 py-1.5 text-[12px] font-semibold rounded-md transition-colors ${tab === "wht" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
            원천세 관리
          </button>
          <button onClick={() => setTab("insurance")}
            className={`px-3 py-1.5 text-[12px] font-semibold rounded-md transition-colors ${tab === "insurance" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
            4대보험 관리
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {tab === "insurance" ? (
          <InsuranceTab filingId={filingId} session={session} />
        ) : entries.length > 0 ? (
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
              {/* ── 검토 대상 섹션 ── */}
              {pendingEntries.length > 0 && (
                <tr><td colSpan={6} className="px-4 py-1.5 bg-amber-50/70 text-[10.5px] font-semibold text-amber-700 uppercase tracking-wider border-b border-amber-100">
                  검토 대상 ({pendingEntries.length}명)
                </td></tr>
              )}
              {pendingEntries.map((e) => <EntryRow key={e.id} e={e} mode="pending" draft={getDraft(e)} setDraft={(d) => setDraftFor(e.id, d)} selected={selected} toggleSelect={toggleSelect} highlightEventId={highlightEventId} onHighlight={onHighlight} onApprove={() => approveEntry(e)} onDelete={() => { if (window.confirm(`${e.raw_name} 삭제?`)) remove.mutate(e.id); }} onSave={() => saveApprovedEdit(e)} onToggleExpand={() => setExpandedId(expandedId === e.id ? null : e.id)} expanded={expandedId === e.id} update={update} remove={remove} />)}
              {/* ── 승인 완료 섹션 ── */}
              {approvedEntries.length > 0 && (
                <tr><td colSpan={6} className="px-4 py-1.5 bg-green-50/70 text-[10.5px] font-semibold text-green-700 uppercase tracking-wider border-b border-green-100">
                  승인 완료 ({approvedEntries.length}명)
                </td></tr>
              )}
              {approvedEntries.map((e) => <EntryRow key={e.id} e={e} mode="approved" draft={getDraft(e)} setDraft={(d) => setDraftFor(e.id, d)} selected={selected} toggleSelect={toggleSelect} highlightEventId={highlightEventId} onHighlight={onHighlight} onApprove={() => {}} onDelete={() => { if (window.confirm(`${e.raw_name} 삭제?`)) remove.mutate(e.id); }} onSave={() => saveApprovedEdit(e)} onToggleExpand={() => setExpandedId(expandedId === e.id ? null : e.id)} expanded={expandedId === e.id} update={update} remove={remove} />)}
            </tbody>
          </table>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">아직 파싱된 항목이 없습니다</div>
        )}
      </div>
    </>
  );
}

/* ═══ 4대보험 관리 탭 ═══ */

function InsuranceTab({ filingId, session }: {
  filingId: string;
  session: CollectionSession;
}) {
  const { data: summary, isLoading } = useInsuranceSummary(filingId, session.client_id);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function dl(
    kind: "combined" | "acquisition" | "loss" | "change",
    label: string,
  ) {
    try {
      const blob = await apiBlob(
        `/api/v1/filings/${filingId}/insurance-${kind}?client_id=${session.client_id}`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `4대보험_${label}_${session.client_name}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  if (isLoading || !summary) {
    return (
      <div className="p-3 text-[12px] text-gray-400 text-center">
        {isLoading ? "4대보험 분류 중..." : "요약 데이터를 불러올 수 없습니다"}
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[12px] text-gray-500">
          {session.client_name} · 이번 달 4대보험 신고 대상
        </div>
        <button
          onClick={() => dl("combined", "통합")}
          className="px-3 py-1.5 text-[12px] font-semibold bg-blue-600 text-white rounded-md hover:bg-blue-700">
          4대보험 통합 다운로드 (3시트)
        </button>
      </div>
      <InsuranceSection title="자격취득" list={summary.acquisitions} kind="acquisition" label="자격취득"
        expanded={expanded} toggle={toggle} onDownload={dl} />
      <InsuranceSection title="자격상실" list={summary.losses} kind="loss" label="자격상실"
        expanded={expanded} toggle={toggle} onDownload={dl} />
      <InsuranceSection title="보수월액 변경" list={summary.changes} kind="change" label="보수월액변경"
        expanded={expanded} toggle={toggle} onDownload={dl} />
      <EdiGuideSection />
    </div>
  );
}

function InsuranceSection({
  title, list, kind, label, expanded, toggle, onDownload,
}: {
  title: string;
  list: InsuranceTarget[];
  kind: "acquisition" | "loss" | "change";
  label: string;
  expanded: Set<string>;
  toggle: (id: string) => void;
  onDownload: (k: "combined" | "acquisition" | "loss" | "change", lbl: string) => void;
}) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-100">
        <span className="text-[12px] font-semibold text-gray-700">
          {title} <span className="text-blue-600">{list.length}</span>명
        </span>
        <button
          onClick={() => onDownload(kind, label)}
          disabled={list.length === 0}
          className="text-[11px] text-blue-600 hover:underline disabled:opacity-40 disabled:no-underline">
          엑셀 다운로드
        </button>
      </div>
      {list.length === 0 ? (
        <div className="px-3 py-3 text-[12px] text-gray-400 text-center">대상 없음</div>
      ) : (
        <ul className="divide-y divide-gray-50">
          {list.map((t) => {
            const isOpen = expanded.has(t.employee_id);
            return (
              <li key={t.employee_id}>
                <button
                  onClick={() => toggle(t.employee_id)}
                  className="w-full flex items-center justify-between px-3 py-2 text-[12px] hover:bg-gray-50 transition-colors">
                  <span className="flex items-center gap-2">
                    <span className={`text-gray-400 transition-transform ${isOpen ? "rotate-90" : ""}`}>▸</span>
                    <span className="font-medium text-gray-800">{t.name}</span>
                    {t.rrn_last4 && (
                      <span className="text-[10.5px] text-gray-400 tabular-nums">***-{t.rrn_last4}</span>
                    )}
                  </span>
                  <span className="tabular-nums text-gray-600">
                    {t.kind === "change" && t.prev_amount != null
                      ? `${formatKrw(t.prev_amount)} → ${formatKrw(t.total_amount)}`
                      : formatKrw(t.total_amount)}
                  </span>
                </button>
                {isOpen && <InsuranceTargetDetail t={t} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function InsuranceTargetDetail({ t }: { t: InsuranceTarget }) {
  return (
    <div className="px-4 py-2.5 bg-blue-50/40 border-t border-blue-100 text-[11.5px] space-y-2">
      {t.kind === "acquisition" && <AcquisitionDetail t={t} />}
      {t.kind === "loss" && <LossDetail t={t} />}
      {t.kind === "change" && <ChangeDetail t={t} />}
      <SocialInsuranceBreakdown t={t} />
    </div>
  );
}

function AcquisitionDetail({ t }: { t: InsuranceTarget }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
      <DetailRow label="자격취득일" value={t.hired_at ?? "—"} />
      <DetailRow label="취득부호" value={`${t.acquisition_code ?? "—"} (기본값, EDI 단계 확정)`} muted />
      <DetailRow label="보수월액 (비과세 제외)" value={formatKrw(t.monthly_wage)} />
      <DetailRow label="당월 총지급액" value={formatKrw(t.total_amount)} />
    </div>
  );
}

function LossDetail({ t }: { t: InsuranceTarget }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
      <DetailRow label="자격상실일" value={t.resigned_at ?? "—"} />
      <DetailRow label="상실부호" value={`${t.loss_code ?? "—"} (사용관계 종료, EDI 단계 확정)`} muted />
      <DetailRow label="당월 보수총액" value={formatKrw(t.total_amount)} />
      <DetailRow label="보수월액 (비과세 제외)" value={formatKrw(t.monthly_wage)} />
    </div>
  );
}

function ChangeDetail({ t }: { t: InsuranceTarget }) {
  const pct = t.change_pct != null ? `${(t.change_pct * 100).toFixed(1)}%` : "—";
  const reasonKo = t.reason_code === "1" ? "보수인상" : t.reason_code === "2" ? "보수인하" : "—";
  return (
    <>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        <DetailRow label="변경 전" value={t.prev_amount != null ? formatKrw(t.prev_amount) : "—"} />
        <DetailRow label="변경 후" value={formatKrw(t.total_amount)} />
        <DetailRow label="변동률" value={pct} />
        <DetailRow label="사유" value={reasonKo} />
      </div>
      <div className="border-t border-blue-100 pt-2 mt-1 space-y-1">
        <div className="text-[10.5px] font-semibold text-gray-500 uppercase tracking-wider">보험별 신청</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <InsuranceFlag label="국민연금"
            ok={!!t.nps_eligible}
            note={t.nps_eligible ? "20%↑ 적격" : "20% 미만 — 변경 불가"}
          />
          <InsuranceFlag label="건강·고용·산재" ok note="변경 시마다 신청 가능" />
        </div>
        {t.nps_eligible && (
          <>
            {t.nps_within_limit === false && (
              <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                ⚠ NPS 기준소득월액 한도(40만원~637만원, 2025.7~2026.6) 초과/미만 — 한도 캡 적용 검토 필요
              </div>
            )}
            {t.nps_consent_required && (
              <div className="text-[11px] text-gray-600 bg-white border border-gray-200 rounded px-2 py-1">
                ℹ NPS 변경신청은 <strong>근로자 동의서</strong> 필수 첨부 (별지 양식)
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

function SocialInsuranceBreakdown({ t }: { t: InsuranceTarget }) {
  return (
    <div className="border-t border-blue-100 pt-2 mt-1">
      <div className="text-[10.5px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
        4대보험 사용자부담분 (월)
      </div>
      <div className="grid grid-cols-4 gap-x-2 text-[11px]">
        <SiCell label="국민연금" v={t.national_pension} />
        <SiCell label="건강보험" v={t.health_insurance} />
        <SiCell label="장기요양" v={t.longterm_care} />
        <SiCell label="고용보험" v={t.employment_insurance} />
      </div>
      <div className="text-[10px] text-gray-400 mt-1">
        ※ 산재보험은 업종별 요율로 별도 산정 (본 화면 미표기, 엑셀에선 월평균보수 기재)
      </div>
    </div>
  );
}

function DetailRow({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[10.5px] text-gray-500 min-w-[88px]">{label}</span>
      <span className={`tabular-nums ${muted ? "text-gray-400" : "text-gray-800"}`}>{value}</span>
    </div>
  );
}

function InsuranceFlag({ label, ok, note }: { label: string; ok: boolean; note: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${ok ? "bg-green-500" : "bg-gray-300"}`} />
      <span className="font-medium text-gray-700 min-w-[88px]">{label}</span>
      <span className={ok ? "text-gray-600" : "text-gray-400"}>{note}</span>
    </div>
  );
}

function SiCell({ label, v }: { label: string; v: number }) {
  return (
    <div className="bg-white border border-gray-100 rounded px-2 py-1">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className="tabular-nums text-[11.5px] font-medium text-gray-800">{formatKrw(v)}</div>
    </div>
  );
}

/* ═══ EDI 제출 상태·가이드 (Phase 2~3 자동화 진입 전 화면 안내) ═══ */

function EdiGuideSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-100 hover:bg-gray-100 transition-colors">
        <span className="text-[12px] font-semibold text-gray-700">
          EDI 제출 가이드 <span className="text-[10.5px] font-normal text-gray-400">(국민연금 EDI 업무대행)</span>
        </span>
        <span className={`text-gray-400 text-[10px] transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
      </button>
      {open && (
        <div className="px-3 py-2.5 text-[11.5px] text-gray-600 space-y-2 leading-relaxed">
          <p>
            <strong>운영 모델 — 업무대행기관 지정.</strong> 세무사사무소가 업무대행기관(세무사·노무사·회계사 등)으로
            1인 업무대행기관번호(사업자등록번호10+구분코드9, 11자리) 발급 → 거래처가 별지4호 신청서로 업무대행기관 지정 →
            업무대행기관 공동인증서로 EDI 로그인 후 [사업장 전환]으로 거래처별 신고.
          </p>
          <p>
            <strong>파일 대량신고 경로.</strong> 국민연금 EDI는 [파일신고업로드] = 엑셀 대량신고 + [파일사양서]를
            공식 제공(자격취득/상실 등). 본 화면 [엑셀 다운로드]·[통합 다운로드]가 그 입력 파일에 해당.
            보수월액변경은 웹EDI 일괄등록 16컬럼 머신 포맷.
          </p>
          <p>
            <strong>처리결과 회수.</strong> EDI 신고 후 신고일·접수번호·서식명·처리상태(정상/오류)·확인여부 흐름 존재 —
            Phase 2~3에서 RPA로 자동 회수 예정.
          </p>
          <div className="border border-amber-200 bg-amber-50/60 rounded px-2 py-1.5 text-[11px] text-amber-800">
            <div className="font-semibold mb-0.5">⚠ 미확보 갭 (정직)</div>
            <ul className="list-disc ml-4 space-y-0.5">
              <li>국민연금 EDI 파일사양서(엑셀 대량신고 컬럼·자릿수) — 포털 별도 다운로드</li>
              <li>취득부호·상실부호 전체 코드표 — 공단 서식/포털 확인 필요 (본 화면은 기본값 노출)</li>
              <li>건강·고용·산재 공단별 고유 항목 — 국민연금 입력 자동표출 외 영역은 각 공단 확인</li>
            </ul>
          </div>
          <p className="text-[10.5px] text-gray-400">
            현재 단계는 신고서 엑셀·요약 화면까지. 자동 제출·결과 회수는 업무대행기관번호 발급 + 파일사양서 확보 + 공동인증서 로컬 처리 후 진입.
          </p>
        </div>
      )}
    </div>
  );
}

/* ═══ Entry Row ═══ */

type EntryRowProps = {
  e: PayrollEntry;
  mode: "pending" | "approved";
  draft: Partial<PayrollEntry>;
  setDraft: (d: Partial<PayrollEntry>) => void;
  selected: Set<string>;
  toggleSelect: (id: string) => void;
  highlightEventId: string | null;
  onHighlight: (id: string | null) => void;
  onApprove: () => void;
  onDelete: () => void;
  onSave: () => void;
  onToggleExpand: () => void;
  expanded: boolean;
  update: ReturnType<typeof useUpdateEntry>;
  remove: ReturnType<typeof useDeleteEntry>;
};

function EntryRow({ e, mode, draft, setDraft, selected, toggleSelect, highlightEventId, onHighlight, onApprove, onDelete, onSave, onToggleExpand, expanded, update, remove }: EntryRowProps) {
  const hasFlag = !!(e.anomaly_notes && Object.keys(e.anomaly_notes).length > 0 && !e.approved);
  const fieldChanges = (e.anomaly_notes?.field_changes ?? null) as Record<string, { prev: number; curr: number }> | null;
  const diff = computeDiff(e);

  return (
    <>
      <tr
        onClick={() => { onToggleExpand(); if (e.collection_event_id) onHighlight(highlightEventId === e.collection_event_id ? null : e.collection_event_id); }}
        className={`border-b border-gray-50 transition-colors cursor-pointer ${
          highlightEventId && e.collection_event_id === highlightEventId
            ? "bg-blue-50 ring-1 ring-inset ring-blue-300"
            : expanded ? "bg-blue-50/30"
            : hasFlag ? "bg-red-50/60" : mode === "approved" ? "hover:bg-green-50/40" : "hover:bg-gray-50"
        }`}>
        <td className="py-2.5 pl-4">
          <input type="checkbox" checked={selected.has(e.id)} onChange={() => toggleSelect(e.id)} onClick={(ev) => ev.stopPropagation()} className="h-3.5 w-3.5 accent-blue-600" />
        </td>
        <td className="py-2.5 pl-2">
          <div className="flex items-center gap-1.5">
            <span className={`text-[10px] text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}>▶</span>
            <span className="font-semibold text-[13px] text-gray-900 tracking-tight">{e.raw_name}</span>
            {e.approved && <span className="text-[10px] text-green-600">✓</span>}
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5 pl-[18px]">{e.a_code ?? "A01"} · {incomeLabel(e.income_type)}</div>
        </td>
        <td className="py-2.5 pr-3.5 text-right text-gray-500 tabular-nums">{e.prev_amount ? formatKrw(e.prev_amount) : "—"}</td>
        <td className="py-2.5 pr-3.5 text-right tabular-nums font-semibold">
          <span className={hasFlag ? "text-red-600 font-bold" : "text-gray-900"}>{formatKrw(e.total_amount)}</span>
          {fieldChanges && !expanded && (
            <div className="flex flex-wrap gap-0.5 mt-0.5 justify-end">
              {Object.keys(fieldChanges).map((k) => (
                <span key={k} className="text-[9px] px-1 py-px rounded bg-red-100 text-red-600 font-medium" title={`전월 ${formatKrw(fieldChanges[k].prev)} → ${formatKrw(fieldChanges[k].curr)}`}>
                  {FIELD_LABELS[k] ?? k}
                </span>
              ))}
            </div>
          )}
        </td>
        <td className="py-2.5 pr-3.5 text-right">
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
        <td className="py-2.5 pr-3 text-right" onClick={(ev) => ev.stopPropagation()}>
          <div className="flex gap-1 justify-end">
            {mode === "pending" ? (<>
              <button onClick={onApprove} className="px-2.5 py-1 text-[11px] bg-blue-600 text-white rounded-full font-medium hover:bg-blue-700" disabled={update.isPending}>승인</button>
              <button onClick={onDelete} className="px-2 py-1 text-[11px] text-red-600 border border-red-200 rounded-full hover:bg-red-50">삭제</button>
            </>) : (<>
              <button onClick={onToggleExpand} className="px-2 py-1 text-[11px] text-blue-600 border border-blue-200 rounded-full hover:bg-blue-50">{expanded ? "접기" : "수정"}</button>
              <button onClick={() => update.mutate({ id: e.id, patch: { approved: false } })} className="px-2 py-1 text-[11px] text-amber-600 border border-amber-200 rounded-full hover:bg-amber-50">승인취소</button>
            </>)}
          </div>
        </td>
      </tr>
      {/* ── 상세 필드 — v3 스프레드시트 (5컬럼) ── */}
      {expanded && (
        <tr className="bg-stone-50/50">
          <td colSpan={6} className="px-0 py-0" onClick={(ev) => ev.stopPropagation()}>
            <V3Spreadsheet
              draft={draft}
              setDraft={setDraft}
              fieldChanges={fieldChanges}
              mode={mode}
              onSave={onSave}
              onCancel={onToggleExpand}
              saving={update.isPending}
            />
          </td>
        </tr>
      )}
    </>
  );
}

/* ═══ v3 스프레드시트 (지급명세서 세부) ═══ */

const V3_GRID = "grid grid-cols-[1.4fr_1fr_1.4fr_1fr_1fr]";

function V3Spreadsheet({
  draft,
  setDraft,
  fieldChanges,
  mode,
  onSave,
  onCancel,
  saving,
}: {
  draft: Partial<PayrollEntry>;
  setDraft: (d: Partial<PayrollEntry>) => void;
  fieldChanges: Record<string, { prev: number; curr: number }> | null;
  mode: "pending" | "approved";
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  // v3 의도: 펼친 상태 = 편집 모드. pending/approved 모두 인라인 편집 가능.
  const editing = true;
  const v = (k: keyof PayrollEntry): number => Number(draft[k] ?? 0) || 0;
  const set = (k: keyof PayrollEntry, val: number) => setDraft({ ...draft, [k]: val });

  const basic = v("total_amount");
  const bonus = v("bonus_amount");
  const meal = v("meal_amount");
  const car = v("car_amount");
  const childcare = v("childcare_amount");
  const np = v("national_pension");
  const hi = v("health_insurance");
  const ei = v("employment_insurance");
  const ltc = v("longterm_care");
  const it = v("income_tax");
  const lt = v("local_tax");

  const paySum = bonus + meal + car + childcare;
  const insSum = np + hi + ei + ltc;
  const taxSum = it + lt;
  const gross = basic + paySum;
  const deduct = insSum + taxSum;
  const net = gross - deduct;

  function v3Num(field: keyof PayrollEntry, value: number, anomaly?: boolean) {
    if (editing) {
      return (
        <input
          type="text"
          inputMode="numeric"
          value={value.toLocaleString("ko-KR")}
          onChange={(e) => {
            const digits = e.target.value.replace(/[^\d-]/g, "");
            set(field, Number(digits) || 0);
          }}
          className={`w-full font-mono tabular-nums text-right text-[13.5px] font-semibold py-0.5 px-1 rounded outline-none ${
            anomaly
              ? "bg-red-50 border border-red-300 text-red-700"
              : "bg-amber-50 border border-amber-200 focus:bg-white focus:border-amber-400"
          }`}
        />
      );
    }
    return (
      <span
        className={`font-mono tabular-nums text-[13.5px] font-semibold ${
          anomaly ? "text-red-700" : value === 0 ? "text-gray-400 font-normal" : "text-gray-900"
        }`}
      >
        {value.toLocaleString("ko-KR")}
      </span>
    );
  }

  return (
    <div className="bg-white border-t border-gray-200">
      {editing && (
        <div className="flex items-center gap-2 px-5 py-2 text-[12px] text-amber-800 bg-amber-50 border-b border-amber-100">
          <span className="font-semibold">편집 모드</span>
          <span>— 노란색 칸을 클릭해 값을 수정한 뒤 저장 버튼을 누르세요.</span>
        </div>
      )}

      {/* 헤더 바 */}
      <div className={`${V3_GRID} bg-gray-50 border-b border-gray-200 text-[10.5px] font-bold uppercase tracking-wider text-gray-500`}>
        <div className="px-3.5 py-2 border-r border-gray-200 text-blue-700 bg-blue-50/40">총지급</div>
        <div className="px-3.5 py-2 border-r border-gray-200 text-blue-700 bg-blue-50/40">비과세 수당</div>
        <div className="px-3.5 py-2 border-r border-gray-200 text-red-700 bg-red-50/40">4대보험</div>
        <div className="px-3.5 py-2 border-r border-gray-200 text-red-700 bg-red-50/40">세금</div>
        <div className="px-3.5 py-2">메모</div>
      </div>

      {/* 본문 라인 */}
      <div className={`${V3_GRID} border-b border-gray-200`}>
        {/* 1: 총지급액 */}
        <div className="px-3.5 py-2.5 border-r border-gray-200 flex flex-col gap-1 min-h-[56px]">
          <span className="text-[11px] text-gray-500">총지급액 · 근로</span>
          <span className="font-mono tabular-nums text-[13.5px] font-semibold text-gray-900">
            ₩ {editing ? v3Num("total_amount", basic) : basic.toLocaleString("ko-KR")}
          </span>
        </div>

        {/* 2: 지급항목 multi */}
        <V3MultiCell
          title="지급항목"
          sum={`${paySum >= 0 ? "+ " : "− "}${Math.abs(paySum).toLocaleString("ko-KR")}`}
          rows={[
            ["상여", v3Num("bonus_amount", bonus, !!fieldChanges?.bonus_amount)],
            ["식대", v3Num("meal_amount", meal, !!fieldChanges?.meal_amount)],
            ["자가운전", v3Num("car_amount", car, !!fieldChanges?.car_amount)],
            ["육아수당", v3Num("childcare_amount", childcare, !!fieldChanges?.childcare_amount)],
          ]}
        />

        {/* 3: 4대보험 */}
        <V3MultiCell
          title="공제"
          sum={insSum.toLocaleString("ko-KR")}
          rows={[
            ["국민연금", v3Num("national_pension", np, !!fieldChanges?.national_pension)],
            ["건강보험", v3Num("health_insurance", hi, !!fieldChanges?.health_insurance)],
            ["고용보험", v3Num("employment_insurance", ei, !!fieldChanges?.employment_insurance)],
            ["장기요양", v3Num("longterm_care", ltc, !!fieldChanges?.longterm_care)],
          ]}
        />

        {/* 4: 세금 */}
        <V3MultiCell
          title="세금"
          sum={taxSum.toLocaleString("ko-KR")}
          rows={[
            ["소득세", v3Num("income_tax", it, !!fieldChanges?.income_tax)],
            ["지방소득세", v3Num("local_tax", lt, !!fieldChanges?.local_tax)],
          ]}
        />

        {/* 5: 메모 */}
        <div className="px-3.5 py-2.5 flex flex-col gap-1 min-h-[56px]">
          <span className="text-[11px] text-gray-500">메모</span>
          {editing ? (
            <textarea
              value={(draft.anomaly_notes?.memo as string) ?? ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  anomaly_notes: { ...(draft.anomaly_notes ?? {}), memo: e.target.value },
                })
              }
              className="text-[12px] text-gray-700 bg-amber-50 border border-amber-200 focus:bg-white focus:border-amber-400 rounded px-1.5 py-1 outline-none resize-none"
              rows={2}
            />
          ) : (
            <span className="text-[12px] text-gray-500">
              {(draft.anomaly_notes?.memo as string) || "—"}
            </span>
          )}
        </div>
      </div>

      {/* 푸터: 지급 / 공제 / 실지급액 */}
      <div className="flex items-center justify-between px-5 py-3 bg-gradient-to-b from-gray-50 to-stone-100 border-t border-gray-300">
        <div className="flex gap-7 text-[12px]">
          <div className="flex items-baseline gap-2">
            <span className="text-[10.5px] uppercase tracking-wider font-semibold text-gray-500">지급</span>
            <span className="font-mono tabular-nums font-semibold text-[13.5px] text-gray-900">
              ₩ {gross.toLocaleString("ko-KR")}
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[10.5px] uppercase tracking-wider font-semibold text-gray-500">공제</span>
            <span className="font-mono tabular-nums font-semibold text-[13.5px] text-red-600">
              − ₩ {deduct.toLocaleString("ko-KR")}
            </span>
          </div>
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="text-[11px] uppercase tracking-widest font-bold text-gray-500">실지급액</span>
          <span className="font-mono tabular-nums font-bold text-[19px] text-blue-700">
            ₩ {net.toLocaleString("ko-KR")}
          </span>
        </div>
      </div>

      {/* 하단 보조 액션 (v3 ghost actions) + approved일 때 저장/취소 */}
      <div className="flex items-center gap-1.5 px-5 py-2 bg-white border-t border-gray-200">
        {mode === "approved" && (
          <>
            <button
              onClick={onSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
            <button
              onClick={onCancel}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-medium border border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              취소
            </button>
            <span className="w-px h-4 bg-gray-200 mx-1" />
          </>
        )}
        <button className="text-[12px] text-gray-500 hover:text-gray-700 hover:bg-gray-50 px-2 py-1 rounded">
          명세서 PDF
        </button>
        <button className="text-[12px] text-gray-500 hover:text-gray-700 hover:bg-gray-50 px-2 py-1 rounded">
          변경 이력
        </button>
        <span className="flex-1" />
        {mode === "approved" && (
          <button
            onClick={onCancel}
            className="text-[12px] text-gray-500 hover:text-gray-700 hover:bg-gray-50 px-2 py-1 rounded"
          >
            접기
          </button>
        )}
      </div>
    </div>
  );
}

function V3MultiCell({
  title,
  sum,
  rows,
}: {
  title: string;
  sum: string;
  rows: [string, React.ReactNode][];
}) {
  return (
    <div className="px-3.5 py-2 border-r border-gray-200 flex flex-col gap-0 min-h-[56px]">
      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">
        {title} <span className="font-mono font-semibold text-gray-700 ml-1.5 normal-case">{sum}</span>
      </div>
      {rows.map(([k, node]) => (
        <div key={k} className="flex justify-between items-baseline gap-2 py-0.5 text-[12px]">
          <span className="text-gray-500 shrink-0">{k}</span>
          <span className="text-right min-w-0 flex-1">{node}</span>
        </div>
      ))}
    </div>
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

type SheetData = { name: string; rows: string[][]; truncated: boolean };
const SHEET_ROW_LIMIT = 500;

function SpreadsheetPreview({ sheets, active, onSelect }: {
  sheets: SheetData[]; active: number; onSelect: (i: number) => void;
}) {
  const sheet = sheets[active] ?? sheets[0];
  if (!sheet) return <p className="p-4 text-sm text-gray-600">빈 파일입니다.</p>;
  return (
    <div className="bg-white min-w-full">
      {sheets.length > 1 && (
        <div className="flex gap-1 px-2 pt-2 border-b border-gray-200 bg-gray-50 sticky top-0 z-10">
          {sheets.map((s, i) => (
            <button key={s.name + i} type="button" onClick={() => onSelect(i)}
              className={`px-3 py-1.5 text-[12px] rounded-t whitespace-nowrap ${i === active ? "bg-white border border-b-white border-gray-200 font-medium text-gray-900" : "text-gray-500 hover:text-gray-800"}`}>
              {s.name || `시트 ${i + 1}`}
            </button>
          ))}
        </div>
      )}
      {sheet.rows.length === 0 ? (
        <p className="p-4 text-sm text-gray-500">빈 시트입니다.</p>
      ) : (
        <table className="border-collapse text-[12px]">
          <tbody>
            {sheet.rows.map((row, ri) => (
              <tr key={ri} className={ri === 0 ? "bg-gray-100 font-medium" : ri % 2 ? "bg-gray-50/60" : ""}>
                {row.map((cell, ci) => (
                  <td key={ci} className="border border-gray-200 px-2 py-1 align-top">
                    <div className="max-w-[360px] truncate" title={cell}>{cell}</div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {sheet.truncated && (
        <p className="p-3 text-[11px] text-amber-700 bg-amber-50 border-t border-amber-200">
          행이 많아 처음 {SHEET_ROW_LIMIT.toLocaleString("ko-KR")}행만 표시했습니다. 전체는 다운로드해 확인하세요.
        </p>
      )}
    </div>
  );
}

function AttachmentZoomModal({ filingId, sessionId, att, onClose }: {
  filingId: string; sessionId: string; att: SessionAttachment; onClose: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheets, setSheets] = useState<SheetData[] | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);
  const [textContent, setTextContent] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    // 첨부가 바뀌면 호출부에서 key 로 마운트 단위 리셋됨 → effect 본문에서 추가 setState 리셋 불필요
    apiBlob(`/api/v1/filings/${filingId}/sessions/${sessionId}/attachments/raw?key=${encodeURIComponent(att.storage_key)}`)
      .then(async (blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
        if (att.kind === "excel" || att.kind === "csv") {
          const buf = await blob.arrayBuffer();
          const mod = await import("xlsx");
          const XLSX = (mod as typeof import("xlsx") & { default?: typeof import("xlsx") }).default ?? mod;
          let wb;
          if (att.kind === "csv") {
            // 한글 CSV는 EUC-KR(CP949)인 경우가 많아 UTF-8 실패 시 폴백
            let text = new TextDecoder("utf-8").decode(buf);
            if (text.includes("�")) {
              try { text = new TextDecoder("euc-kr").decode(buf); } catch { /* keep utf-8 */ }
            }
            wb = XLSX.read(text, { type: "string" });
          } else {
            wb = XLSX.read(buf, { type: "array" });
          }
          const parsed: SheetData[] = wb.SheetNames.map((name) => {
            const all = XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets[name], {
              header: 1, blankrows: false, defval: "", raw: false,
            });
            return {
              name,
              rows: all.slice(0, SHEET_ROW_LIMIT).map((r) => (r ?? []).map((c) => String(c ?? ""))),
              truncated: all.length > SHEET_ROW_LIMIT,
            };
          });
          if (!cancelled) setSheets(parsed);
        } else if (att.kind === "text") {
          const t = await blob.text();
          if (!cancelled) setTextContent(t);
        }
      })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [filingId, sessionId, att.storage_key, att.kind]);

  const isSheet = att.kind === "excel" || att.kind === "csv";

  return (
    <Modal open={true} onClose={onClose} title={att.filename}
      footer={blobUrl ? <a href={blobUrl} download={att.filename} className="text-sm text-blue-600 hover:underline">다운로드</a> : null}>
      <div className="max-h-[70vh] overflow-auto bg-gray-50 rounded">
        {error ? <p className="text-red-500 p-4">{error}</p>
          : !blobUrl ? <p className="p-8 text-center text-gray-400">로딩 중...</p>
          : att.kind === "image" ? (
            <div className="flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={blobUrl} alt={att.filename} className="max-w-full" />
            </div>
          ) : att.kind === "pdf" ? (
            <iframe src={blobUrl} className="w-full h-[70vh]" title={att.filename} />
          ) : isSheet ? (
            sheets
              ? <SpreadsheetPreview sheets={sheets} active={activeSheet} onSelect={setActiveSheet} />
              : <p className="p-8 text-center text-gray-400">표 변환 중...</p>
          ) : att.kind === "audio" ? (
            <div className="p-6">
              <audio controls src={blobUrl} className="w-full">오디오 재생을 지원하지 않는 브라우저입니다.</audio>
            </div>
          ) : att.kind === "text" ? (
            textContent != null
              ? <pre className="p-4 text-[12px] leading-relaxed whitespace-pre-wrap break-words text-gray-800">{textContent}</pre>
              : <p className="p-8 text-center text-gray-400">로딩 중...</p>
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
