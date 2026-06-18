"use client";

import { useState } from "react";

import { Badge, Button, Card, Chip, Input, Modal, Textarea } from "@/components/ui";
import { formatBizNumber } from "@/lib/format";
import {
  useAddPromotion,
  useAdminOfficeDetail,
  useAdminOffices,
  useApproveOffice,
  useDeletePromotion,
  useRejectOffice,
  useUpdateOffice,
} from "@/lib/queries";
import type { AdminOffice } from "@/lib/types";

const STATUS_FILTERS = [
  { key: "PENDING", label: "승인 대기" },
  { key: "APPROVED", label: "승인됨" },
  { key: "REJECTED", label: "거부됨" },
  { key: "", label: "전체" },
] as const;

const STATUS_META: Record<AdminOffice["approval_status"], { label: string; tone: "warning" | "success" | "danger" }> = {
  PENDING: { label: "승인 대기", tone: "warning" },
  APPROVED: { label: "승인됨", tone: "success" },
  REJECTED: { label: "거부됨", tone: "danger" },
};

const CLASS_OPTIONS = [
  { key: "TRIAL", label: "무료 체험" },
  { key: "REGULAR", label: "정식" },
  { key: "VIP", label: "VIP" },
  { key: "CHURNED", label: "해지" },
] as const;

const CLASS_LABEL: Record<AdminOffice["customer_class"], string> = {
  TRIAL: "무료 체험",
  REGULAR: "정식",
  VIP: "VIP",
  CHURNED: "해지",
};

