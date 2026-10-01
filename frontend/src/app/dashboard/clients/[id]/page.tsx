"use client";

import { Fragment, use, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  useClientArchive,
  useClientDetail,
  useClientMessages,
  useDeleteClient,
  useIssuePortalPin,
  useMe,
  usePayrollDefault,
  usePortalLink,
  usePortalPinStatus,
  useResetPayrollDefault,
  useRotatePortalLink,
  useSendClientMessage,
  useUpdateClient,
  useUpdatePayrollDefault,
  useUploadFilingDocument,
  useUpsertFilingResult,
} from "@/lib/queries";
import { Badge, Button, Card, Input, Modal } from "@/components/ui";
import { useConfirm } from "@/components/confirm-dialog";
import { digitsOnly, formatBizNumber, formatPhone, koreanPeriod } from "@/lib/format";
import type {
  ArchivePeriod,
  Client,
  PayrollDefault,
  PayrollDefaultPatch,
  VatType,
} from "@/lib/types";

const VAT_TYPE_KO: Record<VatType, string> = {
  GENERAL: "일반과세",
  SIMPLIFIED: "간이과세",
  EXEMPT: "면세",
};

export default function ClientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: me } = useMe();
  const { data: client, isLoading } = useClientDetail(id);
  const updateClient = useUpdateClient(id);

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

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
            {me?.is_admin && (
              <Button
                variant="secondary"
                className="!text-red-600 !border-red-200 hover:!bg-red-50"
                onClick={() => setDeleteOpen(true)}
              >
                삭제
              </Button>
            )}
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
          <div>
            <span className="text-gray-500">부가세 과세유형</span>
            <p className="text-gray-900">{client.vat_type ? VAT_TYPE_KO[client.vat_type] : "미지정"}</p>
          </div>
          <div>
            <span className="text-gray-500">원천세 납부</span>
            <p className="text-gray-900">{client.withholding_semiannual ? "반기납부" : "매월납부"}</p>
          </div>
          {client.is_corporation ? (
            <div>
              <span className="text-gray-500">결산월</span>
              <p className="text-gray-900">{client.fiscal_year_end_month ? `${client.fiscal_year_end_month}월` : "미지정"}</p>
            </div>
          ) : (
            <div>
              <span className="text-gray-500">성실신고</span>
              <p className="text-gray-900">{client.sincere_filing ? "대상" : "비대상"}</p>
            </div>
          )}
          <div>
            <span className="text-gray-500">업태</span>
            <p className="text-gray-900">{client.business_type || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">종목</span>
            <p className="text-gray-900">{client.business_item || "—"}</p>
          </div>
          <div>
            <span className="text-gray-500">관할세무서</span>
            <p className="text-gray-900">{client.tax_jurisdiction || "—"}</p>
          </div>
          <div className="col-span-2 md:col-span-4">
            <span className="text-gray-500">사업장 주소</span>
            <p className="text-gray-900">{client.business_address || "—"}</p>
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
      {/* 사장님 화면 — 상설 링크 + PIN (plan/12-owner-portal.md §4.3) */}
      <PortalSection clientId={id} />

      {/* 메시지 — 자료 제출 커뮤니케이션 채널 (plan/12-owner-portal.md §3.8) */}
      <MessagesSection clientId={id} />

      {/* Payroll Defaults — 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8) */}
      <PayrollDefaultSection clientId={id} />

      {/* 사원 목록·급여명세서는 사원정보 메뉴로 이관됨 (2026-10-01) — 여기선 해당 화면으로 넘어가는 링크만 둔다. */}
      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">사원·급여 정보</h2>
        <div className="flex gap-3">
          <Link
            href={`/dashboard/employee-changes/roster?client=${id}`}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-3 text-sm font-medium text-gray-900 hover:bg-gray-50"
          >
            사원정보 보기 →
          </Link>
          <Link
            href={`/dashboard/employee-changes/payroll?client=${id}`}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-3 text-sm font-medium text-gray-900 hover:bg-gray-50"
          >
            급여정보 보기 →
          </Link>
        </div>
      </Card>
      {deleteOpen && client && (
        <ClientDeleteModal
          clientId={id}
          client={client}
          onClose={() => setDeleteOpen(false)}
          onDeleted={() => router.push("/dashboard/clients")}
        />
      )}

      {/* 보관함 — 사장님 화면에 뜨는 신고 결과를 세무사가 채운다 */}
      <ArchiveSection clientId={id} />
    </div>
  );
}

