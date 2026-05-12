"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useClients, useCreateClient } from "@/lib/queries";
import { Button, Card, Input, Modal } from "@/components/ui";

export default function ClientsPage() {
  const { data, isLoading } = useClients();
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">거래처 관리</h1>
        <Button onClick={() => setOpen(true)}>+ 거래처 추가</Button>
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
    </div>
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