export default function AdminPage() {
  const [filter, setFilter] = useState<string>("PENDING");
  const [detailId, setDetailId] = useState<string | null>(null);
  const { data: offices, isLoading } = useAdminOffices(filter || undefined);
  const approve = useApproveOffice();
  const reject = useRejectOffice();

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-xl font-bold tracking-tight text-gray-900 mb-1">사무소 회원 관리</h1>
      <p className="text-[13px] text-gray-500 mb-5">가입 승인, 고객 분류, 결제기간, 프로모션을 관리합니다.</p>

      <div className="flex gap-1.5 mb-4">
        {STATUS_FILTERS.map((f) => (
          <button key={f.key} onClick={() => setFilter(f.key)}>
            <Chip active={filter === f.key}>{f.label}</Chip>
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-[13px] text-gray-400">불러오는 중...</div>
        ) : !offices || offices.length === 0 ? (
          <div className="p-8 text-center text-[13px] text-gray-400">해당하는 사무소가 없습니다.</div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-200 text-left text-[11px] text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-2.5 font-medium">사무소</th>
                <th className="px-4 py-2.5 font-medium">상태</th>
                <th className="px-4 py-2.5 font-medium">분류</th>
                <th className="px-4 py-2.5 font-medium">결제기간</th>
                <th className="px-4 py-2.5 font-medium text-center">사용자</th>
                <th className="px-4 py-2.5 font-medium text-right">작업</th>
              </tr>
            </thead>
            <tbody>
              {offices.map((o) => (
                <tr key={o.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{o.name}</div>
                    <div className="text-[11px] text-gray-400">
                      {o.business_number ? formatBizNumber(o.business_number) : "—"}
                      {o.representative ? ` · ${o.representative}` : ""}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_META[o.approval_status].tone}>
                      {STATUS_META[o.approval_status].label}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{CLASS_LABEL[o.customer_class]}</td>
                  <td className="px-4 py-3 text-gray-600 text-[12px]">
                    {o.subscription_start || o.subscription_end
                      ? `${o.subscription_start ?? "?"} ~ ${o.subscription_end ?? "?"}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-center text-gray-600">{o.user_count}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      {o.approval_status === "PENDING" && (
                        <>
                          <Button
                            variant="primary"
                            className="px-3 py-1 text-[12px]"
                            disabled={approve.isPending}
                            onClick={() => approve.mutate(o.id)}
                          >
                            승인
                          </Button>
                          <Button
                            variant="danger"
                            className="px-3 py-1 text-[12px]"
                            disabled={reject.isPending}
                            onClick={() => reject.mutate(o.id)}
                          >
                            거부
                          </Button>
                        </>
                      )}
                      <Button
                        variant="secondary"
                        className="px-3 py-1 text-[12px]"
                        onClick={() => setDetailId(o.id)}
                      >
                        관리
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {detailId && <OfficeDetailModal officeId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  );
}

function OfficeDetailModal({ officeId, onClose }: { officeId: string; onClose: () => void }) {
  const { data: office, isLoading } = useAdminOfficeDetail(officeId);
  const update = useUpdateOffice();
  const addPromo = useAddPromotion();
  const delPromo = useDeletePromotion();

  const [form, setForm] = useState<{ customer_class: string; subscription_start: string; subscription_end: string; admin_memo: string } | null>(null);
  const [promo, setPromo] = useState({ name: "", discount: "", start_date: "", end_date: "", memo: "" });
  const [err, setErr] = useState<string | null>(null);

  // office 로드 후 폼 초기화 (최초 1회)
  if (office && form === null) {
    setForm({
      customer_class: office.customer_class,
      subscription_start: office.subscription_start ?? "",
      subscription_end: office.subscription_end ?? "",
      admin_memo: office.admin_memo ?? "",
    });
  }

  async function saveOffice() {
    if (!form) return;
    setErr(null);
    try {
      await update.mutateAsync({
        officeId,
        customer_class: form.customer_class,
        subscription_start: form.subscription_start || null,
        subscription_end: form.subscription_end || null,
        admin_memo: form.admin_memo || null,
      });
      onClose();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function submitPromo() {
    if (!promo.name.trim()) {
      setErr("프로모션명을 입력하세요");
      return;
    }
    setErr(null);
    try {
      await addPromo.mutateAsync({
        officeId,
        name: promo.name,
        discount: promo.discount || null,
        start_date: promo.start_date || null,
        end_date: promo.end_date || null,
        memo: promo.memo || null,
      });
      setPromo({ name: "", discount: "", start_date: "", end_date: "", memo: "" });
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <Modal open onClose={onClose} title={office ? office.name : "사무소 관리"}>
      {isLoading || !office || !form ? (
        <div className="py-6 text-center text-[13px] text-gray-400">불러오는 중...</div>
      ) : (
        <div className="space-y-5">
          {/* 회원 정보 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">고객 분류</label>
              <select
                value={form.customer_class}
                onChange={(e) => setForm({ ...form, customer_class: e.target.value })}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 outline-none focus:border-blue-500"
              >
                {CLASS_OPTIONS.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">사업자번호</label>
              <div className="px-3 py-2 text-[13px] text-gray-500">
                {office.business_number ? formatBizNumber(office.business_number) : "—"}
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">결제기간 시작</label>
              <Input type="date" value={form.subscription_start} onChange={(e) => setForm({ ...form, subscription_start: e.target.value })} />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-gray-600 mb-1">결제기간 종료</label>
              <Input type="date" value={form.subscription_end} onChange={(e) => setForm({ ...form, subscription_end: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-gray-600 mb-1">관리자 메모</label>
            <Textarea rows={2} value={form.admin_memo} onChange={(e) => setForm({ ...form, admin_memo: e.target.value })} />
          </div>
          <div className="flex justify-end">
            <Button onClick={saveOffice} disabled={update.isPending} className="px-4 py-1.5 text-[12px]">
              {update.isPending ? "저장중..." : "회원 정보 저장"}
            </Button>
          </div>

          {/* 프로모션 부여 내역 */}
          <div className="border-t border-gray-200 pt-4">
            <div className="text-[12px] font-semibold text-gray-900 mb-2">프로모션 부여 내역</div>
            {office.promotions.length === 0 ? (
              <div className="text-[12px] text-gray-400 mb-3">부여된 프로모션이 없습니다.</div>
            ) : (
              <div className="space-y-1.5 mb-3">
                {office.promotions.map((p) => (
                  <div key={p.id} className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                    <div className="min-w-0">
                      <div className="text-[12px] font-medium text-gray-900">
                        {p.name}
                        {p.discount ? <span className="text-blue-600 ml-1.5">{p.discount}</span> : null}
                      </div>
                      <div className="text-[11px] text-gray-400">
                        {(p.start_date || p.end_date) ? `${p.start_date ?? "?"} ~ ${p.end_date ?? "?"}` : "기간 미지정"}
                        {p.memo ? ` · ${p.memo}` : ""}
                      </div>
                    </div>
                    <button
                      onClick={() => delPromo.mutate(p.id)}
                      className="text-[11px] text-red-600 hover:underline shrink-0 ml-2"
                    >
                      삭제
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* 신규 프로모션 부여 */}
            <div className="bg-gray-50/60 border border-gray-200 rounded-lg p-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <Input placeholder="프로모션명" value={promo.name} onChange={(e) => setPromo({ ...promo, name: e.target.value })} />
                <Input placeholder="할인 (예: 30%, 3개월 무료)" value={promo.discount} onChange={(e) => setPromo({ ...promo, discount: e.target.value })} />
                <Input type="date" value={promo.start_date} onChange={(e) => setPromo({ ...promo, start_date: e.target.value })} />
                <Input type="date" value={promo.end_date} onChange={(e) => setPromo({ ...promo, end_date: e.target.value })} />
              </div>
              <Input placeholder="메모 (선택)" value={promo.memo} onChange={(e) => setPromo({ ...promo, memo: e.target.value })} />
              <div className="flex justify-end">
                <Button variant="secondary" onClick={submitPromo} disabled={addPromo.isPending} className="px-3 py-1 text-[12px]">
                  {addPromo.isPending ? "추가중..." : "프로모션 부여"}
                </Button>
              </div>
            </div>
          </div>

          {err && <p className="text-[12px] text-red-600">{err}</p>}
        </div>
      )}
    </Modal>
  );
}
