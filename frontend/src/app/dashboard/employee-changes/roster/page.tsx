"use client";

// 사원 목록 — 거래처정보 상세에 있던 "직원 마스터 업로드"·"소득지급자 목록"과
// 거래처정보 목록에 있던 "위하고에서 가져오기"를 이 메뉴로 옮겼다 (2026-10-01).

import { useRef, useState } from "react";
import Link from "next/link";

import { useBusinessTypeCodes, useClientEmployees, useCreateEmployee, useImportEmployees, useUpdateEmployee } from "@/lib/queries";
import { Badge, Button, Card, Chip, Modal } from "@/components/ui";
import { ClientPicker, useSelectedClientId } from "@/components/clients/client-picker";
import { WehagoImportModal } from "@/components/rpa/wehago-import-modal";
import type { Employee, ImportEmployeeResult } from "@/lib/types";

const INCOME_TYPE_TABS = ["WAGE", "BUSINESS", "OTHER", "DAILY"] as const;

export default function EmployeeRosterPage() {
  const { clientId, setClientId, loading } = useSelectedClientId();
  const [wehagoOpen, setWehagoOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight text-gray-900">사원 목록</h1>
          <p className="text-[12px] text-gray-500 mt-1">거래처를 고르면 직원 마스터와 소득지급자 목록을 관리할 수 있습니다.</p>
        </div>
        <div className="flex gap-2 items-center">
          <ClientPicker value={clientId} onChange={setClientId} />
          <Button variant="secondary" onClick={() => setWehagoOpen(true)} disabled={!clientId}>
            위하고에서 가져오기
          </Button>
        </div>
      </div>

      {!loading && !clientId && (
        <Card className="text-center py-12">
          <p className="text-[13px] text-gray-500">등록된 거래처가 없습니다. 거래처정보에서 먼저 추가하세요.</p>
        </Card>
      )}

      {clientId && <RosterContent clientId={clientId} />}

      {wehagoOpen && <WehagoImportModal onClose={() => setWehagoOpen(false)} />}
    </div>
  );
}

