"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useBulkUploadClients, useClients, useCreateClient } from "@/lib/queries";
import { Button, Card, Input, Modal } from "@/components/ui";

export default function ClientsPage() {
  const { data, isLoading } = useClients();
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">거래처 관리</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setBulkOpen(true)}>
            거래처 일괄 업로드
          </Button>
          <Button onClick={() => setOpen(true)}>+ 거래처 추가</Button>
        </div>
      </div>

      {isLoading && <p>로딩 중...</p>}

      {!isLoading && (data ?? []).length === 0 && (
        <Card>
          <p className="text-sm text-gray-500">
            등록된 거래처가 없습니다. 우측 상단 [거래처 추가]로 시작하세요.
          </p>
        </Card>
      )}

      <div className="grid gap-3">
        {(data ?? []).map((c) => (
          <Link key={c.id} href={`/dashboard/clients/${c.id}`}>
            <Card className="hover:border-blue-400 transition-colors cursor-pointer">
              <div className="flex items-baseline gap-3">
                <div className="text-lg font-medium">{c.business_name}</div>
                {c.business_number && (
                  <span className="text-xs text-gray-500">{c.business_number}</span>
                )}
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {[c.representative, c.contact_phone, c.contact_email]
                  .filter(Boolean)
                  .join(" · ") || "—"}
              </div>
            </Card>
          </Link>
        ))}
      </div>

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
      <div className="space-y-3 text-sm">
        {result ? (
          <p className="text-green-700 dark:text-green-300">
            {result.count}개 거래처가 등록되었습니다.
          </p>
        ) : (
          <>
            <p className="text-gray-600 dark:text-gray-400">
              엑셀(.xlsx) 또는 CSV 파일을 업로드하세요.
            </p>
            <p className="text-xs text-gray-500">
              필수 컬럼: <strong>상호</strong> (또는 사업자명, 거래처명)
              <br />
              선택 컬럼: 사업자번호, 대표자, 전화번호, 이메일, 법인여부
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="block w-full text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-blue-950 dark:file:text-blue-300"
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

  const canSubmit = businessName.trim().length > 0 && !create.isPending;

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
          <Button
            disabled={!canSubmit}
            onClick={async () => {
              setErr(null);
              try {
                const created = await create.mutateAsync({
                  business_name: businessName.trim(),
                  business_number: businessNumber.trim() || null,
                  representative: representative.trim() || null,
                  contact_phone: contactPhone.trim() || null,
                  contact_email: contactEmail.trim() || null,
                  is_corporation: isCorporation,
                });
                onClose();
                router.push(`/dashboard/clients/${created.id}`);
              } catch (e) {
                setErr((e as Error).message);
              }
            }}
          >
            {create.isPending ? "등록 중..." : "등록"}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <div>
          <label className="block text-xs text-gray-500 mb-1">
            상호 <span className="text-red-500">*</span>
          </label>
          <Input
            placeholder="(주)에이상사"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">사업자번호</label>
          <Input
            placeholder="123-45-67890"
            value={businessNumber}
            onChange={(e) => setBusinessNumber(e.target.value)}
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
            value={contactPhone}
            onChange={(e) => setContactPhone(e.target.value)}
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
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-1">
            초대장 이메일이 이 주소로 발송됩니다.
          </p>
        </div>
        <div className="flex items-center gap-2 pt-1">
          <input
            id="is_corporation"
            type="checkbox"
            checked={isCorporation}
            onChange={(e) => setIsCorporation(e.target.checked)}
            className="h-4 w-4"
          />
          <label htmlFor="is_corporation" className="text-sm">
            법인 거래처 (원천징수이행상황신고서 A01 분류)
          </label>
        </div>
        {err && <p className="text-red-600">{err}</p>}
      </div>
    </Modal>
  );
}
