"use client";

import { use, useRef, useState } from "react";
import Link from "next/link";

import {
  useClientDetail,
  useClientEmployees,
  useImportEmployees,
  useImportPayroll,
} from "@/lib/queries";
import { Badge, Button, Card } from "@/components/ui";
import type { ImportEmployeeResult, ImportPayrollResult } from "@/lib/types";

export default function ClientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: client, isLoading } = useClientDetail(id);
  const { data: employees } = useClientEmployees(id);
  const importEmp = useImportEmployees(id);
  const importPay = useImportPayroll(id);

  const empFileRef = useRef<HTMLInputElement>(null);
  const payFileRef = useRef<HTMLInputElement>(null);
  const [payPeriod, setPayPeriod] = useState("2026-03");
  const [empResult, setEmpResult] = useState<ImportEmployeeResult | null>(null);
  const [payResult, setPayResult] = useState<ImportPayrollResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (isLoading || !client) return <p className="p-6">로딩 중...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/dashboard/clients" className="hover:underline">
          거래처 관리
        </Link>
        <span>/</span>
        <span>{client.business_name}</span>
      </div>

      <Card>
        <h1 className="text-2xl font-semibold mb-2">{client.business_name}</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <span className="text-gray-500">사업자번호</span>
            <p>{client.business_number || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">대표자</span>
            <p>{client.representative || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">연락처</span>
            <p>{client.contact_phone || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">이메일</span>
            <p>{client.contact_email || "—"}</p>
          </div>
        </div>
        {client.collect_email && (
          <div className="mt-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
            <p className="text-xs text-gray-500 mb-1">전용 수신 이메일 (거래처 안내용)</p>
            <p className="font-mono text-sm text-blue-700 dark:text-blue-300">
              {client.collect_email}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {client.invite_sent ? "✅ 초대장 발송 완료" : "⏳ 초대장 미발송"}
            </p>
          </div>
        )}
      </Card>

      {/* Import Section */}
      <Card>
        <h2 className="text-lg font-semibold mb-3">데이터 임포트</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Employee Import */}
          <div className="space-y-2 p-4 rounded-lg border border-gray-200 dark:border-gray-800">
            <h3 className="font-medium">직원 마스터 업로드</h3>
            <p className="text-xs text-gray-500">
              위하고T 인적사항 엑셀 또는 자유 양식 (.xlsx, .csv)
            </p>
            <input
              ref={empFileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setError(null);
                setEmpResult(null);
                try {
                  const res = await importEmp.mutateAsync(f);
                  setEmpResult(res);
                } catch (err) {
                  setError((err as Error).message);
                }
                e.target.value = "";
              }}
            />
            <Button
              variant="secondary"
              onClick={() => empFileRef.current?.click()}
              disabled={importEmp.isPending}
            >
              {importEmp.isPending ? "업로드 중..." : "파일 선택 + 업로드"}
            </Button>
            {empResult && (
              <div className="text-xs mt-2 p-2 rounded bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-300">
                <p>
                  총 {empResult.total_rows}행 처리 — 생성 {empResult.created},
                  업데이트 {empResult.updated}, 건너뜀 {empResult.skipped}
                </p>
                {empResult.errors.length > 0 && (
                  <ul className="mt-1 text-amber-700 dark:text-amber-400">
                    {empResult.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Payroll Import */}
          <div className="space-y-2 p-4 rounded-lg border border-gray-200 dark:border-gray-800">
            <h3 className="font-medium">전월 급여 업로드</h3>
            <p className="text-xs text-gray-500">
              위하고T 원천징수이행상황신고서 엑셀 (.xlsx, .csv)
            </p>
            <div className="flex gap-2 items-end">
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  지급년월
                </label>
                <input
                  type="month"
                  value={payPeriod}
                  onChange={(e) => setPayPeriod(e.target.value)}
                  className="rounded border border-gray-300 dark:border-gray-700 bg-transparent px-2 py-1 text-sm"
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
                    const res = await importPay.mutateAsync({
                      file: f,
                      period: payPeriod,
                    });
                    setPayResult(res);
                  } catch (err) {
                    setError((err as Error).message);
                  }
                  e.target.value = "";
                }}
              />
              <Button
                variant="secondary"
                onClick={() => payFileRef.current?.click()}
                disabled={importPay.isPending}
              >
                {importPay.isPending ? "업로드 중..." : "파일 선택 + 업로드"}
              </Button>
            </div>
            {payResult && (
              <div className="text-xs mt-2 p-2 rounded bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-300">
                <p>
                  {payResult.period} — 총 {payResult.total_rows}행, 매칭{" "}
                  {payResult.matched}, 미매칭 {payResult.unmatched}, 생성{" "}
                  {payResult.created_entries}건
                </p>
                {payResult.errors.length > 0 && (
                  <ul className="mt-1 text-amber-700 dark:text-amber-400">
                    {payResult.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
        {error && (
          <p className="text-sm text-red-600 mt-3">{error}</p>
        )}
      </Card>

      {/* Employee List */}
      <Card>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold">
            직원 목록 ({employees?.length ?? 0}명)
          </h2>
        </div>
        {employees && employees.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-500 border-b border-gray-200 dark:border-gray-800">
                <tr>
                  <th className="text-left py-2 pr-3">이름</th>
                  <th className="text-left py-2 pr-3">사번</th>
                  <th className="text-left py-2 pr-3">주민번호</th>
                  <th className="text-left py-2 pr-3">입사일</th>
                  <th className="text-left py-2 pr-3">퇴사일</th>
                  <th className="text-left py-2">상태</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((e) => (
                  <tr
                    key={e.id}
                    className="border-b border-gray-100 dark:border-gray-900"
                  >
                    <td className="py-2 pr-3 font-medium">{e.name}</td>
                    <td className="py-2 pr-3 text-gray-500">
                      {e.employee_code || "—"}
                    </td>
                    <td className="py-2 pr-3 text-gray-500">
                      {e.rrn_last4 ? `******-*${e.rrn_last4}` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-gray-500">
                      {e.hired_at || "—"}
                    </td>
                    <td className="py-2 pr-3 text-gray-500">
                      {e.resigned_at || "—"}
                    </td>
                    <td className="py-2">
                      <StatusBadge status={e.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            등록된 직원이 없습니다. 위에서 직원 마스터를 업로드하세요.
          </p>
        )}
      </Card>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ACTIVE") return <Badge tone="success">재직</Badge>;
  if (status === "RESIGNED") return <Badge tone="danger">퇴사</Badge>;
  return <Badge tone="warning">대기</Badge>;
}