function RosterContent({ clientId }: { clientId: string }) {
  const { data: employees } = useClientEmployees(clientId);
  const importEmp = useImportEmployees(clientId);
  const empFileRef = useRef<HTMLInputElement>(null);
  const [empResult, setEmpResult] = useState<ImportEmployeeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [addingEmployee, setAddingEmployee] = useState(false);
  const [incomeTab, setIncomeTab] = useState<string>("WAGE");

  return (
    <div className="space-y-6">
      <Link href={`/dashboard/clients/${clientId}`} className="text-[12px] text-blue-600 hover:underline">
        ← 거래처정보로 돌아가기
      </Link>

      {/* 직원 마스터 업로드 */}
      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">직원 마스터 업로드</h2>
        <div className="space-y-2 p-4 rounded-lg border border-gray-300">
          <p className="text-xs text-gray-500">위하고T 인적사항 엑셀 또는 자유 양식 (.xlsx, .csv)</p>
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
          <Button variant="secondary" onClick={() => empFileRef.current?.click()} disabled={importEmp.isPending}>
            {importEmp.isPending ? "업로드 중..." : "파일 선택 + 업로드"}
          </Button>
          {empResult && (
            <div className="text-xs mt-2 p-2 rounded bg-green-50 text-green-800">
              <p>
                총 {empResult.total_rows}행 처리 — 생성 {empResult.created}, 업데이트 {empResult.updated}, 건너뜀{" "}
                {empResult.skipped}
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
          {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
        </div>
      </Card>

      {/* 소득지급자 목록 */}
      <Card>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">소득지급자 목록 ({employees?.length ?? 0}명)</h2>
          <Button variant="secondary" className="!text-[12px] !px-2.5 !py-1" onClick={() => setAddingEmployee(true)}>
            + 추가
          </Button>
        </div>
        <div className="flex gap-1.5 mb-3">
          {INCOME_TYPE_TABS.map((t) => {
            const count = employees?.filter((e) => e.income_type === t).length ?? 0;
            return (
              <Chip key={t} active={incomeTab === t} className="cursor-pointer select-none" onClick={() => setIncomeTab(t)}>
                {incomeTypeKo(t)} {count}
              </Chip>
            );
          })}
        </div>
        {(() => {
          const filtered = employees?.filter((e) => e.income_type === incomeTab) ?? [];
          return filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-500 border-b border-gray-300">
                  <tr>
                    <th className="text-left py-2 pr-3">이름</th>
                    <th className="text-left py-2 pr-3">사번</th>
                    <th className="text-left py-2 pr-3">주민번호</th>
                    <th className="text-left py-2 pr-3">입사일</th>
                    <th className="text-left py-2 pr-3">퇴사일</th>
                    <th className="text-left py-2 pr-3">상태</th>
                    <th className="text-right py-2">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((e) => (
                    <tr key={e.id} className="border-b border-gray-100">
                      <td className="py-2 pr-3 font-medium text-gray-900">
                        {e.name}
                        {e.other_income_types.length > 0 && (
                          <span
                            className="ml-1.5 inline-block px-1.5 py-0.5 rounded text-[10.5px] font-normal bg-blue-50 text-blue-600"
                            title="주민번호가 같은 다른 소득유형 행이 있습니다 — 같은 사람일 수 있습니다"
                          >
                            동일인: {e.other_income_types.map(incomeTypeKo).join("·")}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">{e.employee_code || "—"}</td>
                      <td className="py-2 pr-3 text-gray-500">{e.rrn_last4 ? `******-*${e.rrn_last4}` : "—"}</td>
                      <td className="py-2 pr-3 text-gray-500">{e.hired_at || "—"}</td>
                      <td className="py-2 pr-3 text-gray-500">{e.resigned_at || "—"}</td>
                      <td className="py-2 pr-3">
                        <StatusBadge status={e.status} />
                      </td>
                      <td className="py-2 text-right">
                        <Button variant="ghost" className="!text-[12px] !px-2 !py-0.5" onClick={() => setEditingEmployee(e)}>
                          수정
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              {employees && employees.length > 0
                ? `${incomeTypeKo(incomeTab)}소득 지급자가 없습니다.`
                : "등록된 직원이 없습니다. 위에서 직원 마스터를 업로드하세요."}
            </p>
          );
        })()}
      </Card>

      {editingEmployee && (
        <EmployeeEditModal clientId={clientId} employee={editingEmployee} onClose={() => setEditingEmployee(null)} />
      )}
      {addingEmployee && (
        <EmployeeCreateModal clientId={clientId} incomeType={incomeTab} onClose={() => setAddingEmployee(false)} />
      )}
    </div>
  );
}

/* ─── 사업소득 업종코드(소득구분코드) 선택 — 위하고 T 사업소득자등록 화면과 같은 코드 체계
   (국세청 간이지급명세서 업종코드 40종, BUSINESS_TYPE_CODES). income_type이 BUSINESS일 때만 보인다. ─── */

function BusinessTypeCodeField({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (code: string) => void;
  className: string;
}) {
  const { data: codes = [] } = useBusinessTypeCodes();
  return (
    <label className="space-y-1">업종코드 (소득구분)
      <select className={className} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">선택 안 함</option>
        {codes.map((c) => (
          <option key={c.code} value={c.code}>{c.code} {c.name}</option>
        ))}
      </select>
    </label>
  );
}

/* ─── 직원 정보 수정 ─── */

function EmployeeEditModal({ clientId, employee, onClose }: { clientId: string; employee: Employee; onClose: () => void }) {
  const update = useUpdateEmployee(clientId);
  const [form, setForm] = useState({
    name: employee.name,
    employee_code: employee.employee_code ?? "",
    department: employee.department ?? "",
    position: employee.position ?? "",
    job_type: employee.job_type ?? "",
    hired_at: employee.hired_at ?? "",
    resigned_at: employee.resigned_at ?? "",
    income_type: employee.income_type,
    business_type_code: employee.business_type_code ?? "",
    dependents_count: String(employee.dependents_count),
    children_count: String(employee.children_count),
    withholding_rate_adjust: String(employee.withholding_rate_adjust),
  });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const code = form.employee_code.trim();
  const nonNumeric = code !== "" && !/^\d+$/.test(code);
  const rehired = Boolean(employee.resigned_at) && !form.resigned_at;

  async function save() {
    setError(null);
    try {
      await update.mutateAsync({
        id: employee.id,
        patch: {
          name: form.name.trim(),
          employee_code: code,
          department: form.department.trim() || null,
          position: form.position.trim() || null,
          job_type: form.job_type.trim() || null,
          hired_at: form.hired_at || null,
          resigned_at: form.resigned_at || null,
          income_type: form.income_type,
          business_type_code: form.income_type === "BUSINESS" ? (form.business_type_code || null) : null,
          dependents_count: Math.max(1, Number(form.dependents_count) || 1),
          children_count: Math.max(0, Number(form.children_count) || 0),
          withholding_rate_adjust: Number(form.withholding_rate_adjust) || 100,
        },
      });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const field = "w-full rounded-lg border border-gray-300 px-3 py-1.5 text-[13px] outline-none focus:border-blue-500";
  return (
    <Modal open={true} onClose={onClose} title={`직원 정보 수정 — ${employee.name}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button onClick={save} disabled={!form.name.trim() || update.isPending}>{update.isPending ? "저장 중..." : "저장"}</Button>
      </>}>
      <div className="grid grid-cols-2 gap-3 text-[12px] text-gray-600">
        <label className="space-y-1">이름<input className={field} value={form.name} onChange={set("name")} /></label>
        <label className="space-y-1">사원코드 (위하고와 같게)
          <input className={field} value={form.employee_code} onChange={set("employee_code")} placeholder="비우면 다음 번호" inputMode="numeric" />
        </label>
        <label className="space-y-1">소득구분
          <select className={field} value={form.income_type} onChange={set("income_type")}>
            {INCOME_TYPE_TABS.map((t) => (
              <option key={t} value={t}>{incomeTypeKo(t)}</option>
            ))}
            <option value="RETIREMENT">퇴직</option>
          </select>
        </label>
        {form.income_type === "BUSINESS" && (
          <BusinessTypeCodeField
            value={form.business_type_code}
            onChange={(code) => setForm((f) => ({ ...f, business_type_code: code }))}
            className={field}
          />
        )}
        <label className="space-y-1">부서<input className={field} value={form.department} onChange={set("department")} /></label>
        <label className="space-y-1">직급<input className={field} value={form.position} onChange={set("position")} /></label>
        <label className="space-y-1">직종<input className={field} value={form.job_type} onChange={set("job_type")} /></label>
        <label className="space-y-1">입사일<input type="date" className={field} value={form.hired_at} onChange={set("hired_at")} /></label>
        <label className="space-y-1">퇴사일<input type="date" className={field} value={form.resigned_at} onChange={set("resigned_at")} /></label>
      </div>
      <details className="mt-3 rounded-lg border border-gray-200 px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-medium text-gray-700">
          소득세 계산 설정 (대부분 기본값 그대로 두면 됩니다)
        </summary>
        <div className="mt-2 grid grid-cols-3 gap-3 text-[12px] text-gray-600">
          <label className="space-y-1">부양가족수 (본인 포함)
            <input type="number" min={1} className={field} value={form.dependents_count} onChange={set("dependents_count")} />
          </label>
          <label className="space-y-1">8~20세 자녀수
            <input type="number" min={0} className={field} value={form.children_count} onChange={set("children_count")} />
          </label>
          <label className="space-y-1">원천징수 조정율
            <select className={field} value={form.withholding_rate_adjust} onChange={set("withholding_rate_adjust")}>
              <option value="80">80%</option>
              <option value="100">100% (기본)</option>
              <option value="120">120%</option>
            </select>
          </label>
        </div>
      </details>
      {nonNumeric && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          사원코드에 숫자가 아닌 글자가 있습니다. 위하고 사원코드는 보통 숫자(1, 2, 3…)라서, 다르면 위하고 전송이 멈춥니다.
        </p>
      )}
      {rehired && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          퇴사일을 지워 재직으로 되돌렸습니다. 위하고 T는 재입사자에게 옛 사원코드가 아닌 <strong>새 사원코드</strong>를
          주는 것이 원칙입니다 — 위하고 사원등록에서도 이 직원을 새 코드로 등록한 뒤, 여기 사원코드도 그 번호로 바꿔주세요.
          코드가 다르면 위하고 전송이 안전하게 멈추고 알려드립니다.
        </p>
      )}
      <p className="mt-3 text-[11.5px] text-gray-500">주민번호는 여기서 바꾸지 않습니다.</p>
      {error && <p className="mt-2 text-[12px] text-red-600">{error}</p>}
    </Modal>
  );
}

/* ─── 소득지급자 추가 — 사원코드: 위하고 명단을 그대로 옮기는 게 아니라 직접 한 명 등록하는
   경우라 사용자가 입력하고, 비우면 거래처의 다음 번호가 자동으로 붙는다 (규칙은 백엔드
   create_employee와 동일, services/employee_codes.py 참고). ─── */

function EmployeeCreateModal({ clientId, incomeType, onClose }: { clientId: string; incomeType: string; onClose: () => void }) {
  const create = useCreateEmployee(clientId);
  const [form, setForm] = useState({
    name: "",
    employee_code: "",
    rrn: "",
    department: "",
    position: "",
    job_type: "",
    hired_at: "",
    income_type: (INCOME_TYPE_TABS as readonly string[]).includes(incomeType) ? incomeType : "WAGE",
    business_type_code: "",
    dependents_count: "1",
    children_count: "0",
    withholding_rate_adjust: "100",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const code = form.employee_code.trim();
  const nonNumeric = code !== "" && !/^\d+$/.test(code);

  async function save() {
    setError(null);
    try {
      await create.mutateAsync({
        name: form.name.trim(),
        employee_code: code,
        rrn: form.rrn.trim() || null,
        department: form.department.trim() || null,
        position: form.position.trim() || null,
        job_type: form.job_type.trim() || null,
        hired_at: form.hired_at || null,
        income_type: form.income_type,
        business_type_code: form.income_type === "BUSINESS" ? (form.business_type_code || null) : null,
        dependents_count: Math.max(1, Number(form.dependents_count) || 1),
        children_count: Math.max(0, Number(form.children_count) || 0),
        withholding_rate_adjust: Number(form.withholding_rate_adjust) || 100,
      });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const field = "w-full rounded-lg border border-gray-300 px-3 py-1.5 text-[13px] outline-none focus:border-blue-500";
  return (
    <Modal open={true} onClose={onClose} title="소득지급자 추가"
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button onClick={save} disabled={!form.name.trim() || create.isPending}>{create.isPending ? "추가 중..." : "추가"}</Button>
      </>}>
      <div className="grid grid-cols-2 gap-3 text-[12px] text-gray-600">
        <label className="space-y-1">이름<input className={field} value={form.name} onChange={set("name")} /></label>
        <label className="space-y-1">사원코드 (위하고와 같게)
          <input className={field} value={form.employee_code} onChange={set("employee_code")} placeholder="비우면 다음 번호" inputMode="numeric" />
        </label>
        <label className="space-y-1">소득구분
          <select className={field} value={form.income_type} onChange={set("income_type")}>
            {INCOME_TYPE_TABS.map((t) => (
              <option key={t} value={t}>{incomeTypeKo(t)}</option>
            ))}
            <option value="RETIREMENT">퇴직</option>
          </select>
        </label>
        {form.income_type === "BUSINESS" && (
          <BusinessTypeCodeField
            value={form.business_type_code}
            onChange={(code) => setForm((f) => ({ ...f, business_type_code: code }))}
            className={field}
          />
        )}
        <label className="space-y-1">주민번호 (선택, 나중에 입력 가능)
          <input className={field} value={form.rrn} onChange={set("rrn")} placeholder="900101-1234567" />
        </label>
        <label className="space-y-1">부서<input className={field} value={form.department} onChange={set("department")} /></label>
        <label className="space-y-1">직급<input className={field} value={form.position} onChange={set("position")} /></label>
        <label className="space-y-1">직종<input className={field} value={form.job_type} onChange={set("job_type")} /></label>
        <label className="space-y-1">입사일<input type="date" className={field} value={form.hired_at} onChange={set("hired_at")} /></label>
      </div>
      <details className="mt-3 rounded-lg border border-gray-200 px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-medium text-gray-700">
          소득세 계산 설정 (대부분 기본값 그대로 두면 됩니다)
        </summary>
        <div className="mt-2 grid grid-cols-3 gap-3 text-[12px] text-gray-600">
          <label className="space-y-1">부양가족수 (본인 포함)
            <input type="number" min={1} className={field} value={form.dependents_count} onChange={set("dependents_count")} />
          </label>
          <label className="space-y-1">8~20세 자녀수
            <input type="number" min={0} className={field} value={form.children_count} onChange={set("children_count")} />
          </label>
          <label className="space-y-1">원천징수 조정율
            <select className={field} value={form.withholding_rate_adjust} onChange={set("withholding_rate_adjust")}>
              <option value="80">80%</option>
              <option value="100">100% (기본)</option>
              <option value="120">120%</option>
            </select>
          </label>
        </div>
      </details>
      {nonNumeric && (
        <p className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[12px] text-amber-800">
          사원코드에 숫자가 아닌 글자가 있습니다. 위하고 사원코드는 보통 숫자(1, 2, 3…)라서, 다르면 위하고 전송이 멈춥니다.
        </p>
      )}
      {error && <p className="mt-2 text-[12px] text-red-600">{error}</p>}
    </Modal>
  );
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

function StatusBadge({ status }: { status: string }) {
  if (status === "ACTIVE") return <Badge tone="success">재직</Badge>;
  if (status === "RESIGNED") return <Badge tone="danger">퇴사</Badge>;
  return <Badge tone="warning">대기</Badge>;
}
