"use client";

import { useState } from "react";

import { useMe, useCreateStaff, useStaff, useUpdateStaff } from "@/lib/queries";
import { Badge, Button, Card, Input } from "@/components/ui";
import type { Staff } from "@/lib/types";

export default function StaffPage() {
  const { data: me } = useMe();
  const { data: staff = [], isLoading } = useStaff();
  const [showAdd, setShowAdd] = useState(false);

  if (me && me.role !== "OWNER") {
    return <p className="text-[13px] text-gray-500">대표(세무사) 계정만 접근할 수 있습니다.</p>;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight text-gray-900">직원계정 등록/변경</h1>
          <p className="text-[13px] text-gray-500 mt-0.5">
            아이디(사업자번호)는 대표와 공용, 코드는 순서대로 자동 부여됩니다.
          </p>
        </div>
        <Button onClick={() => setShowAdd(true)}>직원 추가</Button>
      </div>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left py-2.5 px-4 text-[11px] font-medium text-gray-500 uppercase tracking-wider">코드</th>
              <th className="text-left py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">이름</th>
              <th className="text-left py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">역할</th>
              <th className="text-center py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">쓰기권한</th>
              <th className="text-center py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">담당 거래처</th>
              <th className="text-center py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">상태</th>
              <th className="py-2.5 px-4" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="text-center py-6 text-gray-400">불러오는 중...</td></tr>
            )}
            {!isLoading && staff.length === 0 && (
              <tr><td colSpan={7} className="text-center py-6 text-gray-400">등록된 직원이 없습니다.</td></tr>
            )}
            {staff.map((s) => <StaffRow key={s.id} staff={s} />)}
          </tbody>
        </table>
      </Card>

      {showAdd && <AddStaffModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}

function StaffRow({ staff }: { staff: Staff }) {
  const update = useUpdateStaff();

  return (
    <tr className="border-b border-gray-50 last:border-0">
      <td className="py-2.5 px-4 font-mono font-semibold text-gray-700">{staff.login_code ?? "—"}</td>
      <td className="py-2.5 px-2 text-gray-900">{staff.name}</td>
      <td className="py-2.5 px-2 text-gray-500">{staff.role === "OWNER" ? "대표" : "직원"}</td>
      <td className="py-2.5 px-2 text-center">
        {staff.role === "OWNER" ? (
          <span className="text-gray-400">항상 가능</span>
        ) : (
          <input
            type="checkbox"
            checked={staff.can_write}
            onChange={(e) => update.mutate({ id: staff.id, can_write: e.target.checked })}
            className="h-3.5 w-3.5 accent-blue-600"
          />
        )}
      </td>
      <td className="py-2.5 px-2 text-center tabular-nums text-gray-600">{staff.assigned_client_count}</td>
      <td className="py-2.5 px-2 text-center">
        <Badge tone={staff.is_active ? "success" : "neutral"}>{staff.is_active ? "활성" : "비활성"}</Badge>
      </td>
      <td className="py-2.5 px-4 text-right">
        {staff.role !== "OWNER" && (
          <button
            onClick={() => update.mutate({ id: staff.id, is_active: !staff.is_active })}
            className="text-[12px] text-gray-500 hover:underline"
          >
            {staff.is_active ? "비활성화" : "다시 활성화"}
          </button>
        )}
      </td>
    </tr>
  );
}

function AddStaffModal({ onClose }: { onClose: () => void }) {
  const create = useCreateStaff();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [canWrite, setCanWrite] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    create.mutate(
      { name: name.trim(), password, can_write: canWrite },
      { onSuccess: onClose, onError: (e) => setErr((e as Error).message) },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <Card className="w-full max-w-sm p-5 space-y-4">
        <h2 className="text-[15px] font-semibold text-gray-900">직원 추가</h2>
        <form className="space-y-3" onSubmit={submit}>
          <div>
            <label className="block text-[12px] font-medium text-gray-700 mb-1">이름</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="block text-[12px] font-medium text-gray-700 mb-1">초기 비밀번호</label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <p className="text-[11px] text-gray-400 mt-1">6자리 이상, 특수문자 포함</p>
          </div>
          <label className="flex items-center gap-2 text-[13px] text-gray-700">
            <input type="checkbox" checked={canWrite} onChange={(e) => setCanWrite(e.target.checked)} className="h-3.5 w-3.5 accent-blue-600" />
            쓰기 권한 부여 (해제 시 담당 거래처 조회만 가능)
          </label>
          {err && <p className="text-[12px] text-red-600">{err}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={onClose}>취소</Button>
            <Button type="submit" disabled={create.isPending}>{create.isPending ? "추가 중..." : "추가"}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
