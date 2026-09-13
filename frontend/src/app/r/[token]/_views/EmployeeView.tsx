"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "@/lib/api";

import { Avatar } from "../_components/Avatar";
import { Badge } from "../_components/Badge";
import { Card } from "../_components/Card";
import { KpiCard } from "../_components/KpiCard";
import { Modal } from "../_components/Modal";
import styles from "../_components/portal.module.css";
import { formatKrw, formatKrwCompact, incomeTypeLabel, periodLabel } from "../_components/format";
import type { EmployeeDetail, EmployeeRow } from "../_components/types";

export function EmployeeView({
  token,
  employees,
  gateOpen,
  grant,
  onNeedPin,
  onOpenHire,
}: {
  token: string;
  employees: EmployeeRow[];
  gateOpen: boolean;
  grant: string | null;
  onNeedPin: () => void;
  onOpenHire: () => void;
}) {
  const [tab, setTab] = useState<"active" | "resigned">("active");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<EmployeeRow | null>(null);

  const filtered = useMemo(() => {
    const wanted = tab === "active" ? "ACTIVE" : "RESIGNED";
    return employees.filter((e) => e.status === wanted && (!q || e.name.includes(q)));
  }, [employees, tab, q]);

  const activeCount = employees.filter((e) => e.status === "ACTIVE").length;
  const resignedCount = employees.filter((e) => e.status === "RESIGNED").length;

  return (
    <>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className={styles.title}>직원별 명세</div>
          <div className={styles.subtitle}>재직 {activeCount}명 · 퇴사 {resignedCount}명</div>
        </div>
        <button type="button" onClick={onOpenHire} className={styles.ctaSecondary} style={{ padding: "10px 14px", fontSize: 13 }}>
          + 신입 등록
        </button>
      </div>

      <div className="flex gap-2 mb-3">
        {(["active", "resigned"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className="rounded-full px-4 py-1.5 text-[12.5px] font-semibold border"
            style={{
              background: tab === t ? "var(--palepill)" : "transparent",
              color: tab === t ? "var(--blue-2)" : "var(--muted)",
              borderColor: tab === t ? "transparent" : "var(--line)",
            }}
          >
            {t === "active" ? `재직 ${activeCount}` : `퇴사 ${resignedCount}`}
          </button>
        ))}
      </div>

      <div className="relative mb-3">
        <input
          className={styles.input}
          placeholder="이름 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <Card>
          <div className="text-[13px] text-[var(--muted)] text-center">
            {q ? "검색 결과가 없어요." : tab === "active" ? "등록된 재직자가 없어요." : "퇴사자가 없어요."}
          </div>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((e) => (
            <button
              key={e.id}
              type="button"
              onClick={() => setSelected(e)}
              className="text-left"
            >
              <Card tight className="hover:border-[color:var(--blue)]">
                <div className="flex items-center gap-3">
                  <Avatar name={e.name} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-bold truncate">{e.name}</span>
                      {e.income_type && (
                        <Badge
                          tone={
                            e.income_type === "WAGE"
                              ? "blue"
                              : e.income_type === "BUSINESS"
                                ? "violet"
                                : e.income_type === "DAILY"
                                  ? "amber"
                                  : "slate"
                          }
                          dot={false}
                        >
                          {incomeTypeLabel(e.income_type)}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-[var(--muted)] truncate">
                      {[e.department, e.position].filter(Boolean).join(" · ") || "직위 미등록"}
                    </div>
                  </div>
                  <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden>
                    <path
                      d="M7 5l5 5-5 5"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              </Card>
            </button>
          ))}
        </div>
      )}

      <EmployeeDetailModal
        token={token}
        open={selected !== null}
        onClose={() => setSelected(null)}
        row={selected}
        gateOpen={gateOpen}
        grant={grant}
        onNeedPin={onNeedPin}
      />
    </>
  );
}

