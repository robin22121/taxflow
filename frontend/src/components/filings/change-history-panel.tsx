"use client";

// 급여 변경이력 패널 — 급여 영역 머리줄의 [변경이력]에서 연다 (받은 자료·원천세관리 공통).
// 삭제된 항목은 표에서 사라지므로 여기서 확인하고 [복구]한다.

import { useState } from "react";

import { Badge, Button } from "@/components/ui";
import { useEntryChanges, useUpdateEntry } from "@/lib/queries";
import type { EntryChange } from "@/lib/types";

const FIELD_LABEL: Record<string, string> = {
  raw_name: "이름", employee_id: "직원 연결", income_type: "소득구분", business_type_code: "업종코드",
  other_income_code: "소득구분코드", total_amount: "총지급액", salary_amount: "급여", bonus_amount: "상여",
  non_taxable: "비과세", meal_amount: "식대", car_amount: "자가운전", childcare_amount: "육아",
  taxable: "과세표준", necessary_expense: "필요경비", national_pension: "국민연금", health_insurance: "건강보험",
  employment_insurance: "고용보험", longterm_care: "장기요양", income_tax: "소득세", local_tax: "지방소득세",
  student_loan: "학자금상환액", settlement_insurance: "정산보험료", rent_support: "월세지원금",
  payment_date: "지급일", work_days: "근무일수",
};

const INCOME_LABEL: Record<string, string> = {
  WAGE: "근로", DAILY: "일용", BUSINESS: "사업", OTHER: "기타", RETIREMENT: "퇴직",
};

const ACTION: Record<EntryChange["action"], { label: string; tone: "neutral" | "info" | "warning" | "success" | "danger" }> = {
  CREATE: { label: "등록", tone: "info" },
  UPDATE: { label: "수정", tone: "warning" },
  DELETE: { label: "삭제", tone: "danger" },
  RESTORE: { label: "복구", tone: "success" },
  APPROVE: { label: "승인", tone: "success" },
  UNAPPROVE: { label: "승인취소", tone: "neutral" },
  PURGE: { label: "영구삭제", tone: "danger" },
};

const SOURCE_LABEL: Record<string, string> = {
  manual: "직접 수정", collect: "고객 자료", portal: "사장님 포털", carry_forward: "전월 동일",
  import: "엑셀 임포트", fast_path: "페스트패스", system: "시스템",
};

function formatValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "income_type") return INCOME_LABEL[String(value)] ?? String(value);
  if (field === "work_days") return `${value}일`;
  if (typeof value === "number") return `${value.toLocaleString("ko-KR")}원`;
  return String(value);
}

