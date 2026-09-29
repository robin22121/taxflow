"use client";

// 로그인 시 고른 "데모버전 / 이지원 버전" 모드에 따른 안내 배너 (plan/16-wehago-rpa.md §3-6).
// 이지원 버전은 rpa_agents 테이블(GET /api/v1/rpa/agents)로 노트북 등록·가동 여부를 판단한다.

import { useQuery } from "@tanstack/react-query";
import { getLoginMode } from "@/lib/login-mode";
import { listAgents } from "@/lib/rpa-api";

// 폴링 주기 기준 임계값 — plan/16-wehago-rpa.md §3-6 "결정" 항목 참고.
const ONLINE_THRESHOLD_MS = 3 * 60 * 1000;

export function AgentStatusBanner() {
  const mode = getLoginMode();
  return mode === "demo" ? <DemoBanner /> : <AgentBanner />;
}

function DemoBanner() {
  return (
    <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 flex items-center justify-between gap-2">
      <span>
        데모 모드 — 이 PC에 위하고 T·홈택스가 로그인돼 있고, 로컬 에이전트가 떠 있어야
        자동화가 동작합니다.
      </span>
      <button
        type="button"
        className="shrink-0 rounded border border-amber-300 px-2 py-1 text-[11px] font-medium hover:bg-amber-100"
        onClick={() => {
          navigator.clipboard?.writeText("bash rpa-agent/scripts/start-chrome.sh").catch(() => {});
        }}
      >
        명령어 복사
      </button>
    </div>
  );
}

function AgentBanner() {
  const { data: agents } = useQuery({ queryKey: ["rpa", "agents"], queryFn: listAgents });
  if (!agents) return null;

  const active = agents.filter((a) => !a.revoked_at);
  if (active.length === 0) {
    return (
      <div className="rounded-md bg-gray-50 border border-gray-200 px-3 py-2 text-xs text-gray-600">
        아직 등록된 이지원 노트북이 없습니다.{" "}
        <a href="/dashboard/settings" className="text-blue-600 hover:underline">
          설정에서 등록
        </a>
      </div>
    );
  }

  const now = Date.now();
  const online = active.some(
    (a) => a.last_seen_at && now - new Date(a.last_seen_at).getTime() < ONLINE_THRESHOLD_MS
  );

  return (
    <div
      className={
        "rounded-md border px-3 py-2 text-xs " +
        (online ? "bg-green-50 border-green-200 text-green-700" : "bg-red-50 border-red-200 text-red-700")
      }
    >
      이지원 노트북 {online ? "가동 중" : "오프라인"} ({active.length}대 등록됨)
    </div>
  );
}
