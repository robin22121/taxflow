"use client";

import { useMemo, useState } from "react";

import { useAssignClient, useClients, useMe, useStaff } from "@/lib/queries";
import { Card } from "@/components/ui";
import type { Client } from "@/lib/types";

export default function AssignmentsPage() {
  const { data: me } = useMe();
  const { data: clients = [], isLoading } = useClients();
  const { data: staff = [] } = useStaff();
  const [onlyMine, setOnlyMine] = useState(false);

  if (me && me.role !== "OWNER") {
    return <p className="text-[13px] text-gray-500">대표(세무사) 계정만 접근할 수 있습니다.</p>;
  }

  const visible = useMemo(
    () => (onlyMine ? clients.filter((c) => c.assigned_user_id === me?.id) : clients),
    [clients, onlyMine, me?.id],
  );
  const unassignedCount = clients.filter((c) => !c.assigned_user_id).length;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">수임담당지정</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          거래처별 담당 직원을 지정하면, 그 직원의 읽기/쓰기 권한이 그대로 적용됩니다.
          {unassignedCount > 0 && (
            <span className="ml-1 text-amber-600 font-medium">미배정 거래처 {unassignedCount}건</span>
          )}
        </p>
      </div>

      <div className="flex gap-1 text-[12px]">
        <button
          onClick={() => setOnlyMine(false)}
          className={`px-3 py-1.5 rounded-md font-medium ${!onlyMine ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600"}`}
        >
          모든 거래처 ({clients.length})
        </button>
        <button
          onClick={() => setOnlyMine(true)}
          className={`px-3 py-1.5 rounded-md font-medium ${onlyMine ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600"}`}
        >
          수임거래처 (내 담당)
        </button>
      </div>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left py-2.5 px-4 text-[11px] font-medium text-gray-500 uppercase tracking-wider">거래처</th>
              <th className="text-left py-2.5 px-4 text-[11px] font-medium text-gray-500 uppercase tracking-wider">담당자</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={2} className="text-center py-6 text-gray-400">불러오는 중...</td></tr>
            )}
            {!isLoading && visible.length === 0 && (
              <tr><td colSpan={2} className="text-center py-6 text-gray-400">해당하는 거래처가 없습니다.</td></tr>
            )}
            {visible.map((c) => (
              <AssignmentRow key={c.id} client={c} staff={staff} />
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function AssignmentRow({
  client,
  staff,
}: {
  client: Client;
  staff: { id: string; name: string; login_code: string | null; is_active: boolean }[];
}) {
  const assign = useAssignClient();

  return (
    <tr className="border-b border-gray-50 last:border-0">
      <td className="py-2.5 px-4 text-gray-900">{client.business_name}</td>
      <td className="py-2.5 px-4">
        <select
          value={client.assigned_user_id ?? ""}
          onChange={(e) => assign.mutate({ clientId: client.id, userId: e.target.value || null })}
          className="rounded-md border border-gray-200 px-2 py-1 text-[12px] bg-white"
          disabled={assign.isPending}
        >
          <option value="">미배정</option>
          {staff.filter((s) => s.is_active).map((s) => (
            <option key={s.id} value={s.id}>
              {s.login_code ? `${s.login_code} · ` : ""}{s.name}
            </option>
          ))}
        </select>
      </td>
    </tr>
  );
}
