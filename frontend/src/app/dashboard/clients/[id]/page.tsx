"use client";

import { use, useRef, useState } from "react";
import Link from "next/link";

import {
  useClientDetail,
  useClientEmployees,
  useImportEmployees,
  useImportPayroll,
  useSendClientInvite,
  useUpdateClient,
} from "@/lib/queries";
import { Badge, Button, Card, Input, Modal } from "@/components/ui";
import { digitsOnly, formatBizNumber, formatPhone } from "@/lib/format";
import type {
  Client,
  ClientInviteResult,
  ImportEmployeeResult,
  ImportPayrollResult,
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
  const sendInvite = useSendClientInvite(id);

  const empFileRef = useRef<HTMLInputElement>(null);
  const payFileRef = useRef<HTMLInputElement>(null);
  const [payPeriod, setPayPeriod] = useState("2026-03");
  const [empResult, setEmpResult] = useState<ImportEmployeeResult | null>(null);
  const [payResult, setPayResult] = useState<ImportPayrollResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [inviteResult, setInviteResult] = useState<ClientInviteResult | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);

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
              연락처 편집
            </Button>
            <Button
              onClick={async () => {
                setInviteError(null);
                setInviteResult(null);
                try {
                  const res = await sendInvite.mutateAsync();
                  setInviteResult(res);
                } catch (err) {
                  setInviteError((err as Error).message);
                }
              }}
              disabled={
                sendInvite.isPending ||
                (!client.contact_phone && !client.contact_email)
              }
            >
              {sendInvite.isPending ? "발송 중..." : "초대장 발송"}
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
        {inviteResult && <InviteResultBanner result={inviteResult} />}
        {inviteError && (
          <p className="mt-3 text-sm text-red-600">{inviteError}</p>
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

function InviteResultBanner({ result }: { result: ClientInviteResult }) {
  const stubChannels = result.channels.filter((c) => c.endsWith("_stub"));
  const realChannels = result.channels.filter((c) => !c.endsWith("_stub"));
  const allStub = stubChannels.length > 0 && realChannels.length === 0;
  const failedAttempts = (result.attempts ?? []).filter(
    (a) => !a.accepted && a.channel !== "alimtalk_skipped",
  );

  return (
    <div className="mt-3 space-y-2">
      {result.sent && realChannels.length > 0 && (
        <div className="text-sm text-green-700">
          ✅ {result.filing_period} 초대장 발송 완료 ({realChannels.join(", ")})
        </div>
      )}

      {result.sent && allStub && (
        <div className="p-3 rounded-md bg-amber-50 border border-amber-200 text-sm">
          <p className="font-medium text-amber-800">
            ⚠️ 테스트 모드 — 실제로 발송되지 않았습니다
          </p>
          <p className="text-xs text-amber-700 mt-1">
            성공한 채널: {stubChannels.join(", ")}
          </p>
        </div>
      )}

      {!result.sent && (
        <div className="text-sm text-amber-700">
          ⚠️ 발송 실패 — {result.detail ?? "알 수 없는 오류"}
        </div>
      )}

      {failedAttempts.length > 0 && (
        <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm">
          <p className="font-medium text-red-800 mb-1">
            실패/스킵된 채널 ({failedAttempts.length}건):
          </p>
          <ul className="text-xs text-red-700 space-y-0.5">
            {failedAttempts.map((a, i) => (
              <li key={i}>
                <code className="font-mono">{a.channel}</code>
                {a.error ? ` — ${a.error}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
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
  const [phone, setPhone] = useState(digitsOnly(client.contact_phone ?? ""));
  const [email, setEmail] = useState(client.contact_email ?? "");
  const [err, setErr] = useState<string | null>(null);

  return (
    <Modal
      open={true}
      onClose={onClose}
      title="거래처 연락처 편집"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            취소
          </Button>
          <Button
            onClick={async () => {
              setErr(null);
              try {
                await onSubmit({
                  contact_phone: digitsOnly(phone) || null,
                  contact_email: email.trim() || null,
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
            전화번호 (휴대폰)
          </label>
          <Input
            type="tel"
            placeholder="010-1234-5678"
            value={formatPhone(phone)}
            onChange={(e) => setPhone(digitsOnly(e.target.value))}
          />
          <p className="text-xs text-gray-400 mt-1">
            알림톡·SMS 발송에 사용됩니다.
          </p>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">이메일</label>
          <Input
            type="email"
            placeholder="contact@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-1">
            초대장 이메일이 이 주소로 발송됩니다.
          </p>
        </div>
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}
