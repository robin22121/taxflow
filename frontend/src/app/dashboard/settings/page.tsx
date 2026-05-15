"use client";

import { useState } from "react";
import { useMe } from "@/lib/queries";
import { Button, Card } from "@/components/ui";

export default function SettingsPage() {
  const { data: me } = useMe();
  const [copied, setCopied] = useState(false);

  function copyCode() {
    if (!me?.short_code) return;
    navigator.clipboard.writeText(me.short_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">설정</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">사무소 정보 및 인가코드를 확인하세요.</p>
      </div>

      <Card className="p-5 space-y-4">
        <h2 className="text-[14px] font-semibold text-gray-900">사무소 인가코드</h2>
        <p className="text-[13px] text-gray-500">
          카카오톡 채널에서 직원이 이 코드를 입력하면 사무소에 연결됩니다.
        </p>

        <div className="flex items-center gap-3">
          <div className="bg-gray-50 border border-gray-200 rounded-xl py-3 px-5 flex-1">
            <div className="text-[11px] text-gray-400 uppercase tracking-wider mb-0.5">인가코드</div>
            <div className="text-[24px] font-bold tracking-[0.15em] text-gray-900 font-mono">
              {me?.short_code ?? "—"}
            </div>
          </div>
          <Button variant="secondary" onClick={copyCode} className="shrink-0">
            {copied ? "복사됨" : "복사"}
          </Button>
        </div>

        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
          <p className="text-[12px] text-blue-700">
            <span className="font-semibold">사용법:</span> 카카오톡 이지원천 채널에서{" "}
            <span className="font-mono font-bold">등록 {me?.short_code ?? "코드"}</span>를 입력하세요.
          </p>
        </div>
      </Card>

      <Card className="p-5 space-y-3">
        <h2 className="text-[14px] font-semibold text-gray-900">계정 정보</h2>
        <InfoRow label="아이디 (사업자번호)" value={me?.email ?? "—"} />
        <InfoRow label="담당자" value={me?.name ?? "—"} />
      </Card>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-[12px] text-gray-500">{label}</span>
      <span className="text-[13px] font-medium text-gray-900">{value}</span>
    </div>
  );
}
