"use client";

import { useState } from "react";

import {
  useFilingNoticeTargets,
  useMessageHistory,
  useMessageTemplates,
  useSendFilingNotice,
} from "@/lib/queries";
import { formatPhone } from "@/lib/format";
import { Badge, Button, Card, Input, Modal, Textarea } from "@/components/ui";
import type { FilingNoticeSendResult, MessageTaxType } from "@/lib/types";

type Channel = "sms" | "alimtalk";

const TAX_TYPES: { value: MessageTaxType; label: string }[] = [
  { value: "WITHHOLDING", label: "원천세" },
  { value: "VAT", label: "부가세" },
  { value: "INCOME", label: "종합소득세" },
  { value: "CORPORATE", label: "법인세" },
];

const SCOPES: Record<MessageTaxType, { value: string; label: string }[]> = {
  WITHHOLDING: [
    { value: "all", label: "전체" },
    { value: "monthly", label: "매월납부" },
    { value: "semiannual", label: "반기납부" },
  ],
  VAT: [
    { value: "all", label: "전체 (면세 제외)" },
    { value: "general", label: "일반과세" },
    { value: "simplified", label: "간이과세" },
  ],
  INCOME: [
    { value: "all", label: "전체 개인" },
    { value: "sincere", label: "성실신고 대상만" },
  ],
  CORPORATE: [
    { value: "all", label: "전체 법인" },
    { value: "fy12", label: "12월 결산" },
    { value: "fy_other", label: "12월 외 결산" },
  ],
};

const PLACEHOLDERS = ["{사무소명}", "{거래처명}", "{대표자}", "{신고기한}", "{세목}"];
const SMS_MAX_BYTES = 90;
const PAGE_SIZE = 50;

function utf8Bytes(text: string): number {
  return new TextEncoder().encode(text).length;
}

function channelKo(channel: string): string {
  if (channel === "alimtalk_skipped") return "카톡 건너뜀";
  if (channel.startsWith("alimtalk")) return "카톡";
  if (channel.startsWith("sms") || channel.startsWith("lms")) return "문자";
  return channel;
}

function taxTypeKo(t: string | null): string {
  return TAX_TYPES.find((x) => x.value === t)?.label ?? t ?? "—";
}

export default function MessagesPage() {
  const [channel, setChannel] = useState<Channel>("sms");
  const [tab, setTab] = useState<"send" | "history">("send");

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold tracking-tight text-gray-900">문자발송</h1>
          <p className="text-[12px] text-gray-500 mt-1">
            거래처에 신고 안내를 일괄 발송합니다.
          </p>
        </div>
        <div className="flex flex-col items-start sm:items-end gap-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[12px] text-gray-500 mr-1">채널</span>
            {(["sms", "alimtalk"] as const).map((value) => (
              <button
                key={value}
                onClick={() => setChannel(value)}
                className={
                  "px-3 py-1.5 rounded-full text-[12px] font-medium transition-colors " +
                  (channel === value ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-100")
                }
              >
                {value === "sms" ? "문자" : "카톡"}
              </button>
            ))}
          </div>
          {channel === "alimtalk" && (
            <span className="text-[11px] text-gray-500">카톡(알림톡) 실패 시 문자로 자동 대체 발송</span>
          )}
        </div>
      </div>

      <div className="flex gap-1.5 border-b border-gray-200">
        {(["send", "history"] as const).map((value) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={
              "px-3 py-2 text-[13px] font-medium -mb-px border-b-2 transition-colors " +
              (tab === value
                ? "border-gray-900 text-gray-900"
                : "border-transparent text-gray-500 hover:text-gray-900")
            }
          >
            {value === "send" ? "발송" : "발송 이력"}
          </button>
        ))}
      </div>

      {tab === "send" ? <SendTab channel={channel} /> : <HistoryTab />}
    </div>
  );
}

