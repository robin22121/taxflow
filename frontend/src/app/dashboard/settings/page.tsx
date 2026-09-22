"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe } from "@/lib/queries";
import { Button, Card, Input } from "@/components/ui";
import { type RpaAgentIssued, issueAgent, listAgents, revokeAgent } from "@/lib/rpa-api";

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

      {me?.is_admin && <AgentsCard />}
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** 자동화 PC(증명발급·위하고 에이전트) 연결 토큰 — plan/17 §4-9, plan/16 §8. 관리자만. */
function AgentsCard() {
  const qc = useQueryClient();
  const { data: agents = [] } = useQuery({ queryKey: ["rpa", "agents"], queryFn: listAgents });
  const [name, setName] = useState("");
  const [issued, setIssued] = useState<RpaAgentIssued | null>(null);
  const [copied, setCopied] = useState(false);

  const issue = useMutation({
    mutationFn: () => issueAgent(name.trim() || "자동화 PC"),
    onSuccess: (a) => {
      setIssued(a);
      setName("");
      qc.invalidateQueries({ queryKey: ["rpa", "agents"] });
    },
  });
  const revoke = useMutation({
    mutationFn: revokeAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rpa", "agents"] }),
  });

  const command = issued
    ? `EASYONE_AGENT_TOKEN=${issued.token} uv run python -m certificate_agent easyone --server ${API_BASE}`
    : "";

  function copy() {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card className="p-5 space-y-4">
      <div>
        <h2 className="text-[14px] font-semibold text-gray-900">자동화 PC 연결</h2>
        <p className="text-[13px] text-gray-500 mt-0.5">증명원 발급 등 홈택스 자동화를 실행할 PC 를 연결합니다. 토큰은 발급 직후 한 번만 보입니다.</p>
      </div>

      <div className="flex gap-2">
        <Input placeholder="PC 이름 (예: 사무실 증명발급 PC)" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
        <Button onClick={() => issue.mutate()} disabled={issue.isPending} className="shrink-0">토큰 발급</Button>
      </div>

      {issued && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
          <p className="text-[12px] text-amber-800 font-medium">이 창을 닫으면 토큰을 다시 볼 수 없습니다. 자동화 PC 의 rpa/certificate-agent 폴더에서 실행하세요.</p>
          <pre className="text-[11px] bg-white border border-amber-200 rounded p-2 whitespace-pre-wrap break-all">{command}</pre>
          <Button variant="secondary" onClick={copy} className="!text-[12px]">{copied ? "복사됨" : "명령 복사"}</Button>
        </div>
      )}

      <div className="divide-y divide-gray-100">
        {agents.length === 0 && <p className="text-[12px] text-gray-400">연결된 PC 가 없습니다.</p>}
        {agents.map((a) => (
          <div key={a.id} className="flex items-center justify-between py-2">
            <div>
              <div className={"text-[13px] " + (a.revoked_at ? "text-gray-400 line-through" : "text-gray-900")}>{a.name}</div>
              <div className="text-[11px] text-gray-400">
                {a.last_seen_at ? `마지막 접속 ${new Date(a.last_seen_at).toLocaleString("ko-KR")}` : "아직 접속 안 함"}
              </div>
            </div>
            {!a.revoked_at && (
              <Button variant="danger" onClick={() => revoke.mutate(a.id)} disabled={revoke.isPending} className="!text-[12px] !px-2.5 !py-1">해제</Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