function EmployeeDetailModal({
  token,
  open,
  onClose,
  row,
  gateOpen,
  grant,
  onNeedPin,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
  row: EmployeeRow | null;
  gateOpen: boolean;
  grant: string | null;
  onNeedPin: () => void;
}) {
  const [tab, setTab] = useState<"summary" | "history">("summary");
  const { data: detail, isLoading: loading, error } = useQuery({
    queryKey: ["portal", token, "employee", row?.id, grant],
    queryFn: () =>
      api<EmployeeDetail>(`/api/v1/public/r/${token}/employees/${row!.id}`, {
        headers: grant ? { "X-Portal-Grant": grant } : undefined,
      }),
    enabled: !!row,
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={row?.name ?? "직원"}
    >
      {loading && (
        <div className="text-[13px] text-[var(--muted)] text-center py-6">불러오는 중…</div>
      )}
      {error && <div className="text-[13px] text-red-600">{(error as Error).message}</div>}
      {detail && (
        <>
          {/* 요약 스트립 */}
          <div className="flex items-center gap-3">
            <Avatar name={detail.name} size={56} />
            <div className="min-w-0 flex-1">
              <div className="text-[16px] font-bold">{detail.name}</div>
              <div className="text-[11.5px] text-[var(--muted)] mt-0.5">
                {[detail.department, detail.position].filter(Boolean).join(" · ") || "직위 미등록"}
              </div>
            </div>
            <Badge tone={detail.status === "ACTIVE" ? "mint" : "slate"}>
              {detail.status === "ACTIVE" ? "재직" : "퇴사"}
            </Badge>
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-2 text-[12.5px]">
            <MetaCell label="소득종류" value={incomeTypeLabel(detail.income_type)} />
            <MetaCell label="입사일" value={detail.hired_at ?? "—"} />
            <MetaCell label="상태" value={detail.status === "ACTIVE" ? "재직중" : "퇴사"} />
            <MetaCell label="퇴사일" value={detail.resigned_at ?? "—"} />
          </dl>

          {/* 탭 */}
          <div className="mt-5 border-b border-[var(--line)] flex gap-4">
            {(["summary", "history"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className="pb-2 text-[13px] font-semibold relative"
                style={{ color: tab === t ? "var(--blue-2)" : "var(--muted)" }}
              >
                {t === "summary" ? "요약" : "급여 이력"}
                {tab === t && (
                  <span className="absolute left-0 right-0 -bottom-px h-[2.5px] rounded bg-[var(--blue)]" />
                )}
              </button>
            ))}
          </div>

          {/* 탭 내용 */}
          {!gateOpen ? (
            <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--bg)] px-4 py-5 text-center">
              <div className="text-[13px] font-semibold">🔒 급여 정보는 PIN 인증 후 볼 수 있어요</div>
              <button
                type="button"
                onClick={onNeedPin}
                className={styles.ctaPrimary}
                style={{ padding: "10px 16px", fontSize: 13, marginTop: 10 }}
              >
                PIN 입력
              </button>
            </div>
          ) : tab === "summary" ? (
            <div className="mt-4 grid grid-cols-3 gap-2">
              <KpiCard
                label="올해 총 지급"
                value={detail.total_ytd != null ? formatKrwCompact(detail.total_ytd) : "—"}
                accent="primary"
              />
              <KpiCard
                label="월평균"
                value={detail.monthly_avg != null ? formatKrwCompact(detail.monthly_avg) : "—"}
              />
              <KpiCard
                label="원천세 계"
                value={detail.tax_ytd != null ? formatKrwCompact(detail.tax_ytd) : "—"}
              />
            </div>
          ) : (
            <div className="mt-4">
              {detail.history && detail.history.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {detail.history.map((h) => (
                    <div key={h.period} className="flex items-center justify-between rounded-xl border border-[var(--line)] px-3 py-2.5">
                      <div>
                        <div className="text-[13px] font-semibold">{periodLabel(h.period)}</div>
                        <div className="text-[11px] text-[var(--muted)]">
                          원천세 {formatKrw(h.tax)} · 실지급 {formatKrw(h.net_amount)}
                        </div>
                      </div>
                      <div className="text-[14px] font-bold tabular-nums" style={{ color: "var(--navy)" }}>
                        {formatKrw(h.total_amount)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[13px] text-[var(--muted)]">올해 급여 이력이 없습니다.</div>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--bg)] px-3 py-2">
      <div className="text-[10.5px] uppercase tracking-wider text-[var(--muted-2)]">{label}</div>
      <div className="mt-0.5 text-[13px] font-semibold">{value}</div>
    </div>
  );
}
