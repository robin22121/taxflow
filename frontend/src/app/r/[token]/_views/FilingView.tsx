"use client";

import { useState } from "react";

import { api, apiUpload } from "@/lib/api";

import { Badge } from "../_components/Badge";
import { Card, SectionHeader } from "../_components/Card";
import { IconBox } from "../_components/IconBox";
import { Modal } from "../_components/Modal";
import { StatusStrip } from "../_components/StatusStrip";
import styles from "../_components/portal.module.css";
import { formatKrw, incomeTypeLabel, periodLabel } from "../_components/format";
import type {
  EmployeeRow,
  LastMonthInfo,
  PortalStatusInfo,
  SubmitResult,
} from "../_components/types";

type Props = {
  token: string;
  status: PortalStatusInfo;
  lastMonth: LastMonthInfo | null;
  gateOpen: boolean;
  onNeedPin: () => void;
  onSubmitted: () => void;
  employees: EmployeeRow[];
};

export function FilingView({
  token,
  status,
  lastMonth,
  gateOpen,
  onNeedPin,
  onSubmitted,
  employees,
}: Props) {
  const accepting = status.state === "COLLECTING";
  const [showPreview, setShowPreview] = useState(false);
  const [showEntry, setShowEntry] = useState(false);
  const [showHire, setShowHire] = useState(false);
  const [showResign, setShowResign] = useState(false);

  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <>
      <StatusStrip status={status} />

      {/* 지난달 지급명세 접힘 카드 */}
      {lastMonth && lastMonth.period && (
        <Card className="mt-4">
          <button
            type="button"
            onClick={() => setDetailsOpen((v) => !v)}
            className="flex w-full items-center gap-3 text-left"
            aria-expanded={detailsOpen}
          >
            <IconBox tone="slate">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
                <rect x="4" y="3.5" width="12" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
                <path d="M7 7h6M7 10h6M7 13h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </IconBox>
            <div className="min-w-0 flex-1">
              <div className={styles.h3}>지난달({periodLabel(lastMonth.period)}) 지급명세</div>
              <div className="mt-0.5 text-[12.5px] text-[var(--muted)]">
                {lastMonth.employee_count}명 · 지급 {formatKrw(lastMonth.total_amount)} · 원천세{" "}
                {formatKrw(lastMonth.total_tax)}
              </div>
            </div>
            <svg
              width="16"
              height="16"
              viewBox="0 0 20 20"
              fill="none"
              className={`transition-transform ${detailsOpen ? "rotate-180" : ""}`}
              aria-hidden
            >
              <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {detailsOpen && (
            <div className="mt-3 pt-3 border-t border-[var(--line)]">
              {lastMonth.entries === null ? (
                <div className="text-[12.5px] text-[var(--muted)]">
                  개별 명세를 보려면{" "}
                  <button
                    type="button"
                    onClick={onNeedPin}
                    className="text-[var(--blue)] font-semibold underline underline-offset-2"
                  >
                    PIN 입력
                  </button>
                  이 필요합니다.
                </div>
              ) : lastMonth.entries.length === 0 ? (
                <div className="text-[12.5px] text-[var(--muted)]">지난달 명세가 없습니다.</div>
              ) : (
                <table className="w-full text-[13px]">
                  <tbody>
                    {lastMonth.entries.map((e) => (
                      <tr key={e.name} className="border-b border-[var(--line)] last:border-0">
                        <td className="py-2 font-medium">{e.name}</td>
                        <td className="py-2 text-[11.5px] text-[var(--muted)]">
                          {incomeTypeLabel(e.income_type)}
                        </td>
                        <td className="py-2 text-right tabular-nums font-semibold">
                          {formatKrw(e.total_amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </Card>
      )}

      {/* 결정 카드 2개 */}
      <div className="mt-5">
        <SectionHeader title="이번 달 급여 결정" />
        {accepting ? (
          <div className={styles.decisionGrid}>
            <DecisionCard
              tone="primary"
              icon={
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M4 12a8 8 0 0114-5.3M20 12a8 8 0 01-14 5.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M18 3v4h-4M6 21v-4h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              }
              badge="대부분 이거예요"
              title="지난달과 동일"
              desc="지난달 명세 그대로 보냅니다"
              onClick={() => setShowPreview(true)}
            />
            <DecisionCard
              tone="secondary"
              icon={
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M4 20l4-1 10-10-3-3L5 16l-1 4z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                </svg>
              }
              title="직접 입력"
              desc="변동 있는 경우 파일이나 텍스트로 보내기"
              onClick={() => setShowEntry(true)}
            />
          </div>
        ) : (
          <Card>
            <div className="text-[13px] text-[var(--muted)]">
              지금은 자료 수집 기간이 아닙니다. 담당 세무사에게 문의해 주세요.
            </div>
          </Card>
        )}
      </div>

      {/* 직원 변동 */}
      <div className="mt-5">
        <SectionHeader title="직원 변동" desc="입·퇴사는 신고 기간이 아니어도 상시 등록할 수 있어요." />
        <div className={styles.decisionGrid}>
          <DecisionCard
            icon={
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <circle cx="9" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
                <path d="M3 20c1.5-3 4-4.5 6-4.5s4.5 1.5 6 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                <path d="M18 8v6M15 11h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            }
            iconTone="mint"
            title="새 직원이 왔어요"
            desc="이름과 입사일만 알려주시면 됩니다"
            onClick={() => setShowHire(true)}
          />
          <DecisionCard
            icon={
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <circle cx="9" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
                <path d="M3 20c1.5-3 4-4.5 6-4.5s4.5 1.5 6 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                <path d="M15 11h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            }
            iconTone="rose"
            title="그만둔 직원이 있어요"
            desc="4대보험 상실도 함께 신고합니다"
            onClick={() => setShowResign(true)}
          />
        </div>
      </div>

      {/* 미리보기 모달 — "지난달과 동일" 흐름 */}
      <PreviewModal
        token={token}
        open={showPreview}
        onClose={() => setShowPreview(false)}
        lastMonth={lastMonth}
        gateOpen={gateOpen}
        onNeedPin={onNeedPin}
        onSubmitted={() => {
          setShowPreview(false);
          onSubmitted();
        }}
      />

      {/* 직접 입력 모달 */}
      <DirectEntryModal
        token={token}
        open={showEntry}
        onClose={() => setShowEntry(false)}
        onSubmitted={() => {
          setShowEntry(false);
          onSubmitted();
        }}
      />

      {/* 신입 등록 모달 */}
      <HireModal token={token} open={showHire} onClose={() => setShowHire(false)} />

      {/* 퇴사 등록 모달 */}
      <ResignModal
        token={token}
        open={showResign}
        onClose={() => setShowResign(false)}
        employees={employees}
      />
    </>
  );
}

function DecisionCard({
  tone,
  icon,
  iconTone,
  badge,
  title,
  desc,
  onClick,
}: {
  tone?: "primary" | "secondary";
  icon: React.ReactNode;
  iconTone?: "blue" | "mint" | "violet" | "amber" | "rose" | "slate";
  badge?: string;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  const primary = tone === "primary";
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left rounded-2xl p-5 transition-all hover:-translate-y-[1px]"
      style={{
        background: primary ? "linear-gradient(180deg, #EFF6FF, #DBEAFE)" : "var(--card)",
        border: `1px solid ${primary ? "#93C5FD" : "var(--line-strong)"}`,
        boxShadow: primary
          ? "0 12px 30px -18px rgba(37, 99, 235, 0.6)"
          : "0 1px 0 rgba(15,23,42,0.02), 0 8px 24px -20px rgba(15,23,42,0.1)",
      }}
    >
      <div className="flex items-start gap-3">
        <IconBox tone={iconTone ?? (primary ? "blue" : "violet")}>{icon}</IconBox>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="text-[15px] font-bold">{title}</div>
            {badge && (
              <Badge tone="blue" dot={false}>
                {badge}
              </Badge>
            )}
          </div>
          <div className="mt-1 text-[12.5px] text-[var(--muted)]">{desc}</div>
        </div>
      </div>
    </button>
  );
}

function PreviewModal({
  token,
  open,
  onClose,
  lastMonth,
  gateOpen,
  onNeedPin,
  onSubmitted,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
  lastMonth: LastMonthInfo | null;
  gateOpen: boolean;
  onNeedPin: () => void;
  onSubmitted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text: "지난달과 동일" },
      });
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const entries = lastMonth?.entries ?? null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="이번 달 급여 확정"
      footer={
        <>
          <button type="button" className={styles.ctaSecondary} onClick={onClose}>
            취소
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            onClick={confirm}
            disabled={busy}
          >
            {busy ? "보내는 중…" : "이대로 확정"}
          </button>
        </>
      }
    >
      {!lastMonth?.period && (
        <div className="text-[13px] text-[var(--muted)]">
          지난달 자료가 없어 이 기능을 쓸 수 없어요. &lsquo;직접 입력&rsquo;으로 보내주세요.
        </div>
      )}
      {lastMonth?.period && !gateOpen && (
        <div>
          <p className="text-[13px] text-[var(--muted)]">
            지난달 명세를 미리 확인하려면 PIN이 필요합니다. &lsquo;이대로 확정&rsquo;을 누르면 지난달 명세 그대로
            세무사 사무소에 접수됩니다.
          </p>
          <button
            type="button"
            onClick={onNeedPin}
            className="mt-3 text-[13px] text-[var(--blue)] font-semibold underline underline-offset-2"
          >
            PIN 입력하고 미리 보기
          </button>
        </div>
      )}
      {gateOpen && entries && entries.length > 0 && (
        <div>
          <div className="mb-2 text-[12.5px] text-[var(--muted)]">
            아래 명세 그대로 이번 달({periodLabel(lastMonth?.period)}) 자료로 접수됩니다.
          </div>
          <table className="w-full text-[13px]">
            <tbody>
              {entries.map((e) => (
                <tr key={e.name} className="border-b border-[var(--line)] last:border-0">
                  <td className="py-2 font-medium">{e.name}</td>
                  <td className="py-2 text-[11.5px] text-[var(--muted)]">
                    {incomeTypeLabel(e.income_type)}
                  </td>
                  <td className="py-2 text-right tabular-nums font-semibold">
                    {formatKrw(e.total_amount)}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="pt-3 font-bold" colSpan={2}>
                  합계
                </td>
                <td className="pt-3 text-right tabular-nums font-bold text-[var(--navy)]">
                  {formatKrw(lastMonth?.total_amount ?? 0)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="mt-3 text-[12.5px] text-red-600">{error}</p>}
    </Modal>
  );
}

function DirectEntryModal({
  token,
  open,
  onClose,
  onSubmitted,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResult | null>(null);

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<SubmitResult>(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text },
      });
      setResult(res);
      setText("");
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleFile(f: File) {
    setBusy(true);
    setError(null);
    try {
      const res = await apiUpload<SubmitResult>(`/api/v1/public/r/${token}/upload`, f);
      setResult(res);
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        setText("");
        setError(null);
        setResult(null);
        onClose();
      }}
      title="이번 달 급여 자료 보내기"
      footer={
        <>
          <button type="button" className={styles.ctaSecondary} onClick={onClose}>
            닫기
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            onClick={submit}
            disabled={busy || !text.trim()}
          >
            {busy ? "보내는 중…" : "보내기"}
          </button>
        </>
      }
    >
      <label className="block rounded-xl border border-dashed border-[var(--line-strong)] bg-white p-4 text-center hover:border-[var(--blue)] cursor-pointer">
        <input
          type="file"
          className="hidden"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) handleFile(f);
          }}
        />
        <div className="text-[22px]">📄</div>
        <div className="mt-1 text-[13.5px] font-semibold">파일 올리기</div>
        <div className="text-[11.5px] text-[var(--muted)]">엑셀 · 사진 · PDF</div>
      </label>
      <div className="mt-4">
        <div className={styles.h3}>또는 텍스트로 적기</div>
        <textarea
          className={styles.input}
          rows={5}
          style={{ marginTop: 8 }}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="예) 김연호 320만원, 박지훈 250만원"
        />
        <p className="mt-1 text-[11px] text-[var(--muted)]">
          &lsquo;지난달과 동일&rsquo;이라고만 적으셔도 됩니다.
        </p>
      </div>
      {result && (
        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--mint-bg)] px-4 py-3 text-[13px] text-[var(--mint-fg)]">
          보내주셔서 감사합니다. 세무사 사무소에서 확인 후 신고합니다.
        </div>
      )}
      {error && <p className="mt-3 text-[12.5px] text-red-600">{error}</p>}
    </Modal>
  );
}

function HireModal({
  token,
  open,
  onClose,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [hiredAt, setHiredAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ name: string }>(`/api/v1/public/r/${token}/employee-change`, {
        method: "POST",
        json: {
          change_type: "HIRE",
          name: name.trim(),
          hired_at: hiredAt || null,
        },
      });
      setDone(`${res.name} 님 입사를 세무사 사무소에 알렸어요.`);
      setName("");
      setHiredAt("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        setError(null);
        setDone(null);
        onClose();
      }}
      title="새 직원 등록"
      footer={
        <>
          <button type="button" className={styles.ctaSecondary} onClick={onClose}>
            닫기
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            onClick={submit}
            disabled={busy || !name.trim()}
          >
            {busy ? "보내는 중…" : "알리기"}
          </button>
        </>
      }
    >
      <label className="block text-[12px] font-semibold text-[var(--text-2)]">이름</label>
      <input
        className={styles.input}
        style={{ marginTop: 6 }}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="예) 김연호"
      />
      <label className="block mt-3 text-[12px] font-semibold text-[var(--text-2)]">입사일</label>
      <input
        type="date"
        className={styles.input}
        style={{ marginTop: 6 }}
        value={hiredAt}
        onChange={(e) => setHiredAt(e.target.value)}
      />
      <p className="mt-3 text-[11.5px] text-[var(--muted)]">
        주민등록번호는 여기에 적지 마세요. 사무소에서 따로 안전하게 받습니다.
      </p>
      {done && (
        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--mint-bg)] px-3 py-2 text-[12.5px] text-[var(--mint-fg)]">
          {done}
        </div>
      )}
      {error && <p className="mt-3 text-[12.5px] text-red-600">{error}</p>}
    </Modal>
  );
}

