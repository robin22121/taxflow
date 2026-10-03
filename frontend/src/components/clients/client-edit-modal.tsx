"use client";

import { useState } from "react";

import { Button, Input, Modal } from "@/components/ui";
import { digitsOnly, formatBizNumber, formatPhone } from "@/lib/format";
import type { Client, VatType } from "@/lib/types";

// 거래처 편집 모달 — 거래처 상세·신고 상세 화면에서 공용으로 쓴다.

export function ClientEditModal({
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
