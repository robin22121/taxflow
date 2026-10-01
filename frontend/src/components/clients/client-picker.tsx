"use client";

// 사원정보 메뉴(사원 목록·급여명세서)의 거래처 선택 — plan/08-action-items.md
// "거래처정보에서 사원/급여 섹션을 사원정보 메뉴로 이관" (2026-10-01).
//
// 거래처정보 상세 화면의 "사원정보 보기"/"급여정보 보기" 링크가 ?client=<id>로 넘기면
// 그 거래처를 자동 선택하고, 사원정보 탭을 직접 열면(쿼리 없음) 첫 거래처를 기본값으로 쓴다.
// 페이지 안에서 드롭다운으로 다른 거래처로 바꿀 수 있다.

import { useRouter, useSearchParams } from "next/navigation";

import { useClients } from "@/lib/queries";
import { formatBizNumber } from "@/lib/format";

export function useSelectedClientId(): {
  clientId: string | null;
  setClientId: (id: string) => void;
  loading: boolean;
} {
  const router = useRouter();
  const params = useSearchParams();
  const { data: clients, isLoading } = useClients();

  const fromQuery = params.get("client");
  const clientId = fromQuery || clients?.[0]?.id || null;

  function setClientId(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("client", id);
    router.push(`?${next.toString()}`);
  }

  return { clientId, setClientId, loading: isLoading };
}

export function ClientPicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (id: string) => void;
}) {
  const { data: clients } = useClients();

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-900 outline-none focus:border-blue-500"
    >
      <option value="" disabled>
        거래처 선택
      </option>
      {(clients ?? []).map((c) => (
        <option key={c.id} value={c.id}>
          {c.business_name}
          {c.business_number ? ` (${formatBizNumber(c.business_number)})` : ""}
        </option>
      ))}
    </select>
  );
}
