"use client";

import { useState } from "react";

import { Card, SectionHeader } from "../_components/Card";
import { StatusBadge } from "../_components/Badge";
import styles from "../_components/portal.module.css";
import { dDay, formatKrw, periodLabel } from "../_components/format";
import type { ArchiveRow, PortalStatusInfo } from "../_components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function PaymentView({
  token,
  status,
  archive,
}: {
  token: string;
  status: PortalStatusInfo;
  archive: ArchiveRow[];
}) {
  const [copyDone, setCopyDone] = useState(false);
  const amount = status.settled_tax ?? status.estimated_tax;
  const amountLabel = status.settled_tax != null ? "납부세액 (확정)" : "예상 세액";

  const copyable = status.virtual_account ?? status.epayment_number;

  async function copy() {
    if (!copyable) return;
    try {
      await navigator.clipboard.writeText(copyable);
      setCopyDone(true);
      setTimeout(() => setCopyDone(false), 1500);
    } catch {
      // fallback: 선택 저장
    }
  }

  return (
    <>
      <SectionHeader title="원천세 납부하기" desc="얼마 · 언제 · 어디로 — 이 세 가지만 알려드립니다." />
      {status.state === "NONE" ? (
        <Card>
          <div className="text-[13px] text-[var(--muted)]">지금은 안내드릴 납부가 없어요.</div>
        </Card>
      ) : (
        <Card hero>
          <div className="flex items-start justify-between gap-3">
            <div className="text-[11.5px] font-semibold uppercase tracking-wider text-[var(--muted-2)]">
              {status.period && `${periodLabel(status.period)} 귀속`}
            </div>
            <StatusBadge state={status.state} />
          </div>
          <div className="mt-4 flex flex-col gap-1">
            <div className="text-[12.5px] text-[var(--muted)]">{amountLabel}</div>
            <div
              className="text-[36px] font-bold tabular-nums leading-none"
              style={{ color: "var(--navy)" }}
            >
              {formatKrw(amount)}
            </div>
          </div>

          <dl className="mt-6 divide-y divide-[var(--line)]">
            <PayRow
              label="기한"
              value={
                status.due_date ? (
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums">{status.due_date}</span>
                    <span className="text-[11.5px] text-[var(--muted)]">
                      {dDay(status.due_date)}
                    </span>
                  </span>
                ) : (
                  "—"
                )
              }
            />
            <PayRow
              label="납부계좌"
              value={
                status.virtual_account ? (
                  <span className="tabular-nums">{status.virtual_account}</span>
                ) : (
                  "미배정"
                )
              }
              action={
                copyable && (
                  <button type="button" onClick={copy} className={styles.ctaSecondary} style={{ padding: "6px 12px", fontSize: 12 }}>
                    {copyDone ? "복사됨" : "복사"}
                  </button>
                )
              }
            />
            <PayRow
              label="납부서"
              value={
                status.has_payment_slip ? (
                  <a
                    href={`${API_BASE}/api/v1/public/r/${token}/archive/${status.period}/payment-slip`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--blue)] font-semibold"
                  >
                    보기 →
                  </a>
                ) : (
                  <span className="text-[var(--muted)]">준비중</span>
                )
              }
            />
            <PayRow
              label="신고접수증"
              value={
                status.has_receipt ? (
                  <a
                    href={`${API_BASE}/api/v1/public/r/${token}/archive/${status.period}/receipt`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--blue)] font-semibold"
                  >
                    보기 →
                  </a>
                ) : (
                  <span className="text-[var(--muted)]">준비중</span>
                )
              }
            />
          </dl>
        </Card>
      )}

      <div className="mt-5">
        <SectionHeader title="지난 납부 이력" />
        {archive.length === 0 ? (
          <Card>
            <div className="text-[13px] text-[var(--muted)]">아직 이력이 없어요.</div>
          </Card>
        ) : (
          <div className="flex flex-col gap-2.5">
            {archive.map((row) => (
              <Card key={row.period} tight>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[14px] font-bold">{periodLabel(row.period)}</div>
                    <div className="mt-1 text-[13px] tabular-nums">
                      {row.settled_tax != null ? (
                        <>납부세액 <strong>{formatKrw(row.settled_tax)}</strong></>
                      ) : (
                        <span className="text-[var(--muted)]">예상 {formatKrw(row.estimated_tax)}</span>
                      )}
                    </div>
                    {row.due_date && (
                      <div className="text-[11.5px] text-[var(--muted)] mt-0.5">
                        기한 {row.due_date}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <DocLink
                      href={
                        row.has_receipt
                          ? `${API_BASE}/api/v1/public/r/${token}/archive/${row.period}/receipt`
                          : null
                      }
                      label="접수증"
                    />
                    <DocLink
                      href={
                        row.has_payment_slip
                          ? `${API_BASE}/api/v1/public/r/${token}/archive/${row.period}/payment-slip`
                          : null
                      }
                      label="납부서"
                    />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function PayRow({
  label,
  value,
  action,
}: {
  label: string;
  value: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <dt className="text-[12.5px] text-[var(--muted)] w-24">{label}</dt>
      <dd className="flex-1 text-[13.5px] font-semibold">{value}</dd>
      {action}
    </div>
  );
}

function DocLink({ href, label }: { href: string | null; label: string }) {
  if (!href) {
    return (
      <span className="rounded-lg border border-[var(--line)] bg-[var(--card)] px-2.5 py-1 text-[11.5px] text-[var(--muted)]">
        {label} 준비중
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="rounded-lg border border-[color:var(--blue-bg)] bg-[color:var(--blue-bg)] px-2.5 py-1 text-[11.5px] font-semibold text-[var(--blue-fg)] hover:brightness-95"
    >
      {label} 보기
    </a>
  );
}
