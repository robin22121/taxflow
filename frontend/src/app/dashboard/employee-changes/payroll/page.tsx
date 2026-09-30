"use client";

// 급여명세서 — 거래처정보 상세에 있던 "전월 급여 업로드"·"급여 이력"을 이 메뉴로 옮겼다
// (2026-10-01, plan/08-action-items.md).

import { Fragment, useRef, useState } from "react";
import Link from "next/link";

import { useClientPayrollHistory, useImportPayroll } from "@/lib/queries";
import { Badge, Button, Card } from "@/components/ui";
import { ClientPicker, useSelectedClientId } from "@/components/clients/client-picker";
import { koreanPeriod, previousPeriod, priorPeriod } from "@/lib/format";
import type { ImportPayrollResult } from "@/lib/types";

export default function EmployeePayrollPage() {
  const { clientId, setClientId, loading } = useSelectedClientId();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight text-gray-900">급여명세서</h1>
          <p className="text-[12px] text-gray-500 mt-1">거래처를 고르면 월별 급여자료를 업로드·조회할 수 있습니다.</p>
        </div>
        <ClientPicker value={clientId} onChange={setClientId} />
      </div>

      {!loading && !clientId && (
        <Card className="text-center py-12">
          <p className="text-[13px] text-gray-500">등록된 거래처가 없습니다. 거래처정보에서 먼저 추가하세요.</p>
        </Card>
      )}

      {clientId && <PayrollContent clientId={clientId} />}
    </div>
  );
}

