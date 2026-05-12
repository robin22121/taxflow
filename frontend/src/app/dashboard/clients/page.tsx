"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useBulkUploadClients, useClients, useCreateClient, useSendClientInvite } from "@/lib/queries";
import { Badge, Button, Card, Input, Modal } from "@/components/ui";
import { digitsOnly, formatBizNumber, formatPhone } from "@/lib/format";

export default function ClientsPage() {
  const { data, isLoading } = useClients();
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [search, setSearch] = useState("");

  const clients = (data ?? []).filter((c) =>
    search
      ? c.business_name.toLowerCase().includes(search.toLowerCase()) ||
        (c.business_number ?? "").includes(search) ||
        (c.representative ?? "").includes(search)
      : true,
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">거래처 관리</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setBulkOpen(true)}>
            거래처 일괄 업로드
          </Button>
          <Button onClick={() => setOpen(true)}>+ 거래처 추가</Button>
        </div>
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <Input
          placeholder="거래처 검색 (상호, 사업자번호, 대표자)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Badge tone="neutral">{clients.length}곳</Badge>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 rounded-[14px] bg-white animate-pulse border border-gray-200" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (data ?? []).length === 0 && (
        <Card className="text-center py-12">
          <div className="text-4xl mb-3 opacity-30">🏢</div>
          <p className="text-[15px] font-medium text-gray-700 mb-1">등록된 거래처가 없습니다</p>
          <p className="text-[13px] text-gray-500">우측 상단 [거래처 추가]로 시작하세요.</p>
        </Card>
      )}

      {/* Client Table */}
      {!isLoading && clients.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-300">
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">상호</th>
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">사업자번호</th>
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">대표자</th>
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">연락처</th>
                <th className="text-left px-4 py-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider">이메일</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Link
                      href={`/dashboard/clients/${c.id}`}
                      className="font-medium text-gray-900 hover:text-blue-600 transition-colors"
                    >
                      {c.business_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700 t-num">{c.business_number ? formatBizNumber(c.business_number) : "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{c.representative || "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{c.contact_phone ? formatPhone(c.contact_phone) : "—"}</td>
                  <td className="px-4 py-3 text-gray-700">{c.contact_email || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {open && <CreateClientModal onClose={() => setOpen(false)} />}
      {bulkOpen && <BulkUploadModal onClose={() => setBulkOpen(false)} />}
    </div>
  );
}

function BulkUploadModal({ onClose }: { onClose: () => void }) {
  const bulk = useBulkUploadClients();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ count: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  return (
    <Modal
      open={true}
      onClose={onClose}
      title="거래처 일괄 업로드"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={bulk.isPending}>
            {result ? "닫기" : "취소"}
          </Button>
          {!result && (
            <Button
              disabled={!file || bulk.isPending}
              onClick={async () => {
                if (!file) return;
                setErr(null);
                try {
                  const created = await bulk.mutateAsync(file);
                  setResult({ count: created.length });
                } catch (e) {
                  setErr((e as Error).message);
                }
              }}
            >
              {bulk.isPending ? "업로드 중..." : "업로드"}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-3 text-[13px]">
        {result ? (
          <p className="text-blue-600 font-medium">
            {result.count}개 거래처가 등록되었습니다.
          </p>
        ) : (
          <>
            <p className="text-gray-700">
              엑셀(.xlsx) 또는 CSV 파일을 업로드하세요.
            </p>
            <p className="text-[12px] text-gray-500">
              필수 컬럼: <strong>상호</strong> (또는 사업자명, 거래처명)
              <br />
              선택 컬럼: 사업자번호, 대표자, 전화번호, 이메일, 법인여부
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="block w-full text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </>
        )}
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}

function CreateClientModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const create = useCreateClient();
  const [businessName, setBusinessName] = useState("");
  const [businessNumber, setBusinessNumber] = useState("");
  const [representative, setRepresentative] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [isCorporation, setIsCorporation] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const sendInvite = useSendClientInvite(createdId ?? "__none__");

  const canSubmit = businessName.trim().length > 0 && !create.isPending;
  const hasContact = contactPhone.trim().length > 0 || contactEmail.trim().length > 0;

  async function doCreate(andInvite: boolean) {
    setErr(null);
    try {
      const created = await create.mutateAsync({
        business_name: businessName.trim(),
        business_number: digitsOnly(businessNumber) || null,
        representative: representative.trim() || null,
        contact_phone: digitsOnly(contactPhone) || null,
        contact_email: contactEmail.trim() || null,
        is_corporation: isCorporation,
      });
      if (andInvite) {
        setCreatedId(created.id);
        try { await sendInvite.mutateAsync(); } catch { /* invite failure is non-blocking */ }
      }
      onClose();
      router.push(`/dashboard/clients/${created.id}`);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <Modal
      open={true}
      onClose={onClose}
      title="거래처 추가"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            취소
          </Button>
          <Button variant="secondary" disabled={!canSubmit} onClick={() => doCreate(false)}>
            {create.isPending ? "등록 중..." : "등록"}
          </Button>
          <Button disabled={!canSubmit || !hasContact} onClick={() => doCreate(true)}
            title={!hasContact ? "연락처 입력 시 초대 발송 가능" : ""}>
            {create.isPending ? "등록 중..." : "저장 + 초대 발송"}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-[13px]">
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">
            상호 <span className="text-red-600">*</span>
          </label>
          <Input
            placeholder="(주)에이상사"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">사업자번호</label>
          <Input
            placeholder="123-45-67890"
            value={formatBizNumber(businessNumber)}
            onChange={(e) => setBusinessNumber(digitsOnly(e.target.value))}
          />
        </div>
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">대표자</label>
          <Input
            placeholder="홍길동"
            value={representative}
            onChange={(e) => setRepresentative(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">전화번호 (휴대폰)</label>
          <Input
            type="tel"
            placeholder="010-1234-5678"
            value={formatPhone(contactPhone)}
            onChange={(e) => setContactPhone(digitsOnly(e.target.value))}
          />
          <p className="text-[11px] text-gray-500 mt-1">알림톡·SMS 발송에 사용됩니다.</p>
        </div>
        <div>
          <label className="block text-[12px] text-gray-500 mb-1">이메일</label>
          <Input
            type="email"
            placeholder="contact@example.com"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
          />
          <p className="text-[11px] text-gray-500 mt-1">초대장 이메일이 이 주소로 발송됩니다.</p>
        </div>
        <div className="flex items-center gap-2 pt-1">
          <input
            id="is_corporation"
            type="checkbox"
            checked={isCorporation}
            onChange={(e) => setIsCorporation(e.target.checked)}
            className="h-4 w-4 accent-blue-600"
          />
          <label htmlFor="is_corporation" className="text-[13px] text-gray-900">
            법인 거래처 (원천징수이행상황신고서 A01 분류)
          </label>
        </div>
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}
