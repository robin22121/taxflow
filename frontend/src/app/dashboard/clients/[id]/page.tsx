"use client";

import { use, useRef, useState } from "react";
import Link from "next/link";

import {
  useClientDetail,
  useClientEmployees,
  useImportEmployees,
  useImportPayroll,
  usePayrollDefault,
  useResetPayrollDefault,
  useUpdateClient,
  useUpdatePayrollDefault,
} from "@/lib/queries";
import { Badge, Button, Card, Input, Modal } from "@/components/ui";
import { digitsOnly, formatBizNumber, formatPhone } from "@/lib/format";
import type {
  Client,
  ImportEmployeeResult,
  ImportPayrollResult,
  PayrollDefault,
  PayrollDefaultPatch,
} from "@/lib/types";

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
  const updateClient = useUpdateClient(id);

  const empFileRef = useRef<HTMLInputElement>(null);
  const payFileRef = useRef<HTMLInputElement>(null);
  const [payPeriod, setPayPeriod] = useState("2026-03");
  const [empResult, setEmpResult] = useState<ImportEmployeeResult | null>(null);
  const [payResult, setPayResult] = useState<ImportPayrollResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading || !client) return <p className="p-6 text-gray-900">로딩 중...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/dashboard/clients" className="hover:underline">
          거래처 관리
        </Link>
        <span>/</span>
        <span className="text-gray-900">{client.business_name}</span>
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-2">
          <h1 className="text-2xl font-semibold text-gray-900">{client.business_name}</h1>
          <div className="flex gap-2 shrink-0">
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              편집
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <span className="text-gray-500">사업자번호</span>
            <p className="text-gray-900">{client.business_number ? formatBizNumber(client.business_number) : "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">대표자</span>
            <p className="text-gray-900">{client.representative || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">연락처</span>
            <p className="text-gray-900">{client.contact_phone ? formatPhone(client.contact_phone) : "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">이메일</span>
            <p className="text-gray-900">{client.contact_email || "—"}</p>
          </div>
        </div>
        {client.collect_email && (
          <div className="mt-3 p-3 rounded-lg bg-blue-50/30 border border-blue-600/20">
            <p className="text-xs text-gray-500 mb-1">전용 수신 이메일 (거래처 안내용)</p>
            <p className="font-mono text-sm text-blue-600">
              {client.collect_email}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {client.invite_sent ? "✅ 초대장 발송 완료" : "⏳ 초대장 미발송"}
            </p>
          </div>
        )}
      </Card>

      {editOpen && (
        <ClientEditModal
          client={client}
          onClose={() => setEditOpen(false)}
          onSubmit={async (patch) => {
            await updateClient.mutateAsync(patch);
            setEditOpen(false);
          }}
          pending={updateClient.isPending}
        />
      )}

      {/* Import Section */}
      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">데이터 임포트</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Employee Import */}
          <div className="space-y-2 p-4 rounded-lg border border-gray-300">
            <h3 className="font-medium text-gray-900">직원 마스터 업로드</h3>
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
              <div className="text-xs mt-2 p-2 rounded bg-green-50 text-green-800">
                <p>
                  총 {empResult.total_rows}행 처리 — 생성 {empResult.created},
                  업데이트 {empResult.updated}, 건너뜀 {empResult.skipped}
                </p>
                {empResult.errors.length > 0 && (
                  <ul className="mt-1 text-amber-700">
                    {empResult.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Payroll Import */}
          <div className="space-y-2 p-4 rounded-lg border border-gray-300">
            <h3 className="font-medium text-gray-900">전월 급여 업로드</h3>
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
              <div className="text-xs mt-2 p-2 rounded bg-green-50 text-green-800">
                <p>
                  {payResult.period} — 총 {payResult.total_rows}행, 매칭{" "}
                  {payResult.matched}, 미매칭 {payResult.unmatched}, 생성{" "}
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
          </div>
        </div>
        {error && (
          <p className="text-sm text-red-600 mt-3">{error}</p>
        )}
      </Card>

      {/* Payroll Defaults — 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8) */}
      <PayrollDefaultSection clientId={id} />

      {/* Employee List */}
      <Card>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">
            직원 목록 ({employees?.length ?? 0}명)
          </h2>
        </div>
        {employees && employees.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-500 border-b border-gray-300">
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
                    className="border-b border-gray-100"
                  >
                    <td className="py-2 pr-3 font-medium text-gray-900">{e.name}</td>
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

/* ─── 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8) ─── */

function PayrollDefaultSection({ clientId }: { clientId: string }) {
  const { data, isLoading } = usePayrollDefault(clientId);
  const update = useUpdatePayrollDefault(clientId);
  const reset = useResetPayrollDefault(clientId);

  if (isLoading || !data) {
    return (
      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">기본 세팅</h2>
        <p className="text-sm text-gray-500">로딩 중...</p>
      </Card>
    );
  }
  // 서버 데이터가 갱신되면 key 변경으로 editor를 remount하여 폼 상태 재초기화.
  // setState-in-effect 안티패턴 회피.
  const dataKey = [
    data.meal_default, data.car_default, data.childcare_default,
    data.apply_national_pension, data.apply_health_insurance,
    data.apply_employment_insurance, data.apply_longterm_care,
    data.nps_rate_percent, data.hi_rate_percent, data.ltc_rate_percent, data.ei_rate_percent,
    data.note ?? "",
  ].join("|");

  return (
    <PayrollDefaultEditor
      key={dataKey}
      data={data}
      onSave={(patch) => update.mutateAsync(patch)}
      onReset={() => {
        if (window.confirm("시스템 기본값(비과세 한도 + 현행 요율)으로 리셋하시겠습니까?")) {
          reset.mutate();
        }
      }}
      saving={update.isPending}
      resetting={reset.isPending}
    />
  );
}

function PayrollDefaultEditor({
  data,
  onSave,
  onReset,
  saving,
  resetting,
}: {
  data: PayrollDefault;
  onSave: (patch: PayrollDefaultPatch) => Promise<unknown>;
  onReset: () => void;
  saving: boolean;
  resetting: boolean;
}) {
  // key-remount 패턴: data가 바뀌면 이 컴포넌트가 새로 마운트되어 초기값으로 form이 셋업됨.
  const [form, setForm] = useState<PayrollDefault>(data);

  function patchField<K extends keyof PayrollDefault>(key: K, value: PayrollDefault[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function diff(): PayrollDefaultPatch {
    const patch: PayrollDefaultPatch = {};
    (Object.keys(form) as (keyof PayrollDefault)[]).forEach((k) => {
      if (k.startsWith("system_")) return;
      if (form[k] !== data[k]) {
        (patch as Record<string, unknown>)[k] = form[k];
      }
    });
    return patch;
  }

  async function handleSave() {
    const patch = diff();
    if (Object.keys(patch).length === 0) return;
    await onSave(patch);
  }

  const dirty = Object.keys(diff()).length > 0;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">기본 세팅</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            거래처의 지급항목·4대보험 기본값. 매월 원시파일에 값이 명시되지 않으면 이 값이 적용됩니다.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="ghost" onClick={onReset} disabled={resetting || saving}>
            {resetting ? "리셋 중..." : "시스템 기본값으로 리셋"}
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!dirty || saving}>
            {saving ? "저장 중..." : "저장"}
          </Button>
        </div>
      </div>

      {/* 비과세 지급항목 */}
      <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-900 mb-2">비과세 지급항목 기본금액</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <AmountField
            label="식대"
            value={form.meal_default}
            onChange={(v) => patchField("meal_default", v)}
            hint="세법상 비과세 한도 200,000원"
          />
          <AmountField
            label="자가운전보조금"
            value={form.car_default}
            onChange={(v) => patchField("car_default", v)}
            hint="세법상 비과세 한도 200,000원"
          />
          <AmountField
            label="육아수당"
            value={form.childcare_default}
            onChange={(v) => patchField("childcare_default", v)}
            hint="기본 0원 (비과세 한도 200,000원)"
          />
        </div>
      </div>

      {/* 4대보험 */}
      <div className="mt-5">
        <h3 className="text-sm font-medium text-gray-900 mb-2">4대보험 적용</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <InsuranceRow
            label="국민연금"
            applied={form.apply_national_pension}
            onToggle={(v) => patchField("apply_national_pension", v)}
            rate={form.nps_rate_percent}
            onRateChange={(v) => patchField("nps_rate_percent", v)}
            systemRate={data.system_nps_rate_percent}
          />
          <InsuranceRow
            label="건강보험"
            applied={form.apply_health_insurance}
            onToggle={(v) => patchField("apply_health_insurance", v)}
            rate={form.hi_rate_percent}
            onRateChange={(v) => patchField("hi_rate_percent", v)}
            systemRate={data.system_hi_rate_percent}
          />
          <InsuranceRow
            label="장기요양"
            applied={form.apply_longterm_care}
            onToggle={(v) => patchField("apply_longterm_care", v)}
            rate={form.ltc_rate_percent}
            onRateChange={(v) => patchField("ltc_rate_percent", v)}
            systemRate={data.system_ltc_rate_percent}
            rateSuffix="% (건강보험료 대비)"
          />
          <InsuranceRow
            label="고용보험"
            applied={form.apply_employment_insurance}
            onToggle={(v) => patchField("apply_employment_insurance", v)}
            rate={form.ei_rate_percent}
            onRateChange={(v) => patchField("ei_rate_percent", v)}
            systemRate={data.system_ei_rate_percent}
          />
        </div>
      </div>

      {/* 비고 */}
      <div className="mt-5">
        <label className="block text-sm font-medium text-gray-900 mb-1.5">비고</label>
        <textarea
          className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-900 min-h-[60px]"
          placeholder="두루누리 사회보험료 지원 등 메모 자유 입력"
          value={form.note ?? ""}
          onChange={(e) => patchField("note", e.target.value || null)}
          maxLength={500}
        />
      </div>
    </Card>
  );
}

function AmountField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <div className="relative">
        <input
          type="number"
          min={0}
          step={10000}
          value={value}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-1.5 pr-8 text-right tabular-nums text-sm text-gray-900"
        />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">원</span>
      </div>
      {hint && <p className="text-[11px] text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

function InsuranceRow({
  label,
  applied,
  onToggle,
  rate,
  onRateChange,
  systemRate,
  rateSuffix = "%",
}: {
  label: string;
  applied: boolean;
  onToggle: (v: boolean) => void;
  rate: number;
  onRateChange: (v: number) => void;
  systemRate: number;
  rateSuffix?: string;
}) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-gray-200">
      <label className="flex items-center gap-2 min-w-[110px] shrink-0">
        <input
          type="checkbox"
          checked={applied}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-4 w-4 accent-blue-600"
        />
        <span className="text-sm font-medium text-gray-900">{label}</span>
      </label>
      <div className="flex-1 flex items-center gap-2 justify-end">
        <input
          type="number"
          step={0.01}
          min={0}
          value={rate}
          disabled={!applied}
          onChange={(e) => onRateChange(Number(e.target.value) || 0)}
          className={`w-24 rounded-lg border border-gray-300 bg-transparent px-2 py-1 text-right tabular-nums text-sm text-gray-900 ${
            applied ? "" : "opacity-50"
          }`}
        />
        <span className="text-xs text-gray-500 whitespace-nowrap">{rateSuffix}</span>
      </div>
      <span className="text-[10.5px] text-gray-400 whitespace-nowrap min-w-[80px] text-right">
        기본 {systemRate.toFixed(rateSuffix === "%" ? 3 : 2)}%
      </span>
    </div>
  );
}


function ClientEditModal({
  client,
  onClose,
  onSubmit,
  pending,
}: {
  client: Client;
  onClose: () => void;
  onSubmit: (patch: Partial<Client>) => Promise<void>;
  pending: boolean;
}) {
  const [businessName, setBusinessName] = useState(client.business_name);
  const [businessNumber, setBusinessNumber] = useState(client.business_number ?? "");
  const [representative, setRepresentative] = useState(client.representative ?? "");
  const [phone, setPhone] = useState(digitsOnly(client.contact_phone ?? ""));
  const [email, setEmail] = useState(client.contact_email ?? "");
  const [isCorporation, setIsCorporation] = useState(client.is_corporation);
  const [err, setErr] = useState<string | null>(null);

  return (
    <Modal
      open={true}
      onClose={onClose}
      title="거래처 편집"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            취소
          </Button>
          <Button
            onClick={async () => {
              if (!businessName.trim()) {
                setErr("상호를 입력해주세요");
                return;
              }
              setErr(null);
              try {
                await onSubmit({
                  business_name: businessName.trim(),
                  business_number: digitsOnly(businessNumber) || null,
                  representative: representative.trim() || null,
                  contact_phone: digitsOnly(phone) || null,
                  contact_email: email.trim() || null,
                  is_corporation: isCorporation,
                });
              } catch (e) {
                setErr((e as Error).message);
              }
            }}
            disabled={pending}
          >
            {pending ? "저장 중..." : "저장"}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <div>
          <label className="block text-xs text-gray-500 mb-1">
            상호 <span className="text-red-600">*</span>
          </label>
          <Input
            placeholder="(주)에이상사"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">사업자번호</label>
          <Input
            placeholder="123-45-67890"
            value={formatBizNumber(businessNumber)}
            onChange={(e) => setBusinessNumber(digitsOnly(e.target.value))}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">대표자</label>
          <Input
            placeholder="홍길동"
            value={representative}
            onChange={(e) => setRepresentative(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">
            전화번호 (휴대폰)
          </label>
          <Input
            type="tel"
            placeholder="010-1234-5678"
            value={formatPhone(phone)}
            onChange={(e) => setPhone(digitsOnly(e.target.value))}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">이메일</label>
          <Input
            type="email"
            placeholder="contact@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 pt-1">
          <input
            id="edit_is_corporation"
            type="checkbox"
            checked={isCorporation}
            onChange={(e) => setIsCorporation(e.target.checked)}
            className="h-4 w-4 accent-blue-600"
          />
          <label htmlFor="edit_is_corporation" className="text-[13px] text-gray-900">
            법인 거래처
          </label>
        </div>
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}