function PayrollContent({ clientId }: { clientId: string }) {
  const importPay = useImportPayroll(clientId);
  const payFileRef = useRef<HTMLInputElement>(null);
  // 진행 중인 신고는 직전 월분(previousPeriod)이고, "전월자료 불러오기"는
  // 그보다 한 달 앞선 자료를 찾는다. 기본값을 거기에 맞춘다.
  const [payPeriod, setPayPeriod] = useState(() => priorPeriod(previousPeriod()));
  const [payResult, setPayResult] = useState<ImportPayrollResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <Link href={`/dashboard/clients/${clientId}`} className="text-[12px] text-blue-600 hover:underline">
        ← 거래처정보로 돌아가기
      </Link>

      {/* 전월 급여 업로드 */}
      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">전월 급여 업로드</h2>
        <div className="space-y-2 p-4 rounded-lg border border-gray-300">
          <p className="text-xs text-gray-500">위하고T 원천징수이행상황신고서 엑셀 (.xlsx, .csv)</p>
          <p className="text-xs text-gray-500">
            선택한 귀속년월의 급여자료로 저장됩니다. 신고 화면의 &ldquo;전월자료 불러오기&rdquo;는 진행 중인 신고월의
            직전 월을 찾으므로, {koreanPeriod(previousPeriod())} 신고를 준비 중이라면{" "}
            {koreanPeriod(priorPeriod(previousPeriod()))} 자료가 필요합니다.
          </p>
          <div className="flex gap-2 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">귀속년월 ({koreanPeriod(payPeriod)})</label>
              <input
                type="month"
                value={payPeriod}
                onChange={(e) => setPayPeriod(e.target.value)}
                className="rounded-lg border border-gray-300 bg-transparent px-2 py-1 text-sm text-gray-900"
              />
            </div>
            <input
              ref={payFileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setError(null);
                setPayResult(null);
                try {
                  const res = await importPay.mutateAsync({ file: f, period: payPeriod });
                  setPayResult(res);
                } catch (err) {
                  setError((err as Error).message);
                }
                e.target.value = "";
              }}
            />
            <Button variant="secondary" onClick={() => payFileRef.current?.click()} disabled={importPay.isPending}>
              {importPay.isPending ? "업로드 중..." : "파일 선택 + 업로드"}
            </Button>
          </div>
          {payResult && (
            <div className="text-xs mt-2 p-2 rounded bg-green-50 text-green-800">
              <p>
                {payResult.period} — 총 {payResult.total_rows}행, 매칭 {payResult.matched}, 미매칭 {payResult.unmatched}, 생성{" "}
                {payResult.created_entries}건
              </p>
              {payResult.errors.length > 0 && (
                <ul className="mt-1 text-amber-700">
                  {payResult.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
        </div>
      </Card>

      <PayrollHistorySection clientId={clientId} />
    </div>
  );
}

/* ─── 급여 이력 — 월별 묶음, 펼치면 직원별 내역 ─── */

function PayrollHistorySection({ clientId }: { clientId: string }) {
  const { data: history, isLoading } = useClientPayrollHistory(clientId);
  const [openPeriod, setOpenPeriod] = useState<string | null>(null);

  return (
    <Card>
      <h2 className="text-lg font-semibold text-gray-900 mb-1">급여 이력</h2>
      <p className="text-xs text-gray-500 mb-3">
        이 거래처에 등록된 모든 월의 급여자료입니다. 월을 클릭하면 직원별
        내역이 펼쳐집니다.
      </p>

      {isLoading ? (
        <p className="text-sm text-gray-500">불러오는 중...</p>
      ) : !history || history.length === 0 ? (
        <p className="text-sm text-gray-500">
          급여자료가 없습니다. 위 &ldquo;전월 급여 업로드&rdquo;에서 월별 자료를
          올리세요.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 border-b border-gray-300">
              <tr>
                <th className="text-left py-2 pr-3">귀속월</th>
                <th className="text-right py-2 pr-3">인원</th>
                <th className="text-right py-2 pr-3">총지급액</th>
                <th className="text-right py-2 pr-3">비과세</th>
                <th className="text-right py-2 pr-3">소득세</th>
                <th className="text-left py-2 pr-3">신고상태</th>
                <th className="text-right py-2"></th>
              </tr>
            </thead>
            <tbody>
              {history.map((p) => (
                <Fragment key={p.period}>
                  <tr
                    className="border-b border-gray-100 cursor-pointer hover:bg-gray-50"
                    onClick={() =>
                      setOpenPeriod(openPeriod === p.period ? null : p.period)
                    }
                  >
                    <td className="py-2 pr-3 font-medium text-gray-900">
                      {koreanPeriod(p.period)}
                    </td>
                    <td className="py-2 pr-3 text-right text-gray-900">
                      {p.employee_count}명
                    </td>
                    <td className="py-2 pr-3 text-right text-gray-900">
                      {p.total_amount.toLocaleString()}
                    </td>
                    <td className="py-2 pr-3 text-right text-gray-500">
                      {p.total_non_taxable.toLocaleString()}
                    </td>
                    <td className="py-2 pr-3 text-right text-gray-500">
                      {p.total_income_tax.toLocaleString()}
                    </td>
                    <td className="py-2 pr-3">
                      <FilingStatusBadge status={p.filing_status} />
                    </td>
                    <td className="py-2 text-right text-xs text-gray-500">
                      {openPeriod === p.period ? "접기" : "펼치기"}
                    </td>
                  </tr>
                  {openPeriod === p.period && (
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <td colSpan={7} className="p-3">
                        <table className="w-full text-xs">
                          <thead className="text-gray-500">
                            <tr>
                              <th className="text-left py-1 pr-3">이름</th>
                              <th className="text-left py-1 pr-3">사번</th>
                              <th className="text-left py-1 pr-3">소득구분</th>
                              <th className="text-right py-1 pr-3">총지급액</th>
                              <th className="text-right py-1 pr-3">비과세</th>
                              <th className="text-right py-1 pr-3">과세</th>
                              <th className="text-right py-1 pr-3">소득세</th>
                              <th className="text-right py-1">지방소득세</th>
                            </tr>
                          </thead>
                          <tbody>
                            {p.rows.map((r) => (
                              <tr key={r.entry_id} className="border-t border-gray-200">
                                <td className="py-1 pr-3 text-gray-900">{r.name}</td>
                                <td className="py-1 pr-3 text-gray-500">
                                  {r.employee_code || "—"}
                                </td>
                                <td className="py-1 pr-3 text-gray-500">
                                  {incomeTypeKo(r.income_type)}
                                </td>
                                <td className="py-1 pr-3 text-right text-gray-900">
                                  {r.total_amount.toLocaleString()}
                                </td>
                                <td className="py-1 pr-3 text-right text-gray-500">
                                  {r.non_taxable.toLocaleString()}
                                </td>
                                <td className="py-1 pr-3 text-right text-gray-500">
                                  {r.taxable.toLocaleString()}
                                </td>
                                <td className="py-1 pr-3 text-right text-gray-500">
                                  {r.income_tax.toLocaleString()}
                                </td>
                                <td className="py-1 text-right text-gray-500">
                                  {r.local_tax.toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <div className="mt-2 text-right">
                          <Link
                            href={`/dashboard/filings/${p.filing_id}`}
                            className="text-xs text-blue-600 hover:underline"
                          >
                            {koreanPeriod(p.period)} 신고 화면으로 이동 →
                          </Link>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function FilingStatusBadge({ status }: { status: string }) {
  const label = {
    DRAFT: "준비",
    COLLECTING: "수집중",
    REVIEWING: "검증중",
    APPROVED: "승인",
    EXCEL_GENERATED: "엑셀생성",
    FILED: "신고완료",
    COMPLETED: "완료",
  }[status];
  if (status === "FILED" || status === "COMPLETED")
    return <Badge tone="success">{label}</Badge>;
  if (status === "DRAFT") return <Badge tone="neutral">{label}</Badge>;
  return <Badge tone="info">{label ?? status}</Badge>;
}

function incomeTypeKo(t: string): string {
  return (
    {
      WAGE: "근로",
      BUSINESS: "사업",
      OTHER: "기타",
      DAILY: "일용",
      RETIREMENT: "퇴직",
    }[t] ?? t
  );
}