/* ─── 거래처 삭제 — 세무사(사무소 관리자)만, 상호+확인 문구를 정확히 입력해야 삭제 가능 ─── */

const DELETE_CONFIRM_PHRASE = "거래처명단을 삭제합니다";

function ClientDeleteModal({
  clientId,
  client,
  onClose,
  onDeleted,
}: {
  clientId: string;
  client: Client;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const del = useDeleteClient(clientId);
  const [businessName, setBusinessName] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ready = businessName === client.business_name && confirmText === DELETE_CONFIRM_PHRASE;

  async function run() {
    setError(null);
    try {
      await del.mutateAsync({ business_name: businessName, confirm_text: confirmText });
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal open={true} onClose={onClose} title={`거래처 삭제 — ${client.business_name}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button
          className="!bg-red-600 hover:!bg-red-700"
          onClick={run}
          disabled={!ready || del.isPending}
        >
          {del.isPending ? "삭제 중..." : "영구 삭제"}
        </Button>
      </>}>
      <p className="text-[13px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
        이 거래처와 직원 명단·급여자료·신고이력·증명원 등 관련 기록이 전부 삭제됩니다.
        되돌릴 수 없습니다.
      </p>
      <label className="block mt-3 space-y-1 text-[12px] text-gray-600">
        상호 확인 — <strong className="text-gray-900">{client.business_name}</strong>를 정확히 입력하세요
        <Input value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
      </label>
      <label className="block mt-3 space-y-1 text-[12px] text-gray-600">
        &quot;{DELETE_CONFIRM_PHRASE}&quot; 를 그대로 입력하세요
        <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
      </label>
      {error && <p className="mt-2 text-[12px] text-red-600">{error}</p>}
    </Modal>
  );
}

/* ─── 보관함 — 확정세액·가상계좌·접수증 (plan/12-owner-portal.md §3.4) ─── */

function ArchiveSection({ clientId }: { clientId: string }) {
  const { data: rows, isLoading } = useClientArchive(clientId);
  const [editPeriod, setEditPeriod] = useState<string | null>(null);
  const editing = rows?.find((r) => r.period === editPeriod) ?? null;

  return (
    <Card>
      <h2 className="text-lg font-semibold text-gray-900 mb-1">보관함</h2>
      <p className="text-xs text-gray-500 mb-3">
        여기 채운 내용이 <strong>사장님 화면에 그대로</strong> 보입니다. 예상세액은 급여자료에서
        자동 계산되고, 확정세액·가상계좌·접수증은 신고 후 직접 넣으셔야 합니다.
      </p>

      {isLoading ? (
        <p className="text-sm text-gray-500">불러오는 중...</p>
      ) : !rows || rows.length === 0 ? (
        <p className="text-sm text-gray-500">
          급여자료가 있는 월이 없어 보관함이 비어 있습니다.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 border-b border-gray-300">
              <tr>
                <th className="text-left py-2 pr-3">귀속월</th>
                <th className="text-right py-2 pr-3">예상세액</th>
                <th className="text-right py-2 pr-3">확정세액</th>
                <th className="text-left py-2 pr-3">납부기한</th>
                <th className="text-left py-2 pr-3">가상계좌</th>
                <th className="text-left py-2 pr-3">접수증</th>
                <th className="text-left py-2 pr-3">납부서</th>
                <th className="text-right py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.period} className="border-b border-gray-100">
                  <td className="py-2 pr-3 font-medium text-gray-900">
                    {koreanPeriod(r.period)}
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-500 tabular-nums">
                    {r.estimated_tax.toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-900 tabular-nums">
                    {r.settled_tax === null ? "—" : r.settled_tax.toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 text-gray-700">{r.due_date || "—"}</td>
                  <td className="py-2 pr-3 text-gray-700">{r.virtual_account || "—"}</td>
                  <td className="py-2 pr-3">
                    {r.has_receipt ? <Badge tone="success">있음</Badge> : <span className="text-gray-400">—</span>}
                  </td>
                  <td className="py-2 pr-3">
                    {r.has_payment_slip ? <Badge tone="success">있음</Badge> : <span className="text-gray-400">—</span>}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => setEditPeriod(r.period)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      채우기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <ArchiveEditModal
          clientId={clientId}
          row={editing}
          onClose={() => setEditPeriod(null)}
        />
      )}
    </Card>
  );
}

function ArchiveEditModal({
  clientId,
  row,
  onClose,
}: {
  clientId: string;
  row: ArchivePeriod;
  onClose: () => void;
}) {
  const save = useUpsertFilingResult(clientId);
  const upload = useUploadFilingDocument(clientId);
  const [settledTax, setSettledTax] = useState(
    row.settled_tax === null ? "" : String(row.settled_tax),
  );
  const [dueDate, setDueDate] = useState(row.due_date ?? "");
  const [account, setAccount] = useState(row.virtual_account ?? "");
  const [epayment, setEpayment] = useState(row.epayment_number ?? "");
  const [err, setErr] = useState<string | null>(null);
  const receiptRef = useRef<HTMLInputElement>(null);
  const slipRef = useRef<HTMLInputElement>(null);

  async function pickDocument(kind: "receipt" | "payment-slip", file: File | null) {
    if (!file) return;
    setErr(null);
    try {
      await upload.mutateAsync({ period: row.period, kind, file });
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={`보관함 — ${koreanPeriod(row.period)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            닫기
          </Button>
          <Button
            disabled={save.isPending}
            onClick={async () => {
              setErr(null);
              try {
                await save.mutateAsync({
                  period: row.period,
                  patch: {
                    settled_tax: settledTax.trim() === "" ? null : Number(digitsOnly(settledTax)),
                    virtual_account: account.trim() || null,
                    epayment_number: epayment.trim() || null,
                    due_date: dueDate || null,
                  },
                });
                onClose();
              } catch (e) {
                setErr((e as Error).message);
              }
            }}
          >
            {save.isPending ? "저장 중..." : "저장"}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <p className="text-[12px] text-gray-500">
          예상세액 {row.estimated_tax.toLocaleString()}원 (급여자료 기준 자동 계산)
        </p>

        <div>
          <label className="block text-xs text-gray-500 mb-1">확정 납부세액</label>
          <Input
            inputMode="numeric"
            placeholder="1,240,300"
            value={settledTax === "" ? "" : Number(digitsOnly(settledTax)).toLocaleString()}
            onChange={(e) => setSettledTax(digitsOnly(e.target.value))}
          />
          <p className="text-[11px] text-gray-500 mt-1">
            비우면 사장님 화면에는 예상세액만 보입니다.
          </p>
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">납부기한</label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-transparent px-3 py-1.5 text-sm text-gray-900"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">가상계좌</label>
          <Input
            placeholder="국민 123456-99-000001"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">전자납부번호</label>
          <Input
            placeholder="1234567890123"
            value={epayment}
            onChange={(e) => setEpayment(e.target.value)}
          />
        </div>

        <div className="pt-2 border-t border-gray-200">
          <p className="text-xs text-gray-500 mb-2">
            PDF 문서 (10MB 이하). 올리는 즉시 사장님 화면에서 받을 수 있습니다.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <DocumentSlot
              label="접수증"
              has={row.has_receipt}
              pending={upload.isPending}
              inputRef={receiptRef}
              onPick={(f) => pickDocument("receipt", f)}
            />
            <DocumentSlot
              label="납부서"
              has={row.has_payment_slip}
              pending={upload.isPending}
              inputRef={slipRef}
              onPick={(f) => pickDocument("payment-slip", f)}
            />
          </div>
        </div>

        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}

function DocumentSlot({
  label,
  has,
  pending,
  inputRef,
  onPick,
}: {
  label: string;
  has: boolean;
  pending: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onPick: (file: File | null) => void;
}) {
  return (
    <div className="p-3 rounded-lg border border-gray-300 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900">{label}</span>
        {has ? <Badge tone="success">등록됨</Badge> : <Badge tone="warning">없음</Badge>}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          onPick(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
      <Button
        variant="secondary"
        disabled={pending}
        onClick={() => inputRef.current?.click()}
      >
        {pending ? "업로드 중..." : has ? "교체" : "PDF 올리기"}
      </Button>
    </div>
  );
}

/* ─── 사장님 화면 — 상설 링크 + PIN (plan/12-owner-portal.md §4.3) ─── */

function PortalSection({ clientId }: { clientId: string }) {
  const [confirm, confirmDialog] = useConfirm();
  const { data: link, isLoading } = usePortalLink(clientId);
  const { data: pin } = usePortalPinStatus(clientId);
  const rotate = useRotatePortalLink(clientId);
  const issuePin = useIssuePortalPin(clientId);
  const [copied, setCopied] = useState(false);
  const [newPin, setNewPin] = useState<string | null>(null);
  const [pinInput, setPinInput] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const lockedUntil = pin?.locked_until ? new Date(pin.locked_until) : null;
  const locked = lockedUntil !== null && lockedUntil.getTime() > Date.now();

  return (
    <>
    {confirmDialog}
    <Card>
      <h2 className="text-lg font-semibold text-gray-900">사장님 화면</h2>
      <p className="text-xs text-gray-500 mt-0.5">
        대표님이 급여 자료를 보내는 상설 링크입니다. 매달 바뀌지 않으니 카카오톡에 저장해두고
        쓰시라고 안내하세요.
      </p>

      <div className="mt-4">
        <label className="block text-xs text-gray-500 mb-1">상설 링크</label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            readOnly
            value={isLoading ? "불러오는 중..." : (link?.url ?? "")}
            onFocus={(e) => e.target.select()}
            className="flex-1 rounded-lg border border-gray-300 bg-gray-50 px-3 py-1.5 font-mono text-[12px] text-gray-900"
          />
          <div className="flex gap-2 shrink-0">
            <Button
              variant="secondary"
              disabled={!link}
              onClick={async () => {
                if (!link) return;
                setErr(null);
                try {
                  await navigator.clipboard.writeText(link.url);
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 2000);
                } catch {
                  setErr("복사에 실패했습니다. 주소를 직접 선택해 복사해주세요.");
                }
              }}
            >
              {copied ? "복사됨" : "링크 복사"}
            </Button>
            <Button
              variant="ghost"
              disabled={!link}
              onClick={() => link && window.open(link.url, "_blank")}
            >
              열기
            </Button>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 mt-1">
          <p className="text-[11px] text-gray-500">
            {link
              ? `${new Date(link.issued_at).toLocaleDateString("ko-KR")} 발급 · ${new Date(link.expires_at).toLocaleDateString("ko-KR")} 만료 (30일 전부터 알림톡에 새 링크 자동 반영)`
              : ""}
          </p>
          <Button
            variant="ghost"
            disabled={!link || rotate.isPending}
            onClick={async () => {
              if (!(await confirm("기존 링크가 즉시 사용 불가가 됩니다. 새 링크를 발급할까요?"))) return;
              rotate.mutate();
            }}
          >
            {rotate.isPending ? "재발급 중..." : "링크 재발급 (기존 무효화)"}
          </Button>
        </div>
      </div>

      {pin?.enabled === false ? (
        <div className="mt-5 pt-4 border-t border-gray-200">
          <h3 className="text-sm font-medium text-gray-900">급여 상세 열람 PIN</h3>
          <p className="text-[11px] text-gray-500 mt-0.5">
            현재 비활성화되어 있습니다. 사장님 화면의 급여 상세가 PIN 없이 열립니다.
          </p>
        </div>
      ) : (
      <div className="mt-5 pt-4 border-t border-gray-200">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h3 className="text-sm font-medium text-gray-900">급여 상세 열람 PIN</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">
              직원별 금액을 볼 때만 필요한 6자리 숫자입니다. 자료 제출에는 필요 없습니다.
              <br />
              원하는 번호를 직접 지정하거나, 비워두고 누르면 무작위로 발급됩니다.
              <br />
              링크와 <strong>다른 경로</strong>(전화·기존 카카오톡)로 전달해야 게이트가 의미를 갖습니다.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <input
              inputMode="numeric"
              maxLength={6}
              value={pinInput}
              onChange={(e) => setPinInput(e.target.value.replace(/\D/g, ""))}
              placeholder="직접 지정 (6자리)"
              className="w-[130px] rounded-lg border border-gray-300 px-3 py-1.5 text-[13px] tracking-[0.15em] outline-none focus:border-blue-500"
            />
            <Button
              variant="secondary"
              disabled={issuePin.isPending || (pinInput.length > 0 && pinInput.length !== 6)}
              onClick={async () => {
                if (pin?.is_set && !(await confirm("기존 PIN이 즉시 무효화됩니다. 새 PIN을 설정할까요?"))) return;
                setErr(null);
                try {
                  const res = await issuePin.mutateAsync(pinInput || undefined);
                  setNewPin(res.pin);
                  setPinInput("");
                } catch (e) {
                  setErr((e as Error).message);
                }
              }}
            >
              {issuePin.isPending
                ? "설정 중..."
                : pinInput.length === 6
                  ? "이 PIN으로 설정"
                  : pin?.is_set ? "무작위 재발급" : "무작위 발급"}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 mt-2 text-[12px]">
          {pin?.is_set ? <Badge tone="success">발급됨</Badge> : <Badge tone="warning">미발급</Badge>}
          {lockedUntil && locked && (
            <Badge tone="danger">
              잠김 — {lockedUntil.toLocaleString("ko-KR")} 해제
            </Badge>
          )}
          {pin && !pin.is_set && (
            <span className="text-gray-500">
              미발급이면 사장님 화면에 급여 상세 구역이 아예 표시되지 않습니다.
            </span>
          )}
        </div>

        {newPin && (
          <div className="mt-3 p-3 rounded-lg bg-blue-50/30 border border-blue-600/20">
            <p className="text-[11px] text-gray-500 mb-1">
              새 PIN — 이 화면을 벗어나면 다시 볼 수 없습니다
            </p>
            <p className="font-mono text-xl tracking-[0.3em] text-blue-600">{newPin}</p>
          </div>
        )}
      </div>
      )}

      {err && <p className="text-sm text-red-600 mt-3">{err}</p>}
    </Card>
    </>
  );
}

/* ─── 메시지 — 자료 제출 커뮤니케이션 채널 (plan/12-owner-portal.md §3.8) ───
   AI가 아닌 담당 직원이 직접 응대한다. 보낸 메시지에는 알림이 가지 않는다 —
   급한 건은 기존 카톡·전화로 별도 연락한다. */

function MessagesSection({ clientId }: { clientId: string }) {
  const { data: messages, isLoading } = useClientMessages(clientId);
  const send = useSendClientMessage(clientId);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSend(file?: File) {
    if (!text.trim() && !file) return;
    setErr(null);
    try {
      await send.mutateAsync({ body: text, file });
      setText("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold text-gray-900">메시지</h2>
      <p className="text-xs text-gray-500 mt-0.5">
        사장님 화면에서 자료 제출과 관련해 보낸 메시지입니다. 여기서 답하면 AI가 아닌{" "}
        <strong>담당 직원이 직접 답변</strong>하는 것으로 표시됩니다.
        <br />
        답변에는 알림이 가지 않으니, 급한 연락은 기존 카톡·전화로 따로 해 주세요.
      </p>

      <div className="mt-4 max-h-80 overflow-y-auto flex flex-col gap-2 pr-1">
        {isLoading && <p className="text-sm text-gray-400">불러오는 중...</p>}
        {!isLoading && (messages?.length ?? 0) === 0 && (
          <p className="text-sm text-gray-400">아직 메시지가 없습니다.</p>
        )}
        {messages?.map((m) => (
          <div
            key={m.id}
            className={`max-w-[80%] rounded-xl px-3 py-2 text-[13px] ${
              m.sender_type === "OWNER"
                ? "self-start bg-gray-100 text-gray-900"
                : "self-end bg-blue-600 text-white"
            }`}
          >
            {m.sender_type === "STAFF" && (
              <div className="text-[10.5px] opacity-80 mb-0.5">{m.staff_name ?? "담당 직원"}</div>
            )}
            {m.body && <div className="whitespace-pre-wrap">{m.body}</div>}
            {m.attachment_url && (
              <a
                href={m.attachment_url}
                target="_blank"
                rel="noreferrer"
                className="block mt-1 text-[12px] underline"
              >
                📎 {m.attachment_name ?? "첨부파일"}
              </a>
            )}
            <div className="text-[10px] opacity-70 mt-1">
              {new Date(m.created_at).toLocaleString("ko-KR")}
            </div>
          </div>
        ))}
      </div>

      {err && <p className="text-sm text-red-600 mt-2">{err}</p>}

      <div className="mt-3 flex items-end gap-2 pt-3 border-t border-gray-200">
        <input
          ref={fileRef}
          type="file"
          accept="image/*,.xlsx,.xls,.csv,.pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleSend(f);
          }}
        />
        <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={send.isPending}>
          +
        </Button>
        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          placeholder="답변을 입력하세요"
          disabled={send.isPending}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-500 resize-none"
        />
        <Button disabled={send.isPending || !text.trim()} onClick={() => void handleSend()}>
          {send.isPending ? "전송 중..." : "전송"}
        </Button>
      </div>
    </Card>
  );
}

/* ─── 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8) ─── */

function PayrollDefaultSection({ clientId }: { clientId: string }) {
  const [confirm, confirmDialog] = useConfirm();
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
    data.pay_month_offset ?? "", data.pay_day ?? "",
  ].join("|");

  return (
    <>
    {confirmDialog}
    <PayrollDefaultEditor
      key={dataKey}
      data={data}
      onSave={(patch) => update.mutateAsync(patch)}
      onReset={async () => {
        if (await confirm("시스템 기본값(비과세 한도 + 현행 요율)으로 리셋하시겠습니까?")) {
          reset.mutate();
        }
      }}
      saving={update.isPending}
      resetting={reset.isPending}
    />
    </>
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

      {/* 급여지급일 */}
      <div className="mt-5">
        <h3 className="text-sm font-medium text-gray-900 mb-2">급여지급일</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select
            className="rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-900"
            value={form.pay_month_offset ?? ""}
            onChange={(e) =>
              patchField("pay_month_offset", e.target.value === "" ? null : (Number(e.target.value) as 0 | 1))
            }
          >
            <option value="">미설정</option>
            <option value="0">귀속 당월</option>
            <option value="1">귀속 익월</option>
          </select>
          <select
            className="rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-900"
            value={form.pay_day ?? ""}
            onChange={(e) => patchField("pay_day", e.target.value === "" ? null : Number(e.target.value))}
          >
            <option value="">미설정</option>
            {Array.from({ length: 30 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>
                {d}일
              </option>
            ))}
            <option value={31}>말일</option>
          </select>
        </div>
        <p className="text-xs text-gray-500 mt-1.5">
          {form.pay_month_offset === null || form.pay_day === null
            ? "둘 다 설정해야 위하고로 전송할 수 있습니다 (위하고 급여자료입력은 지급일로 조회)."
            : `예: 6월 귀속 → ${form.pay_month_offset === 1 ? "7월" : "6월"} ${
                form.pay_day === 31 ? "말일" : `${form.pay_day}일`
              } 지급 (그달에 없는 날은 말일)`}
        </p>
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
  const [vatType, setVatType] = useState<VatType | "">(client.vat_type ?? "");
  const [withholdingSemiannual, setWithholdingSemiannual] = useState(client.withholding_semiannual);
  const [fiscalYearEndMonth, setFiscalYearEndMonth] = useState<number | null>(client.fiscal_year_end_month);
  const [sincereFiling, setSincereFiling] = useState(client.sincere_filing);
  const [businessType, setBusinessType] = useState(client.business_type ?? "");
  const [businessItem, setBusinessItem] = useState(client.business_item ?? "");
  const [businessAddress, setBusinessAddress] = useState(client.business_address ?? "");
  const [taxJurisdiction, setTaxJurisdiction] = useState(client.tax_jurisdiction ?? "");
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
                  vat_type: vatType || null,
                  withholding_semiannual: withholdingSemiannual,
                  // 결산월은 법인, 성실신고는 개인에만 의미가 있다 — 반대쪽 값은 보낸 그대로 둔다.
                  ...(isCorporation
                    ? { fiscal_year_end_month: fiscalYearEndMonth }
                    : { sincere_filing: sincereFiling }),
                  business_type: businessType.trim() || null,
                  business_item: businessItem.trim() || null,
                  business_address: businessAddress.trim() || null,
                  tax_jurisdiction: taxJurisdiction.trim() || null,
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
        <div>
          <label className="block text-xs text-gray-500 mb-1">부가세 과세유형</label>
          <select
            value={vatType}
            onChange={(e) => setVatType(e.target.value as VatType | "")}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 outline-none focus:border-blue-500"
          >
            <option value="">미지정</option>
            <option value="GENERAL">일반과세</option>
            <option value="SIMPLIFIED">간이과세</option>
            <option value="EXEMPT">면세</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <input
            id="edit_withholding_semiannual"
            type="checkbox"
            checked={withholdingSemiannual}
            onChange={(e) => setWithholdingSemiannual(e.target.checked)}
            className="h-4 w-4 accent-blue-600"
          />
          <label htmlFor="edit_withholding_semiannual" className="text-[13px] text-gray-900">
            원천세 반기납부
          </label>
        </div>
        {isCorporation ? (
          <div>
            <label className="block text-xs text-gray-500 mb-1">법인 결산월</label>
            <select
              value={fiscalYearEndMonth ?? ""}
              onChange={(e) => setFiscalYearEndMonth(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 outline-none focus:border-blue-500"
            >
              <option value="">미지정</option>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {m}월
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <input
              id="edit_sincere_filing"
              type="checkbox"
              checked={sincereFiling}
              onChange={(e) => setSincereFiling(e.target.checked)}
              className="h-4 w-4 accent-blue-600"
            />
            <label htmlFor="edit_sincere_filing" className="text-[13px] text-gray-900">
              성실신고 대상
            </label>
          </div>
        )}
        <div className="pt-2 border-t border-gray-200">
          <p className="text-[11px] text-gray-400 mb-2">위하고 T 참고 정보 — 보통 &ldquo;위하고에서 가져오기&rdquo;로 채워집니다.</p>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">업태</label>
              <Input placeholder="부동산업" value={businessType} onChange={(e) => setBusinessType(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">종목</label>
              <Input placeholder="비주거용 건물 임대업" value={businessItem} onChange={(e) => setBusinessItem(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">사업장 주소</label>
              <Input value={businessAddress} onChange={(e) => setBusinessAddress(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">관할세무서</label>
              <Input placeholder="원주 세무서" value={taxJurisdiction} onChange={(e) => setTaxJurisdiction(e.target.value)} />
            </div>
          </div>
        </div>
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}
