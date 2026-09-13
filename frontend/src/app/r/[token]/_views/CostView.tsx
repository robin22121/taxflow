"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/lib/api";

import { StackedBarChart } from "../_components/BarChart";
import { Card, SectionHeader } from "../_components/Card";
import { KpiCard } from "../_components/KpiCard";
import { formatKrw, formatKrwCompact, periodLabel } from "../_components/format";
import styles from "../_components/portal.module.css";
import type { MonthlyCostReport } from "../_components/types";

const RANGES = [3, 6, 12, 24] as const;

export function CostView({ token }: { token: string }) {
  const [months, setMonths] = useState<(typeof RANGES)[number]>(12);
  const { data: report, isLoading: loading, error } = useQuery({
    queryKey: ["portal", token, "monthly-cost", months],
    queryFn: () =>
      api<MonthlyCostReport>(
        `/api/v1/public/r/${token}/monthly-cost?months=${months}`,
      ),
  });

  const yoy = report?.kpis.yoy_pct;

  return (
    <>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <div className={styles.title}>월별 인건비</div>
          <div className={styles.subtitle}>사업장 전체 지급액 흐름</div>
        </div>
        <div className="flex gap-1 p-1 bg-[var(--card)] border border-[var(--line)] rounded-full">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setMonths(r)}
              className="text-[12px] font-semibold px-3 py-1 rounded-full"
              style={{
                background: months === r ? "var(--palepill)" : "transparent",
                color: months === r ? "var(--blue-2)" : "var(--muted)",
              }}
            >
              {r}개월
            </button>
          ))}
        </div>
      </div>

      <div className={styles.kpiGrid}>
        <KpiCard
          label={`${months}개월 총 지급`}
          value={report ? formatKrwCompact(report.kpis.total) : "—"}
          accent="primary"
          hint={report && report.kpis.total > 0 ? formatKrw(report.kpis.total) : undefined}
        />
        <KpiCard
          label="월평균"
          value={report ? formatKrwCompact(report.kpis.monthly_avg) : "—"}
        />
        <KpiCard
          label="전년 동월 대비"
          value={
            yoy == null
              ? "—"
              : yoy >= 0
                ? `+${yoy.toFixed(1)}%`
                : `${yoy.toFixed(1)}%`
          }
          hint={yoy != null ? (yoy >= 0 ? "증가" : "감소") : "데이터 부족"}
        />
      </div>

      <div className="mt-5">
        <Card>
          <SectionHeader title="소득종류별 지급" desc="근로 · 사업 · 일용 · 기타" />
          {loading && (
            <div className="h-40 flex items-center justify-center text-[13px] text-[var(--muted)]">
              불러오는 중…
            </div>
          )}
          {error && <div className="text-[13px] text-red-600">{(error as Error).message}</div>}
          {report && !loading && <StackedBarChart data={report.series} />}
        </Card>
      </div>

      <div className="mt-5">
        <SectionHeader title="월별 상세" />
        {report && (
          <div className="flex flex-col gap-2">
            {[...report.series]
              .reverse()
              .filter((p) => p.total > 0)
              .map((p) => (
                <Card key={p.period} tight>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[14px] font-bold">{periodLabel(p.period)}</div>
                    <div className="text-[14px] font-bold tabular-nums" style={{ color: "var(--navy)" }}>
                      {formatKrw(p.total)}
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11.5px] text-[var(--muted)]">
                    <MiniStat label="근로" value={p.wage} />
                    <MiniStat label="사업" value={p.business} />
                    <MiniStat label="일용" value={p.daily} />
                    <MiniStat label="기타" value={p.other} />
                  </div>
                </Card>
              ))}
            {report.series.every((p) => p.total === 0) && (
              <Card>
                <div className="text-[13px] text-[var(--muted)]">
                  아직 이 기간에 지급된 인건비가 없습니다.
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-[var(--bg)] px-2.5 py-2">
      <div className="text-[10.5px] uppercase tracking-wider">{label}</div>
      <div className="text-[12.5px] font-semibold tabular-nums text-[var(--text)] mt-0.5">
        {value > 0 ? formatKrwCompact(value) : "—"}
      </div>
    </div>
  );
}
