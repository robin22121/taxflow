"use client";

// 사원 목록 — 거래처정보 상세에 있던 "직원 마스터 업로드"·"소득지급자 목록"과
// 거래처정보 목록에 있던 "위하고에서 가져오기"를 이 메뉴로 옮겼다 (2026-10-01).

import { useState } from "react";

import { Button, Card } from "@/components/ui";
import { ClientPicker, useSelectedClientId } from "@/components/clients/client-picker";
import { RosterContent } from "@/components/employees/roster-content";
import { WehagoImportModal } from "@/components/rpa/wehago-import-modal";

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