function ResignModal({
  token,
  open,
  onClose,
  employees,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
  employees: EmployeeRow[];
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [resignedAt, setResignedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ name: string }>(`/api/v1/public/r/${token}/employee-change`, {
        method: "POST",
        json: {
          change_type: "RESIGN",
          employee_id: employeeId,
          resigned_at: resignedAt || null,
        },
      });
      setDone(`${res.name} 님 퇴사를 세무사 사무소에 알렸어요.`);
      setEmployeeId("");
      setResignedAt("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        setError(null);
        setDone(null);
        onClose();
      }}
      title="퇴사 직원 등록"
      footer={
        <>
          <button type="button" className={styles.ctaSecondary} onClick={onClose}>
            닫기
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            onClick={submit}
            disabled={busy || !employeeId}
          >
            {busy ? "보내는 중…" : "알리기"}
          </button>
        </>
      }
    >
      <label className="block text-[12px] font-semibold text-[var(--text-2)]">직원 선택</label>
      <select
        className={styles.input}
        style={{ marginTop: 6 }}
        value={employeeId}
        onChange={(e) => setEmployeeId(e.target.value)}
      >
        <option value="">그만둔 직원을 선택해 주세요</option>
        {employees
          .filter((e) => e.status === "ACTIVE")
          .map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
      </select>
      <label className="block mt-3 text-[12px] font-semibold text-[var(--text-2)]">퇴사일</label>
      <input
        type="date"
        className={styles.input}
        style={{ marginTop: 6 }}
        value={resignedAt}
        onChange={(e) => setResignedAt(e.target.value)}
      />
      {done && (
        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--mint-bg)] px-3 py-2 text-[12.5px] text-[var(--mint-fg)]">
          {done}
        </div>
      )}
      {error && <p className="mt-3 text-[12.5px] text-red-600">{error}</p>}
    </Modal>
  );
}