function SendTab({ channel }: { channel: Channel }) {
  const [taxType, setTaxType] = useState<MessageTaxType>("WITHHOLDING");
  const [scope, setScope] = useState("all");
  const [deadline, setDeadline] = useState("");
  // 세목·범위별로 사용자가 바꾼 선택만 저장 — 없으면 발송 가능 거래처 전체가 기본 선택.
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  // 세목별로 사용자가 고친 본문만 저장 — 없으면 템플릿 원문.
  const [bodies, setBodies] = useState<Partial<Record<MessageTaxType, string>>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [result, setResult] = useState<FilingNoticeSendResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const { data: templates } = useMessageTemplates();
  const { data: targetsData, isLoading, error: targetsError } = useFilingNoticeTargets(taxType, scope);
  const send = useSendFilingNotice();

  const targets = targetsData?.items ?? [];
  const eligible = targets.filter((t) => t.eligible);
  const selKey = `${taxType}:${scope}`;
  const selected = new Set(picked[selKey] ?? eligible.map((t) => t.client_id));
  const selectedIds = eligible.filter((t) => selected.has(t.client_id)).map((t) => t.client_id);

  const template = templates?.find((t) => t.tax_type === taxType);
  const body = bodies[taxType] ?? template?.sms_body ?? "";
  const bytes = utf8Bytes(body);

  function setSelection(ids: string[]) {
    setPicked((prev) => ({ ...prev, [selKey]: ids }));
  }

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelection([...next]);
  }

  function openConfirm() {
    if (selectedIds.length === 0) {
      setErr("발송할 거래처를 선택해주세요");
      return;
    }
    if (!body.trim()) {
      setErr("본문을 입력해주세요");
      return;
    }
    if (body.includes("{신고기한}") && !deadline.trim()) {
      setErr("본문에 {신고기한}이 있습니다. 신고기한을 입력해주세요");
      return;
    }
    setErr(null);
    setConfirmOpen(true);
  }

  async function doSend() {
    setErr(null);
    try {
      const res = await send.mutateAsync({
        tax_type: taxType,
        channel,
        client_ids: selectedIds,
        body,
        deadline: deadline.trim(),
      });
      setResult(res);
      setConfirmOpen(false);
    } catch (e) {
      setErr((e as Error).message);
      setConfirmOpen(false);
    }
  }

  const failedRows = result?.results.filter((r) => !r.accepted) ?? [];

  return (
    <div className="space-y-4">
      <Card className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">세목</label>
          <select
            value={taxType}
            onChange={(e) => {
              setTaxType(e.target.value as MessageTaxType);
              setScope("all");
              setResult(null);
            }}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 outline-none focus:border-blue-500"
          >
            {TAX_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">대상 범위</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] text-gray-700 outline-none focus:border-blue-500"
          >
            {SCOPES[taxType].map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">신고기한</label>
          <Input
            placeholder="예: 10월 10일"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <span className="text-[13px] font-semibold text-gray-900">
            대상 거래처 <span className="text-gray-500 font-normal">
              {selectedIds.length} / {eligible.length}곳 선택 (전체 {targets.length})
            </span>
          </span>
          <div className="flex gap-1.5">
            <Button variant="ghost" className="px-2 py-1 text-[12px]" onClick={() => setSelection(eligible.map((t) => t.client_id))}>
              전체 선택
            </Button>
            <Button variant="ghost" className="px-2 py-1 text-[12px]" onClick={() => setSelection([])}>
              선택 해제
            </Button>
          </div>
        </div>
        {isLoading && <p className="p-4 text-[13px] text-gray-500">불러오는 중...</p>}
        {targetsError && <p className="p-4 text-[13px] text-red-600">{(targetsError as Error).message}</p>}
        {!isLoading && !targetsError && targets.length === 0 && (
          <p className="p-4 text-[13px] text-gray-500">해당 범위의 거래처가 없습니다.</p>
        )}
        {targets.length > 0 && (
          <div className="max-h-[360px] overflow-auto">
            <table className="w-full text-[13px]">
              <thead className="bg-gray-50 text-gray-500 text-[12px] sticky top-0">
                <tr>
                  <th className="w-10 px-4 py-2" />
                  <th className="text-left px-2 py-2 font-medium">거래처</th>
                  <th className="text-left px-2 py-2 font-medium">대표자</th>
                  <th className="text-left px-2 py-2 font-medium">연락처</th>
                  <th className="text-left px-2 py-2 font-medium">비고</th>
                </tr>
              </thead>
              <tbody>
                {targets.map((t) => (
                  <tr key={t.client_id} className={"border-t border-gray-100 " + (t.eligible ? "" : "text-gray-400")}>
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-blue-600"
                        disabled={!t.eligible}
                        checked={t.eligible && selected.has(t.client_id)}
                        onChange={() => toggle(t.client_id)}
                      />
                    </td>
                    <td className="px-2 py-2 text-gray-900">{t.business_name}</td>
                    <td className="px-2 py-2">{t.representative || "—"}</td>
                    <td className="px-2 py-2">{t.contact_phone ? formatPhone(t.contact_phone) : "—"}</td>
                    <td className="px-2 py-2 text-[12px]">{t.eligible ? "" : t.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-[13px] font-semibold text-gray-900">본문</label>
          <span className={"text-[12px] " + (bytes > SMS_MAX_BYTES ? "text-amber-700" : "text-gray-500")}>
            {bytes}B · {bytes > SMS_MAX_BYTES ? "LMS" : `SMS (≤${SMS_MAX_BYTES}B)`}
          </span>
        </div>
        <Textarea
          rows={7}
          value={body}
          onChange={(e) => setBodies((prev) => ({ ...prev, [taxType]: e.target.value }))}
        />
        <p className="text-[11px] text-gray-500">
          치환 문구: {PLACEHOLDERS.join(" ")} — 거래처별로 자동 치환됩니다 (바이트는 치환 전 기준).
        </p>
        <div className="flex items-center justify-end gap-3 pt-1">
          {err && <span className="text-[12px] text-red-600">{err}</span>}
          <Button onClick={openConfirm} disabled={send.isPending}>
            {send.isPending ? "발송 중..." : "발송"}
          </Button>
        </div>
      </Card>

      {result && (
        <Card className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-gray-900">발송 결과</span>
            <Badge tone="success">성공 {result.sent}</Badge>
            {result.failed > 0 && <Badge tone="danger">실패 {result.failed}</Badge>}
          </div>
          {failedRows.length > 0 && (
            <ul className="text-[12px] space-y-1">
              {failedRows.map((r) => (
                <li key={r.client_id} className="text-gray-700">
                  <span className="font-medium text-gray-900">{r.business_name}</span>
                  {" · "}
                  {channelKo(r.channel)}
                  {" · "}
                  <span className="text-red-600">{r.error ?? "실패"}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="발송 확인"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={send.isPending}>
              취소
            </Button>
            <Button onClick={doSend} disabled={send.isPending}>
              {send.isPending ? "발송 중..." : "발송"}
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-gray-900">
          {selectedIds.length}곳에 발송합니다.
        </p>
        <p className="text-[12px] text-gray-500 mt-1">
          {taxTypeKo(taxType)} 신고 안내 · {channel === "sms" ? "문자" : "카톡 (실패 시 문자 대체)"}
        </p>
      </Modal>
    </div>
  );
}

function HistoryTab() {
  const [page, setPage] = useState(0);
  const { data, isLoading, error } = useMessageHistory(PAGE_SIZE, page * PAGE_SIZE);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return (
    <Card className="p-0 overflow-hidden">
      {isLoading && <p className="p-4 text-[13px] text-gray-500">불러오는 중...</p>}
      {error && <p className="p-4 text-[13px] text-red-600">{(error as Error).message}</p>}
      {!isLoading && !error && items.length === 0 && (
        <p className="p-8 text-center text-[13px] text-gray-500">발송 이력이 없습니다.</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 text-gray-500 text-[12px]">
              <tr>
                <th className="text-left px-4 py-2 font-medium whitespace-nowrap">발송일시</th>
                <th className="text-left px-2 py-2 font-medium">거래처</th>
                <th className="text-left px-2 py-2 font-medium">세목</th>
                <th className="text-left px-2 py-2 font-medium">채널</th>
                <th className="text-left px-2 py-2 font-medium">수신번호</th>
                <th className="text-left px-2 py-2 font-medium">본문</th>
                <th className="text-left px-2 py-2 font-medium">결과</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} className="border-t border-gray-100 align-top">
                  <td className="px-4 py-2 whitespace-nowrap text-gray-600">
                    {new Date(m.created_at).toLocaleString("ko-KR")}
                  </td>
                  <td className="px-2 py-2 text-gray-900">{m.business_name ?? "—"}</td>
                  <td className="px-2 py-2">{taxTypeKo(m.tax_type)}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    {channelKo(m.channel)}
                    {m.requested_channel === "alimtalk" && !m.channel.startsWith("alimtalk") && (
                      <span className="text-[11px] text-gray-500"> (카톡 실패 → 대체)</span>
                    )}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">{m.to_phone ? formatPhone(m.to_phone) : "—"}</td>
                  <td className="px-2 py-2 max-w-[320px]">
                    <p className="truncate" title={m.body}>{m.body}</p>
                  </td>
                  <td className="px-2 py-2">
                    {m.accepted ? (
                      <Badge tone="success">성공</Badge>
                    ) : (
                      <span title={m.error ?? undefined}>
                        <Badge tone="danger">실패</Badge>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-gray-200">
          <span className="text-[12px] text-gray-500">
            {page + 1} / {lastPage + 1} 페이지 (총 {total}건)
          </span>
          <Button variant="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            이전
          </Button>
          <Button variant="secondary" disabled={page >= lastPage} onClick={() => setPage((p) => p + 1)}>
            다음
          </Button>
        </div>
      )}
    </Card>
  );
}