function formatAt(iso: string): string {
  // 시간대 표시가 없는 값(개발용 SQLite)은 UTC로 본다.
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, "0")}:${mm}`;
}

type Group = { key: string; rows: EntryChange[] };

/** 같은 묶음(batch_id)·같은 동작의 연속된 이력은 "일괄 승인 12건"처럼 한 덩어리로 접는다. */
function groupRows(rows: EntryChange[]): Group[] {
  const out: Group[] = [];
  for (const row of rows) {
    const last = out[out.length - 1];
    if (last && row.batch_id && last.rows[0].batch_id === row.batch_id && last.rows[0].action === row.action) {
      last.rows.push(row);
    } else {
      out.push({ key: row.id, rows: [row] });
    }
  }
  return out;
}

export function ChangeHistoryPanel({
  filingId, clientId, clientName, entryId, onClearEntry, onClose, onBeforeRestore,
}: {
  filingId: string;
  clientId: string;
  clientName: string;
  entryId: string | null; // 특정 직원(항목)만 볼 때
  onClearEntry: () => void;
  onClose: () => void;
  // 복구 전에 확인이 필요하면(예: 이미 위하고로 전송된 자료) false 를 돌려줘 막는다.
  onBeforeRestore?: (row: EntryChange) => Promise<boolean>;
}) {
  const [includeApprovals, setIncludeApprovals] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());
  const { data: rows = [], isLoading, isError } = useEntryChanges(filingId, { clientId, entryId, includeApprovals });
  const update = useUpdateEntry(filingId);

  // 복구는 항목별로 가장 최근 이력이 "삭제"이고 지금도 삭제 상태일 때만 보여준다 (rows 는 최신순).
  const restorable = new Set<string>();
  const seen = new Set<string>();
  for (const r of rows) {
    if (seen.has(r.entry_id)) continue;
    seen.add(r.entry_id);
    if (r.action === "DELETE" && r.entry_deleted === true) restorable.add(r.id);
  }

  async function restore(row: EntryChange) {
    if (onBeforeRestore && !(await onBeforeRestore(row))) return;
    update.mutate({ id: row.entry_id, patch: { deleted: false } }, { onError: (err) => alert((err as Error).message) });
  }

  const groups = groupRows(rows);
  const subject = entryId ? rows[0]?.subject_name : null;

  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-[min(92vw,440px)] bg-white border-l border-gray-200 shadow-xl flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 shrink-0">
        <h2 className="text-[14px] font-bold text-gray-900">변경이력</h2>
        <span className="text-[12px] text-gray-500 truncate">{clientName}</span>
        <span className="flex-1" />
        <button onClick={onClose} aria-label="닫기" className="text-gray-400 hover:text-gray-700 text-[16px] leading-none px-1">✕</button>
      </div>

      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-100 shrink-0 text-[12px]">
        {entryId && (
          <button onClick={onClearEntry} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100 hover:bg-blue-100">
            {subject ?? "선택한 직원"}만 보는 중 ✕
          </button>
        )}
        <span className="flex-1" />
        <label className="flex items-center gap-1.5 text-gray-600 cursor-pointer">
          <input type="checkbox" checked={includeApprovals} onChange={(e) => setIncludeApprovals(e.target.checked)} className="accent-blue-600" />
          승인 이력 포함
        </label>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {isLoading && <p className="text-[12px] text-gray-400 text-center py-6">불러오는 중...</p>}
        {isError && <p className="text-[12px] text-red-600 text-center py-6">변경이력을 불러오지 못했습니다.</p>}
        {!isLoading && !isError && rows.length === 0 && (
          <p className="text-[12px] text-gray-400 text-center py-8">변경 이력이 없습니다.</p>
        )}
        {groups.map((g) => {
          const head = g.rows[0];
          if (g.rows.length === 1) {
            return (
              <ChangeRow key={g.key} row={head} canRestore={restorable.has(head.id)}
                restoring={update.isPending}
                onRestore={() => restore(head)} />
            );
          }
          const open = openGroups.has(g.key);
          return (
            <div key={g.key} className="rounded-lg border border-gray-200">
              <button
                onClick={() => setOpenGroups((prev) => { const n = new Set(prev); if (n.has(g.key)) n.delete(g.key); else n.add(g.key); return n; })}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50"
              >
                <Badge tone={ACTION[head.action].tone}>{`일괄 ${ACTION[head.action].label}`}</Badge>
                <span className="text-[12px] text-gray-700">{g.rows.length}건</span>
                <span className="text-[11px] text-gray-400">{head.actor_label ?? "자동"} · {formatAt(head.created_at)}</span>
                <span className="flex-1" />
                <span className="text-[10px] text-gray-400">{open ? "▲" : "▼"}</span>
              </button>
              {open && (
                <div className="border-t border-gray-100 p-2 space-y-2">
                  {g.rows.map((r) => (
                    <ChangeRow key={r.id} row={r} compact canRestore={restorable.has(r.id)} restoring={update.isPending}
                      onRestore={() => restore(r)} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

function ChangeRow({
  row, compact = false, canRestore, restoring, onRestore,
}: {
  row: EntryChange;
  compact?: boolean;
  canRestore: boolean;
  restoring: boolean;
  onRestore: () => void;
}) {
  const a = ACTION[row.action];
  const changes = (row.changes ?? {}) as Record<string, { before: unknown; after: unknown; auto?: boolean }>;
  const snapshot = (row.action === "DELETE" ? (row.changes as { snapshot?: Record<string, unknown> } | null)?.snapshot : null) ?? null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2">
      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge tone={a.tone}>{a.label}</Badge>
        <span className="text-[13px] font-semibold text-gray-900">{row.subject_name}</span>
        {row.income_type && <span className="text-[11px] text-gray-400">{INCOME_LABEL[row.income_type] ?? row.income_type}</span>}
        <span className="flex-1" />
        {!compact && <span className="text-[11px] text-gray-400">{formatAt(row.created_at)}</span>}
      </div>

      {row.action === "UPDATE" && Object.keys(changes).length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {Object.entries(changes).map(([field, c]) => (
            <li key={field} className="text-[12px] text-gray-700 flex items-baseline gap-1.5 flex-wrap">
              <span className="text-gray-500 shrink-0">{FIELD_LABEL[field] ?? field}</span>
              <span className="tabular-nums text-gray-400">{formatValue(field, c.before)}</span>
              <span className="text-gray-300">→</span>
              <span className="tabular-nums font-semibold">{formatValue(field, c.after)}</span>
              {c.auto && <span className="text-[10px] text-gray-400">(자동 계산)</span>}
            </li>
          ))}
        </ul>
      )}
      {snapshot && (
        <p className="mt-1.5 text-[12px] text-gray-600 tabular-nums">
          삭제 당시 {formatValue("total_amount", snapshot.total_amount)}
        </p>
      )}
      {row.reason && <p className="mt-1.5 text-[12px] text-gray-700">사유: {row.reason}</p>}

      <div className="mt-1.5 flex items-center gap-2">
        <span className="text-[11px] text-gray-400">
          {row.actor_label ?? "자동"} · {SOURCE_LABEL[row.source] ?? row.source}
          {compact && ` · ${formatAt(row.created_at)}`}
        </span>
        <span className="flex-1" />
        {canRestore && (
          <Button variant="secondary" className="!text-[11px] !px-2 !py-0.5" disabled={restoring} onClick={onRestore}>
            복구
          </Button>
        )}
      </div>
    </div>
  );
}
