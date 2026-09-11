"use client";

import { use, useEffect, useState } from "react";

import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui";

type SessionInfo = {
  client_name: string;
  period: string;
  accepting: boolean;
  has_pin: boolean;
};
type PayrollRow = { name: string; total_amount: number; prev_amount: number | null };
type RosterEntry = { id: string; name: string };
type ArchiveRow = {
  period: string;
  estimated_tax: number;
  settled_tax: number | null;
  due_date: string | null;
  virtual_account: string | null;
  epayment_number: string | null;
  has_receipt: boolean;
  has_payment_slip: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type SubmitResult = {
  matched: number;
  new_hire_suspected: number;
  resignation_suspected: number;
  ambiguous: number;
  needs_followup?: number;
  unconfirmed?: number;
};

export default function PublicCollectPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [mode, setMode] = useState<"idle" | "text" | "processing">("idle");
  // PIN 게이트 — 금액이 걸린 것만 자물쇠 뒤에 둔다 (plan/12-owner-portal.md §4.3.1)
  const [gate, setGate] = useState<"hidden" | "asking" | "open">("hidden");
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [pinBusy, setPinBusy] = useState(false);
  const [payroll, setPayroll] = useState<PayrollRow[] | null>(null);
  // 입·퇴사 등록 — 신고월과 무관하게 항상 열어둔다 (§5.2). 4대보험 자격취득은 입사일 +14일이다.
  const [changeMode, setChangeMode] = useState<"none" | "hire" | "resign">("none");
  const [hireName, setHireName] = useState("");
  const [hireDate, setHireDate] = useState("");
  const [resignId, setResignId] = useState("");
  const [resignDate, setResignDate] = useState("");
  const [roster, setRoster] = useState<RosterEntry[] | null>(null);
  const [changeBusy, setChangeBusy] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeDone, setChangeDone] = useState<string | null>(null);
  // 보관함 — 얼마 내야 하나 / 접수증 있나 (§3.1)
  const [archive, setArchive] = useState<ArchiveRow[]>([]);

  // grant는 sessionStorage에만 둔다 — 탭을 닫으면 사라지고 장기 쿠키를 남기지 않는다 (§4.1)
  const grantKey = `taxflow_portal_grant_${token}`;

  useEffect(() => {
    api<SessionInfo>(`/api/v1/public/r/${token}`)
      .then(setSession)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  useEffect(() => {
    api<ArchiveRow[]>(`/api/v1/public/r/${token}/archive`)
      .then(setArchive)
      .catch(() => setArchive([]));
  }, [token]);

  useEffect(() => {
    if (!session?.has_pin) return;
    const saved = sessionStorage.getItem(grantKey);
    if (!saved) return;
    api<PayrollRow[]>(`/api/v1/public/r/${token}/payroll`, {
      headers: { "X-Portal-Grant": saved },
    })
      .then((rows) => {
        setPayroll(rows);
        setGate("open");
      })
      .catch(() => sessionStorage.removeItem(grantKey));
  }, [session, token, grantKey]);

  async function submit() {
    if (!text.trim()) return;
    setSubmitting(true);
    setMode("processing");
    setError(null);
    try {
      const res = await api<SubmitResult>(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text },
      });
      setResult(res);
      setText("");
      setMode("idle");
    } catch (e) {
      setError((e as Error).message);
      setMode("text");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFile(f: File) {
    setSubmitting(true);
    setMode("processing");
    setError(null);
    try {
      const r = await apiUpload<SubmitResult>(`/api/v1/public/r/${token}/upload`, f);
      setResult(r);
      setMode("idle");
    } catch (err) {
      setError((err as Error).message);
      setMode("idle");
    } finally {
      setSubmitting(false);
    }
  }


  async function unlock() {
    if (pin.length < 4) return;
    setPinBusy(true);
    setPinError(null);
    try {
      const res = await api<{ grant: string }>(`/api/v1/public/r/${token}/unlock`, {
        method: "POST",
        json: { pin },
      });
      sessionStorage.setItem(grantKey, res.grant);
      const rows = await api<PayrollRow[]>(`/api/v1/public/r/${token}/payroll`, {
        headers: { "X-Portal-Grant": res.grant },
      });
      setPayroll(rows);
      setGate("open");
      setPin("");
    } catch (e) {
      setPinError((e as Error).message);
    } finally {
      setPinBusy(false);
    }
  }

  async function openResign() {
    setChangeError(null);
    setChangeMode("resign");
    if (roster) return;
    try {
      setRoster(await api<RosterEntry[]>(`/api/v1/public/r/${token}/employees`));
    } catch (e) {
      setChangeError((e as Error).message);
    }
  }

  async function submitChange() {
    setChangeBusy(true);
    setChangeError(null);
    try {
      const body =
        changeMode === "hire"
          ? { change_type: "HIRE", name: hireName.trim(), hired_at: hireDate || null }
          : { change_type: "RESIGN", employee_id: resignId, resigned_at: resignDate || null };
      const res = await api<{ name: string }>(`/api/v1/public/r/${token}/employee-change`, {
        method: "POST",
        json: body,
      });
      setChangeDone(
        changeMode === "hire"
          ? `${res.name} 님 입사를 세무사 사무소에 알렸어요.`
          : `${res.name} 님 퇴사를 세무사 사무소에 알렸어요.`,
      );
      setChangeMode("none");
      setHireName("");
      setHireDate("");
      setResignId("");
      setResignDate("");
      setRoster(null);
    } catch (e) {
      setChangeError((e as Error).message);
    } finally {
      setChangeBusy(false);
    }
  }

  function lockAgain() {
    sessionStorage.removeItem(grantKey);
    setPayroll(null);
    setPin("");
    setPinError(null);
    setGate("hidden");
  }

  if (error && !session) {
    return (
      <div className="min-h-dvh flex items-center justify-center p-4 bg-[#F7F7F9]">
        <div className="max-w-md rounded-2xl bg-white border border-gray-200 p-6 text-center shadow-lg">
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    );
  }
  if (!session) {
    return <div className="min-h-dvh flex items-center justify-center bg-[#F7F7F9]"><p className="text-gray-500">로딩 중...</p></div>;
  }

  return (
    <div className="flex flex-col min-h-dvh bg-[#F7F7F9]" style={{
      backgroundImage: "radial-gradient(circle at 1px 1px, rgba(16,17,18,0.025) 1px, transparent 0)",
      backgroundSize: "16px 16px",
    }}>
      {/* Header */}
      <div className="px-4 py-3 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-600 text-white flex items-center justify-center text-base font-extrabold shrink-0">
            {session.client_name.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-bold tracking-tight text-gray-900 truncate">{session.client_name}</div>
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${session.accepting ? "bg-green-500" : "bg-gray-300"}`} />
              <span className="text-[11.5px] text-gray-500">
                {session.accepting ? `${session.period} 자료 수집중` : "지금은 보낼 자료 없음"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Chat body */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        {/* Date divider */}
        <div className="flex justify-center mb-3">
          <span className="px-3 py-1 rounded-full bg-black/[0.06] text-[11.5px] text-gray-500">
            오늘
          </span>
        </div>

        {/* Safety card */}
        <div className="mx-0 mb-3 p-3 bg-white border border-gray-200 rounded-[14px] shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0 text-sm">🔒</div>
            <div>
              <div className="text-[12px] font-bold text-gray-900">전용 안전 링크</div>
              <div className="text-[11px] text-gray-500 leading-snug">답장 내용은 세무사 사무소만 확인할 수 있어요</div>
            </div>
          </div>
        </div>

        {/* Greeting bubbles (them) */}
        {!session.accepting ? (
          <ChatBubbleThem>
            안녕하세요 <b className="text-blue-600">{session.client_name}</b> 사장님,<br />
            지금은 보내주실 자료가 없어요.<br />
            다음 신고 기간이 되면 알림톡으로 알려드릴게요 🙏
          </ChatBubbleThem>
        ) : (
          <>
            <ChatBubbleThem>
              안녕하세요 <b className="text-blue-600">{session.client_name}</b> 사장님,<br />
              {session.period} 직원 급여 자료 부탁드려요 🙏
            </ChatBubbleThem>
            <ChatBubbleThem>
              아래 <b>편한 방법</b>으로 보내주시면 돼요.
            </ChatBubbleThem>
          </>
        )}

        {/* Quick actions */}
        <div className={`pl-10 space-y-2 mb-3 ${session.accepting ? "" : "hidden"}`}>
          <div className="flex gap-2 max-w-[78%]">
            <label className="flex-1 flex flex-col items-center gap-1 py-2.5 px-2 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 transition-colors">
              <span className="text-lg">📷</span>
              <span className="text-[11px] font-semibold text-gray-700">사진·파일</span>
              <input type="file" className="hidden" accept="audio/*,.mp3,.m4a,.wav,.xlsx,.xls,.csv,.png,.jpg,.jpeg"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
            </label>
            <button onClick={() => setMode("text")} className="flex-1 flex flex-col items-center gap-1 py-2.5 px-2 bg-white border border-gray-200 rounded-xl hover:border-gray-300 transition-colors">
              <span className="text-lg">✏️</span>
              <span className="text-[11px] font-semibold text-gray-700">직접 적기</span>
            </button>
          </div>
        </div>

        {/* User text input (expanded) */}
        {mode === "text" && (
          <div className="flex justify-end mb-2">
            <div className="max-w-[82%] w-full space-y-2">
              <textarea
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={"예) 김연호 100만원, 박민수 신규입사 150만원, 이영수는 이번달 퇴사했어요"}
                className="w-full rounded-2xl bg-white border border-gray-300 px-3.5 py-3 text-[14px] text-gray-900 leading-relaxed outline-none focus:border-blue-500 resize-none"
                autoFocus
              />
              <div className="flex gap-2 justify-end">
                <button onClick={() => { setMode("idle"); setText(""); }}
                  className="px-3.5 py-2 rounded-xl border border-gray-300 text-[13px] text-gray-700 hover:bg-gray-50">
                  취소
                </button>
                <Button onClick={submit} disabled={submitting || !text.trim()}>
                  {submitting ? "전송 중..." : "전송"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Processing indicator */}
        {mode === "processing" && (
          <div className="flex gap-2 items-end mb-2">
            <div className="w-8 h-8 rounded-[10px] bg-amber-50 text-amber-700 flex items-center justify-center shrink-0 text-sm">🤖</div>
            <div className="max-w-[78%]">
              <div className="bg-white border border-gray-200 rounded-[4px_16px_16px_16px] p-3 shadow-sm min-w-[200px]">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                  <span className="text-[12.5px] font-bold text-gray-900">자료 읽고 있어요</span>
                </div>
                <div className="h-[5px] rounded-full bg-gray-200 overflow-hidden mb-1.5">
                  <div className="h-full rounded-full bg-gradient-to-r from-amber-200 to-amber-500 animate-pulse" style={{ width: "72%" }} />
                </div>
                <div className="text-[11px] text-gray-500">분석 중… 약 10초</div>
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex justify-end mb-2">
            <div className="bg-red-50 border border-red-600/20 rounded-2xl px-3.5 py-2.5 text-[13px] text-red-600 max-w-[82%]">
              {error}
            </div>
          </div>
        )}

        {/* Result summary card */}
        {result && (
          <div className="flex gap-2 items-end mb-2">
            <div className="w-8 shrink-0" />
            <div className="max-w-[88%] w-full">
              <div className="bg-white border border-gray-200 rounded-[4px_18px_18px_18px] overflow-hidden shadow-md">
                <div className="px-3.5 py-3 border-b border-gray-200 bg-gradient-to-b from-blue-50 to-white">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-blue-600">✅</span>
                    <span className="text-[13px] font-bold text-blue-600">정리 완료</span>
                  </div>
                  <div className="text-[11.5px] text-gray-500">
                    {session.period} {session.client_name} 급여 · {result.matched + result.new_hire_suspected}명 접수
                  </div>
                </div>

                <div className={`grid py-2.5 px-1 border-b border-gray-200`} style={{
                  gridTemplateColumns: `repeat(${
                    2
                    + (result.resignation_suspected > 0 ? 1 : 0)
                    + (result.ambiguous > 0 ? 1 : 0)
                  }, 1fr)`,
                }}>
                  {([
                    ["기존", result.matched, "gray-900"],
                    ["신규", result.new_hire_suspected, "blue-600"],
                    ...(result.resignation_suspected > 0 ? [["퇴사", result.resignation_suspected, "gray-500"] as const] : []),
                    ...(result.ambiguous > 0 ? [["확인", result.ambiguous, "red-600"] as const] : []),
                  ] as const).map(([label, val, tone], i, arr) => (
                    <div key={i} className="flex flex-col items-center gap-0.5" style={{ borderRight: i < arr.length - 1 ? "1px solid #E3E3E5" : "none" }}>
                      <span className={`text-xl font-extrabold tabular-nums text-${tone}`}>{val}</span>
                      <span className="text-[11px] text-gray-500">{label}</span>
                    </div>
                  ))}
                </div>

                <div className="px-3.5 py-2.5 bg-gray-50 text-[12.5px] text-gray-700">
                  {(result.unconfirmed ?? 0) > 0 ? (
                    <>
                      <span className="text-amber-600 font-semibold">지난달 근무자 중 {result.unconfirmed}명</span>이 이번달 자료에 없어요.
                      <br />계속 근무 중이라면 해당 직원의 급여도 보내주세요.
                      <br />퇴사한 직원이 있다면 알려주세요.
                    </>
                  ) : (
                    <>세무사가 검증 후 추가 확인 사항이 있으면 다시 연락드릴게요.</>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 보관함 — 얼마 내야 하나 / 접수증 (§3.1, §3.4) */}
        {archive.length > 0 && (
          <div className="pl-10 mb-3">
            <div className="max-w-[88%] bg-white border border-gray-200 rounded-[14px] overflow-hidden shadow-sm">
              <div className="px-3.5 py-2.5 border-b border-gray-200 text-[12.5px] font-bold text-gray-900">
                원천세 납부 내역
              </div>
              {archive.map((row) => (
                <div key={row.period} className="px-3.5 py-2.5 border-b border-gray-100 last:border-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-semibold text-gray-900">
                        {row.period.replace("-", "년 ")}월
                      </div>
                      <div className="text-[11px] text-gray-500">
                        {row.settled_tax != null ? "납부" : "예상"}{" "}
                        <span className="tabular-nums">
                          {(row.settled_tax ?? row.estimated_tax).toLocaleString()}원
                        </span>
                        {row.due_date ? ` · ${row.due_date}까지` : ""}
                      </div>
                    </div>
                    <div className="flex gap-1.5 shrink-0">
                      {row.has_receipt && (
                        <a
                          href={`${API_BASE}/api/v1/public/r/${token}/archive/${row.period}/receipt`}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg border border-gray-300 text-[11px] font-medium text-gray-700 hover:bg-gray-50"
                        >
                          접수증
                        </a>
                      )}
                      {row.has_payment_slip && (
                        <a
                          href={`${API_BASE}/api/v1/public/r/${token}/archive/${row.period}/payment-slip`}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg border border-gray-300 text-[11px] font-medium text-gray-700 hover:bg-gray-50"
                        >
                          납부서
                        </a>
                      )}
                    </div>
                  </div>
                  {row.virtual_account && (
                    <div className="mt-1.5 text-[11px] text-gray-700 bg-gray-50 rounded-lg px-2.5 py-1.5">
                      가상계좌 <span className="font-medium">{row.virtual_account}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 입·퇴사 등록 — 자료 수집 기간이 아니어도 항상 열려 있다 (§5.2) */}
        <div className="pl-10 mb-3">
          {changeDone ? (
            <div className="max-w-[78%] bg-white border border-gray-200 rounded-[14px] p-3 shadow-sm">
              <div className="text-[12.5px] font-bold text-gray-900 mb-0.5">✅ 전달했어요</div>
              <div className="text-[11px] text-gray-500 leading-snug">{changeDone}</div>
              <button
                onClick={() => setChangeDone(null)}
                className="mt-2 text-[11.5px] text-blue-600 underline"
              >
                더 알려주기
              </button>
            </div>
          ) : changeMode === "none" ? (
            <div className="flex flex-col gap-2 max-w-[78%]">
              <button
                onClick={() => { setChangeError(null); setChangeMode("hire"); }}
                className="py-2.5 px-3 bg-white border border-gray-200 rounded-xl text-[12.5px] font-semibold text-gray-700 text-left hover:border-gray-300 transition-colors"
              >
                ＋ 새 직원이 들어왔어요
              </button>
              <button
                onClick={openResign}
                className="py-2.5 px-3 bg-white border border-gray-200 rounded-xl text-[12.5px] font-semibold text-gray-700 text-left hover:border-gray-300 transition-colors"
              >
                － 그만둔 직원이 있어요
              </button>
            </div>
          ) : (
            <div className="max-w-[82%] bg-white border border-gray-200 rounded-[14px] p-3 shadow-sm space-y-2">
              <div className="text-[12.5px] font-bold text-gray-900">
                {changeMode === "hire" ? "새 직원 등록" : "퇴사 알리기"}
              </div>

              {changeMode === "hire" ? (
                <>
                  <input
                    value={hireName}
                    onChange={(e) => setHireName(e.target.value)}
                    placeholder="직원 이름"
                    className="w-full rounded-xl bg-white border border-gray-300 px-3 py-2 text-[13.5px] text-gray-900 outline-none focus:border-blue-500"
                    autoFocus
                  />
                  <label className="block">
                    <span className="text-[11px] text-gray-500">입사일</span>
                    <input
                      type="date"
                      value={hireDate}
                      onChange={(e) => setHireDate(e.target.value)}
                      className="w-full rounded-xl bg-white border border-gray-300 px-3 py-2 text-[13.5px] text-gray-900 outline-none focus:border-blue-500"
                    />
                  </label>
                  <div className="text-[11px] text-amber-700 bg-amber-50 rounded-lg px-2.5 py-2 leading-snug">
                    주민등록번호는 여기 적지 마세요. 필요하면 세무사 사무소에서 따로 요청드려요.
                  </div>
                </>
              ) : (
                <>
                  <select
                    value={resignId}
                    onChange={(e) => setResignId(e.target.value)}
                    className="w-full rounded-xl bg-white border border-gray-300 px-3 py-2 text-[13.5px] text-gray-900 outline-none focus:border-blue-500"
                  >
                    <option value="">그만둔 직원을 골라주세요</option>
                    {(roster ?? []).map((r) => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                  <label className="block">
                    <span className="text-[11px] text-gray-500">마지막 근무일</span>
                    <input
                      type="date"
                      value={resignDate}
                      onChange={(e) => setResignDate(e.target.value)}
                      className="w-full rounded-xl bg-white border border-gray-300 px-3 py-2 text-[13.5px] text-gray-900 outline-none focus:border-blue-500"
                    />
                  </label>
                </>
              )}

              {changeError && (
                <div className="text-[11.5px] text-red-600 leading-snug">{changeError}</div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => { setChangeMode("none"); setChangeError(null); }}
                  className="flex-1 py-2 rounded-xl border border-gray-300 text-[12.5px] text-gray-700 hover:bg-gray-50"
                >
                  취소
                </button>
                <Button
                  onClick={submitChange}
                  disabled={
                    changeBusy ||
                    (changeMode === "hire" ? !hireName.trim() : !resignId)
                  }
                >
                  {changeBusy ? "전달 중..." : "알리기"}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* PIN 게이트 — 금액이 걸린 화면만 자물쇠 뒤 (§4.3.1) */}
        {session.has_pin && (
          <div className="pl-10 mb-3">
            {gate !== "open" ? (
              <div className="max-w-[78%] bg-white border border-gray-200 rounded-[14px] p-3 shadow-sm">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm">🔒</span>
                  <span className="text-[12.5px] font-bold text-gray-900">급여 상세 보기</span>
                </div>
                <div className="text-[11px] text-gray-500 leading-snug mb-2.5">
                  직원별 금액은 세무사 사무소에서 받으신 PIN을 넣어야 보여요.
                </div>
                {gate === "hidden" ? (
                  <button
                    onClick={() => setGate("asking")}
                    className="w-full py-2 rounded-xl border border-gray-300 text-[12.5px] font-semibold text-gray-700 hover:bg-gray-50"
                  >
                    PIN 입력하고 보기
                  </button>
                ) : (
                  <div className="space-y-2">
                    <input
                      inputMode="numeric"
                      maxLength={8}
                      value={pin}
                      onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                      placeholder="PIN 6자리"
                      className="w-full rounded-xl bg-white border border-gray-300 px-3 py-2 text-[14px] tracking-[0.3em] text-center text-gray-900 outline-none focus:border-blue-500"
                      autoFocus
                    />
                    {pinError && (
                      <div className="text-[11.5px] text-red-600 leading-snug">{pinError}</div>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => { setGate("hidden"); setPin(""); setPinError(null); }}
                        className="flex-1 py-2 rounded-xl border border-gray-300 text-[12.5px] text-gray-700 hover:bg-gray-50"
                      >
                        취소
                      </button>
                      <Button onClick={unlock} disabled={pinBusy || pin.length < 4}>
                        {pinBusy ? "확인 중..." : "확인"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="max-w-[88%] bg-white border border-gray-200 rounded-[14px] overflow-hidden shadow-sm">
                <div className="px-3.5 py-2.5 border-b border-gray-200 flex items-center justify-between">
                  <span className="text-[12.5px] font-bold text-gray-900">
                    {session.period} 급여 상세
                  </span>
                  <button onClick={lockAgain} className="text-[11px] text-gray-500 underline">
                    닫기
                  </button>
                </div>
                {payroll && payroll.length > 0 ? (
                  <table className="w-full text-[12.5px]">
                    <thead>
                      <tr className="text-[11px] text-gray-500">
                        <th className="text-left px-3.5 py-1.5 font-medium">이름</th>
                        <th className="text-right px-2 py-1.5 font-medium">전월</th>
                        <th className="text-right px-3.5 py-1.5 font-medium">이번 달</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payroll.map((row, i) => (
                        <tr key={i} className="border-t border-gray-100">
                          <td className="px-3.5 py-2 text-gray-900">{row.name}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-gray-500">
                            {row.prev_amount != null ? row.prev_amount.toLocaleString() : "—"}
                          </td>
                          <td className="px-3.5 py-2 text-right tabular-nums font-semibold text-gray-900">
                            {row.total_amount.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="px-3.5 py-3 text-[12px] text-gray-500">
                    아직 이번 달 자료가 없어요.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="h-2" />
      </div>

      {/* Bottom input bar */}
      <div className={`px-3 py-2 bg-white border-t border-gray-200 items-center gap-2 shrink-0 ${session.accepting ? "flex" : "hidden"}`}>
        <label className="w-9 h-9 rounded-full bg-gray-50 flex items-center justify-center text-gray-700 cursor-pointer shrink-0 hover:bg-gray-200 transition-colors">
          <span className="text-lg">+</span>
          <input type="file" className="hidden" accept="audio/*,.mp3,.m4a,.wav,.xlsx,.xls,.csv,.png,.jpg,.jpeg"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
        </label>
        <div
          onClick={() => setMode("text")}
          className="flex-1 h-9 bg-gray-50 rounded-full px-3.5 flex items-center text-[13.5px] text-gray-500 cursor-text"
        >
          메시지 입력…
        </div>
        <button
          onClick={() => { if (text.trim()) submit(); else setMode("text"); }}
          className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-[0_4px_12px_-4px_rgba(19,112,206,0.5)]"
        >
          <span className="text-sm">↑</span>
        </button>
      </div>
    </div>
  );
}

function ChatBubbleThem({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 items-end mb-1">
      <div className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-blue-600 to-blue-600 text-white flex items-center justify-center shrink-0 text-[13px] font-extrabold">
        조
      </div>
      <div className="max-w-[78%]">
        <div className="bg-white border border-gray-200 rounded-[4px_16px_16px_16px] px-3.5 py-2.5 text-[14px] text-gray-900 leading-relaxed shadow-sm">
          {children}
        </div>
      </div>
    </div>
  );
}
