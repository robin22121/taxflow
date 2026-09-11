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
type SubmitResult = {
  matched: number;
  new_hire_suspected: number;
  resignation_suspected: number;
  ambiguous: number;
  needs_followup?: number;
  unconfirmed?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Tab = "input" | "filings" | "payslips";

const TABS: { key: Tab; label: string; hint: string }[] = [
  { key: "input", label: "급여 입력", hint: "이번 달 자료 보내기" },
  { key: "filings", label: "신고 내역", hint: "납부세액·접수증" },
  { key: "payslips", label: "급여명세서", hint: "월별 내려받기" },
];

export default function OwnerPortalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [tab, setTab] = useState<Tab>("input");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [mode, setMode] = useState<"idle" | "text" | "processing">("idle");
  // PIN 게이트 — 금액이 걸린 것만 자물쇠 뒤에 둔다 (plan/12-owner-portal.md §4.3.1)
  const [gate, setGate] = useState<"hidden" | "asking" | "open">("hidden");
  const [grant, setGrant] = useState<string | null>(null);
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
  // 보관함 — 얼마 내야 하나 / 접수증 있나 (§3.1, §3.4)
  const [archive, setArchive] = useState<ArchiveRow[]>([]);
  const [downloading, setDownloading] = useState<string | null>(null);

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
        setGrant(saved);
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
      setGrant(res.grant);
      setGate("open");
      setPin("");
    } catch (e) {
      setPinError((e as Error).message);
    } finally {
      setPinBusy(false);
    }
  }

  function lockAgain() {
    sessionStorage.removeItem(grantKey);
    setGrant(null);
    setPayroll(null);
    setGate("hidden");
  }

  async function downloadPayslips(period: string) {
    if (!grant) {
      setGate("asking");
      return;
    }
    setDownloading(period);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/public/r/${token}/payslips/${period}`,
        { headers: { "X-Portal-Grant": grant } },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "명세서를 받지 못했어요");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `급여명세서_${period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setDownloading(null);
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

  if (error && !session) {
    return (
      <main className="min-h-dvh bg-gray-50 flex items-center justify-center px-5">
        <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 text-center shadow-sm">
          <div className="text-[15px] font-semibold text-gray-900">링크를 열 수 없어요</div>
          <p className="mt-2 text-[13px] text-gray-500">{error}</p>
          <p className="mt-3 text-[12px] text-gray-400">세무사 사무소에 문의해 주세요.</p>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="min-h-dvh bg-gray-50 flex items-center justify-center">
        <div className="text-[13px] text-gray-400">불러오는 중…</div>
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-gray-50">
      {/* 상단 — 어느 회사의 무엇인지 한눈에 */}
      <header className="bg-white border-b border-gray-200">
        <div className="mx-auto max-w-3xl px-5 pt-5 pb-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-blue-600">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-gray-900 text-[10px] font-extrabold text-white">이</span>
            이지원천
          </div>
          <h1 className="mt-2 text-[20px] font-bold tracking-tight text-gray-900">
            {session.client_name}
          </h1>
          <div className="mt-1 flex items-center gap-2 text-[12.5px] text-gray-500">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${
              session.accepting
                ? "bg-blue-50 text-blue-700 border border-blue-100"
                : "bg-gray-100 text-gray-500 border border-gray-200"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${session.accepting ? "bg-blue-500" : "bg-gray-400"}`} />
              {periodLabel(session.period)} {session.accepting ? "자료 받는 중" : "접수 마감"}
            </span>
            <span className="text-gray-300">·</span>
            <span>세무 대리 · 원천세 신고</span>
          </div>
        </div>

        {/* 탭 */}
        <nav className="mx-auto max-w-3xl px-5">
          <div className="flex gap-1 overflow-x-auto">
            {TABS.map((t) => {
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`relative shrink-0 px-3.5 pb-2.5 pt-1 text-[14px] font-semibold transition-colors ${
                    active ? "text-blue-600" : "text-gray-500 hover:text-gray-800"
                  }`}
                >
                  {t.label}
                  {active && <span className="absolute inset-x-2 bottom-0 h-[2.5px] rounded-t bg-blue-600" />}
                </button>
              );
            })}
          </div>
        </nav>
      </header>

      <div className="mx-auto max-w-3xl px-5 py-5 space-y-4 pb-16">
        {tab === "input" && (
          <>
            <Section title={`${periodLabel(session.period)} 급여 자료`}
              desc={session.accepting
                ? "급여대장 파일을 올리거나, 직접 적어 보내주세요."
                : "이번 달 접수는 마감됐어요. 변경할 내용이 있으면 세무사 사무소로 알려주세요."}>
              {session.accepting ? (
                <>
                  <div className="grid grid-cols-2 gap-2.5">
                    <label className="cursor-pointer rounded-xl border border-gray-200 bg-white px-4 py-5 text-center transition-colors hover:border-blue-300 hover:bg-blue-50/40">
                      <input type="file" className="hidden" disabled={submitting}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          e.target.value = "";
                          if (f) handleFile(f);
                        }} />
                      <div className="text-[22px]">📄</div>
                      <div className="mt-1.5 text-[13.5px] font-semibold text-gray-900">파일 올리기</div>
                      <div className="text-[11.5px] text-gray-500">엑셀·사진·PDF</div>
                    </label>
                    <button onClick={() => setMode(mode === "text" ? "idle" : "text")}
                      disabled={submitting}
                      className="rounded-xl border border-gray-200 bg-white px-4 py-5 text-center transition-colors hover:border-blue-300 hover:bg-blue-50/40 disabled:opacity-50">
                      <div className="text-[22px]">✏️</div>
                      <div className="mt-1.5 text-[13.5px] font-semibold text-gray-900">직접 적기</div>
                      <div className="text-[11.5px] text-gray-500">이름과 금액만</div>
                    </button>
                  </div>

                  {mode === "text" && (
                    <div className="mt-3 space-y-2">
                      <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
                        placeholder="예) 김연호 320만원, 박지훈 250만원&#10;지난달과 같으면 '지난달과 동일'이라고만 적어주셔도 돼요."
                        className="w-full rounded-xl border border-gray-200 bg-white px-3.5 py-3 text-[14px] outline-none focus:border-blue-500" />
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" onClick={() => { setMode("idle"); setText(""); }}>취소</Button>
                        <Button onClick={submit} disabled={submitting || !text.trim()}>보내기</Button>
                      </div>
                    </div>
                  )}

                  {mode === "processing" && (
                    <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-[13px] text-blue-700">
                      자료를 읽고 있어요. 잠시만 기다려 주세요…
                    </div>
                  )}

                  {error && (
                    <div className="mt-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-red-600">
                      {error}
                    </div>
                  )}

                  {result && (
                    <div className="mt-3 rounded-xl border border-gray-200 bg-white px-4 py-3.5">
                      <div className="text-[13.5px] font-semibold text-gray-900">보내주셔서 감사합니다</div>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-gray-600">
                        <span>확인된 직원 <strong className="text-gray-900">{result.matched}</strong>명</span>
                        {result.new_hire_suspected > 0 && <span>새 직원 <strong className="text-gray-900">{result.new_hire_suspected}</strong>명</span>}
                        {result.resignation_suspected > 0 && <span>퇴사 확인 <strong className="text-gray-900">{result.resignation_suspected}</strong>명</span>}
                      </div>
                      <p className="mt-2 text-[11.5px] text-gray-400">
                        세무사 사무소에서 확인 후 신고를 진행합니다.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-5 text-center text-[13px] text-gray-500">
                  다음 달 자료 요청 때 다시 안내드릴게요.
                </div>
              )}
            </Section>

            <Section title="직원이 바뀌었나요?"
              desc="입사·퇴사를 알려주시면 4대보험 신고까지 함께 처리합니다.">
              {changeDone && (
                <div className="mb-2.5 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-[13px] text-blue-700">
                  {changeDone}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2.5">
                <button onClick={() => { setChangeError(null); setChangeMode(changeMode === "hire" ? "none" : "hire"); }}
                  className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-[13.5px] font-semibold text-gray-900 hover:border-blue-300 hover:bg-blue-50/40">
                  + 새 직원이 왔어요
                </button>
                <button onClick={() => (changeMode === "resign" ? setChangeMode("none") : openResign())}
                  className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-[13.5px] font-semibold text-gray-900 hover:border-blue-300 hover:bg-blue-50/40">
                  − 그만둔 직원이 있어요
                </button>
              </div>

              {changeMode === "hire" && (
                <div className="mt-3 space-y-2">
                  <input value={hireName} onChange={(e) => setHireName(e.target.value)} placeholder="이름"
                    className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[14px] outline-none focus:border-blue-500" />
                  <label className="block text-[12px] text-gray-500">입사일</label>
                  <input type="date" value={hireDate} onChange={(e) => setHireDate(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[14px]" />
                  <p className="text-[11.5px] text-gray-400">주민등록번호는 여기에 적지 마세요. 사무소에서 따로 안전하게 받습니다.</p>
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setChangeMode("none")}>취소</Button>
                    <Button onClick={submitChange} disabled={changeBusy || !hireName.trim()}>알리기</Button>
                  </div>
                </div>
              )}

              {changeMode === "resign" && (
                <div className="mt-3 space-y-2">
                  <select value={resignId} onChange={(e) => setResignId(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[14px]">
                    <option value="">직원 선택</option>
                    {(roster ?? []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                  <label className="block text-[12px] text-gray-500">퇴사일</label>
                  <input type="date" value={resignDate} onChange={(e) => setResignDate(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[14px]" />
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setChangeMode("none")}>취소</Button>
                    <Button onClick={submitChange} disabled={changeBusy || !resignId}>알리기</Button>
                  </div>
                </div>
              )}

              {changeError && <p className="mt-2 text-[12.5px] text-red-600">{changeError}</p>}
            </Section>

            <Section title="이번 달 직원별 급여" desc="확인이 필요하면 PIN을 입력해 주세요.">
              <GatedPayroll
                hasPin={session.has_pin} gate={gate} setGate={setGate}
                pin={pin} setPin={setPin} pinError={pinError} pinBusy={pinBusy}
                unlock={unlock} payroll={payroll} lockAgain={lockAgain} />
            </Section>
          </>
        )}

        {tab === "filings" && (
          <Section title="원천세 신고 내역" desc="월별 납부세액과 접수증·납부서를 보관합니다.">
            {archive.length === 0 ? (
              <Empty>아직 신고 내역이 없어요.</Empty>
            ) : (
              <div className="divide-y divide-gray-100">
                {archive.map((row) => (
                  <div key={row.period} className="py-3.5 first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-[14.5px] font-semibold text-gray-900">{periodLabel(row.period)}</div>
                        <div className="mt-0.5 text-[13px] text-gray-600 tabular-nums">
                          {row.settled_tax != null ? (
                            <>납부세액 <strong className="text-gray-900">{formatKrw(row.settled_tax)}</strong></>
                          ) : (
                            <>예상세액 {formatKrw(row.estimated_tax)}</>
                          )}
                        </div>
                        {row.due_date && (
                          <div className="mt-0.5 text-[12px] text-gray-500 tabular-nums">납부기한 {row.due_date}</div>
                        )}
                        {row.virtual_account && (
                          <div className="mt-0.5 text-[12px] text-gray-500">가상계좌 {row.virtual_account}</div>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-col gap-1.5">
                        <DocLink token={token} period={row.period} kind="receipt" enabled={row.has_receipt} label="접수증" />
                        <DocLink token={token} period={row.period} kind="payment-slip" enabled={row.has_payment_slip} label="납부서" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {tab === "payslips" && (
          <Section title="급여명세서" desc="직원별 지급·공제 내역입니다. PIN 확인 후 내려받을 수 있어요.">
            {gate !== "open" ? (
              <GatedPayroll
                hasPin={session.has_pin} gate={gate} setGate={setGate}
                pin={pin} setPin={setPin} pinError={pinError} pinBusy={pinBusy}
                unlock={unlock} payroll={null} lockAgain={lockAgain} payslipMode />
            ) : archive.length === 0 ? (
              <Empty>아직 명세서가 없어요.</Empty>
            ) : (
              <div className="divide-y divide-gray-100">
                {archive.map((row) => (
                  <div key={row.period} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                    <div className="text-[14px] font-semibold text-gray-900">{periodLabel(row.period)}</div>
                    <Button variant="secondary" className="!text-[12.5px] !px-3 !py-1.5"
                      onClick={() => downloadPayslips(row.period)}
                      disabled={downloading === row.period}>
                      {downloading === row.period ? "받는 중…" : "내려받기"}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        <p className="pt-2 text-center text-[11.5px] text-gray-400">
          이 링크는 {session.client_name} 전용입니다. 보내주신 내용은 세무사 사무소만 확인합니다.
        </p>
      </div>
    </main>
  );
}

/* ═══ 조각 ═══ */

function Section({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-[15.5px] font-bold tracking-tight text-gray-900">{title}</h2>
      {desc && <p className="mt-1 mb-3.5 text-[12.5px] leading-relaxed text-gray-500">{desc}</p>}
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-6 text-center text-[13px] text-gray-500">
      {children}
    </div>
  );
}

function DocLink({ token, period, kind, enabled, label }: {
  token: string; period: string; kind: "receipt" | "payment-slip"; enabled: boolean; label: string;
}) {
  if (!enabled) {
    return (
      <span className="rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-center text-[12px] text-gray-400">
        {label} 준비중
      </span>
    );
  }
  return (
    <a href={`${API_BASE}/api/v1/public/r/${token}/archive/${period}/${kind}`}
      target="_blank" rel="noreferrer"
      className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-center text-[12px] font-semibold text-blue-700 hover:bg-blue-100">
      {label} 보기
    </a>
  );
}

function GatedPayroll({
  hasPin, gate, setGate, pin, setPin, pinError, pinBusy, unlock, payroll, lockAgain, payslipMode,
}: {
  hasPin: boolean;
  gate: "hidden" | "asking" | "open";
  setGate: (g: "hidden" | "asking" | "open") => void;
  pin: string;
  setPin: (v: string) => void;
  pinError: string | null;
  pinBusy: boolean;
  unlock: () => void;
  payroll: PayrollRow[] | null;
  lockAgain: () => void;
  payslipMode?: boolean;
}) {
  if (!hasPin) {
    return <Empty>PIN이 아직 발급되지 않았어요. 세무사 사무소에 요청해 주세요.</Empty>;
  }

  if (gate !== "open") {
    return gate === "asking" ? (
      <div className="space-y-2">
        <input inputMode="numeric" value={pin} maxLength={8}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          onKeyDown={(e) => { if (e.key === "Enter") unlock(); }}
          placeholder="PIN 6자리"
          className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-center text-[16px] tracking-[0.3em] outline-none focus:border-blue-500" />
        {pinError && <p className="text-[12.5px] text-red-600">{pinError}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => { setGate("hidden"); setPin(""); }}>취소</Button>
          <Button onClick={unlock} disabled={pinBusy || pin.length < 4}>{pinBusy ? "확인 중…" : "확인"}</Button>
        </div>
      </div>
    ) : (
      <button onClick={() => setGate("asking")}
        className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-4 text-[13.5px] font-medium text-gray-700 hover:border-blue-300 hover:bg-blue-50/40">
        🔒 PIN 입력하고 {payslipMode ? "명세서 보기" : "급여 확인하기"}
      </button>
    );
  }

  if (payslipMode) return null;

  return (
    <div>
      {payroll && payroll.length > 0 ? (
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="border-b border-gray-200 text-[11.5px] uppercase tracking-wider text-gray-500">
              <th className="py-2 text-left font-semibold">이름</th>
              <th className="py-2 text-right font-semibold">지난달</th>
              <th className="py-2 text-right font-semibold">이번 달</th>
            </tr>
          </thead>
          <tbody>
            {payroll.map((r) => (
              <tr key={r.name} className="border-b border-gray-100 last:border-0">
                <td className="py-2 font-medium text-gray-900">{r.name}</td>
                <td className="py-2 text-right tabular-nums text-gray-400">
                  {r.prev_amount != null ? formatKrw(r.prev_amount) : "—"}
                </td>
                <td className="py-2 text-right tabular-nums font-semibold text-gray-900">
                  {formatKrw(r.total_amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Empty>아직 등록된 급여가 없어요.</Empty>
      )}
      <div className="mt-2.5 text-right">
        <button onClick={lockAgain} className="text-[12px] text-gray-400 hover:text-gray-700">다시 잠그기</button>
      </div>
    </div>
  );
}

function periodLabel(period: string): string {
  const [y, m] = period.split("-");
  return `${y}년 ${Number(m)}월`;
}

function formatKrw(n: number): string {
  return `${n.toLocaleString("ko-KR")}원`;
}
