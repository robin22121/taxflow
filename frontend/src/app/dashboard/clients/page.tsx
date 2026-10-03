"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useClients } from "@/lib/queries";
import { Badge, Button, Card, Input } from "@/components/ui";
import { WehagoImportModal } from "@/components/rpa/wehago-import-modal";
import { formatBizNumber, formatPhone } from "@/lib/format";

export default function ClientsPage() {
  const router = useRouter();
  const { data, isLoading } = useClients();
  const [wehagoOpen, setWehagoOpen] = useState(false);
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">거래처 관리</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setWehagoOpen(true)}>
            위하고에서 가져오기
          </Button>
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
          <p className="text-[13px] text-gray-500">우측 상단 [위하고에서 가져오기]로 시작하세요.</p>
        </Card>
      )}

      {/* Client Table */}
      {!isLoading && clients.length > 0 && (
        <Card className="p-0 overflow-hidden overflow-x-auto">
          <table className="w-full text-[13px] min-w-[540px]">
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
                <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
                  onClick={() => router.push(`/dashboard/clients/${c.id}`)}>
                  <td className="px-4 py-3 font-medium text-gray-900">{c.business_name}</td>
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

      {wehagoOpen && <WehagoImportModal onClose={() => setWehagoOpen(false)} />}
    </div>
  );
}
