"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import {
  useFilingDashboard,
  useFilings,
  useInsuranceSummary,
} from "@/lib/queries";
import { apiBlob } from "@/lib/api";
import { Badge, Card } from "@/components/ui";
import type { CollectionSession } from "@/lib/types";

/* ═══ 4대보험 메뉴 — 월 선택 → 거래처별 신고 대상 ═══ */

export default function InsurancePage() {
  const { data: filings, isLoading: filingsLoading } = useFilings();
  // 사용자 명시 선택은 override 로, 미선택 시 활성 신고기간(미완료) 우선·없으면 최신.
  const [override, setOverride] = useState<string | null>(null);
  const defaultFilingId = useMemo(() => {
    if (!filings || filings.length === 0) return null;
    return (
      filings.find((f) => f.status !== "COMPLETED" && f.status !== "FILED")
        ?? filings[0]
    ).id;
  }, [filings]);
  const filingId = override ?? defaultFilingId;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">4대보험 관리</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          신고기간을 선택해 거래처별 자격취득·자격상실·보수월액변경 대상을 확인하세요.
        </p>
      </div>

      {filingsLoading && (
        <div className="h-12 rounded-[14px] bg-white animate-pulse border border-gray-200" />
      )}

      {!filingsLoading && filings && filings.length > 0 && (
        <PeriodPicker
          filings={filings}
          value={filingId}
          onChange={setOverride}
        />
      )}

      {!filingsLoading && (!filings || filings.length === 0) && (
        <Card className="text-center py-12">
          <p className="text-[14px] font-medium text-gray-700 mb-1">아직 생성된 신고기간이 없습니다</p>
          <p className="text-[12px] text-gray-500">
            <Link href="/dashboard" className="text-blue-600 hover:underline">월별 신고</Link> 메뉴에서 기간을 먼저 생성하세요.
          </p>
        </Card>
      )}

      {filingId && <InsuranceMonth filingId={filingId} />}
    </div>
  );
}

function PeriodPicker({
  filings,
  value,
  onChange,
}: {
  filings: { id: string; period: string; status: string }[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">신고기간</span>
      <div className="flex gap-1 flex-wrap">
        {filings.map((f) => (
          <button
            key={f.id}
            onClick={() => onChange(f.id)}
            className={
              "px-3 py-1.5 rounded-full text-[12px] font-medium transition-colors " +
              (value === f.id
                ? "bg-gray-900 text-white"
                : "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50")
            }
          >
            {f.period}
          </button>
        ))}
      </div>
    </div>
  );
}

function InsuranceMonth({ filingId }: { filingId: string }) {
  const { data: dashboard, isLoading: dashLoading } = useFilingDashboard(filingId);
  const { data: summary, isLoading: sumLoading } = useInsuranceSummary(filingId, null);

  const countsByClient = useMemo(() => {
    const m = new Map<string, { acq: number; loss: number; chg: number }>();
    const incr = (cid: string, key: "acq" | "loss" | "chg") => {
      const cur = m.get(cid) ?? { acq: 0, loss: 0, chg: 0 };
      cur[key] += 1;
      m.set(cid, cur);
    };
    summary?.acquisitions.forEach((t) => incr(t.client_id, "acq"));
    summary?.losses.forEach((t) => incr(t.client_id, "loss"));
    summary?.changes.forEach((t) => incr(t.client_id, "chg"));
    return m;
  }, [summary]);

  const sessions = dashboard?.sessions ?? [];
  const totalAcq = summary?.acquisitions.length ?? 0;
  const totalLoss = summary?.losses.length ?? 0;
  const totalChg = summary?.changes.length ?? 0;

  if (dashLoading || sumLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-14 rounded-[10px] bg-white animate-pulse border border-gray-200" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="자격취득 대상" value={totalAcq} unit="명" />
        <KpiCard label="자격상실 대상" value={totalLoss} unit="명" />
        <KpiCard label="보수월액변경 대상" value={totalChg} unit="명" />
      </div>

      {sessions.length === 0 ? (
        <Card className="text-center py-10 text-[13px] text-gray-500">
          이 신고기간에 등록된 거래처가 없습니다.
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-300 bg-gray-50/50">
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">거래처</th>
                <th className="text-right px-3 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">자격취득</th>
                <th className="text-right px-3 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">자격상실</th>
                <th className="text-right px-3 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">보수월액변경</th>
                <th className="text-right px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">액션</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => {
                const c = countsByClient.get(s.client_id) ?? { acq: 0, loss: 0, chg: 0 };
                const total = c.acq + c.loss + c.chg;
                return (
                  <ClientRow
                    key={s.client_id}
                    filingId={filingId}
                    session={s}
                    counts={c}
                    hasAny={total > 0}
                  />
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function ClientRow({
  filingId,
  session,
  counts,
  hasAny,
}: {
  filingId: string;
  session: CollectionSession;
  counts: { acq: number; loss: number; chg: number };
  hasAny: boolean;
}) {
  async function downloadCombined() {
    try {
      const blob = await apiBlob(
        `/api/v1/filings/${filingId}/insurance-combined?client_id=${session.client_id}`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `4대보험_통합_${session.client_name}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-2.5">
        <span className="font-medium text-gray-900">{session.client_name}</span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <CountBadge n={counts.acq} tone="info" />
      </td>
      <td className="px-3 py-2.5 text-right">
        <CountBadge n={counts.loss} tone="warning" />
      </td>
      <td className="px-3 py-2.5 text-right">
        <CountBadge n={counts.chg} tone="neutral" />
      </td>
      <td className="px-4 py-2.5 text-right whitespace-nowrap">
        <button
          onClick={downloadCombined}
          disabled={!hasAny}
          className="text-[11px] text-blue-600 hover:underline disabled:opacity-40 disabled:no-underline mr-3">
          통합 다운로드
        </button>
        <Link
          href={`/dashboard/filings/${filingId}?client=${session.client_id}`}
          className="text-[11px] text-gray-700 hover:underline">
          상세 →
        </Link>
      </td>
    </tr>
  );
}

function CountBadge({ n, tone }: { n: number; tone: "info" | "warning" | "neutral" }) {
  if (n === 0) {
    return <span className="text-[12px] tabular-nums text-gray-300">0</span>;
  }
  return (
    <Badge tone={tone}>
      <span className="tabular-nums">{n}</span>
    </Badge>
  );
}

function KpiCard({ label, value, unit }: { label: string; value: number; unit?: string }) {
  return (
    <Card className="py-3 px-4">
      <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-[22px] font-bold tracking-tight tabular-nums text-gray-900">{value}</span>
        {unit && <span className="text-[13px] text-gray-500">{unit}</span>}
      </div>
    </Card>
  );
}
