"use client";

import { use, useEffect, useState } from "react";

import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui";

type SessionInfo = { client_name: string; period: string };
type SubmitResult = {
  matched: number;
  new_hire_suspected: number;
  resignation_suspected: number;
  ambiguous: number;
  needs_followup?: number;
};

export default function PublicCollectPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [mode, setMode] = useState<"idle" | "text" | "processing">("idle");

  useEffect(() => {
    api<SessionInfo>(`/api/v1/public/r/${token}`)
      .then(setSession)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  async function submit() {
    if (!text.trim()) return;
    setSubmitting(true);
    setMode("processing");
    setError(null);
    try {
      const res = await api<SubmitResult>(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text },
      });
      setResult(res);
      setText("");
      setMode("idle");
    } catch (e) {
      setError((e as Error).message);
      setMode("text");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFile(f: File) {
    setSubmitting(true);
    setMode("processing");
    setError(null);
    try {
      const r = await apiUpload<SubmitResult>(`/api/v1/public/r/${token}/upload`, f);
      setResult(r);
      setMode("idle");
    } catch (err) {
      setError((err as Error).message);
      setMode("idle");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitSameAsPrev() {
    setSubmitting(true);
    setMode("processing");
    setError(null);
    try {
      const res = await api<SubmitResult>(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text: "전월과 동일합니다" },
      });
      setResult(res);
      setMode("idle");
    } catch (e) {
      setError((e as Error).message);
      setMode("idle");
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !session) {
    return (
      <div className="min-h-dvh flex items-center justify-center p-4 bg-[#F7F7F9]">
        <div className="max-w-md rounded-2xl bg-white border border-gray-200 p-6 text-center shadow-lg">
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    );
  }
  if (!session) {
    return <div className="min-h-dvh flex items-center justify-center bg-[#F7F7F9]"><p className="text-gray-500">로딩 중...</p></div>;
  }

  return (
    <div className="flex flex-col min-h-dvh bg-[#F7F7F9]" style={{
      backgroundImage: "radial-gradient(circle at 1px 1px, rgba(16,17,18,0.025) 1px, transparent 0)",
      backgroundSize: "16px 16px",
    }}>
      {/* Header */}
      <div className="px-4 py-3 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-600 text-white flex items-center justify-center text-base font-extrabold shrink-0">
            {session.client_name.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-bold tracking-tight text-gray-900 truncate">{session.client_name}</div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              <span className="text-[11.5px] text-gray-500">{session.period} 자료 수집중</span>
            </div>
          </div>
        </div>
      </div>

      {/* Chat body */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        {/* Date divider */}
        <div className="flex justify-center mb-3">
          <span className="px-3 py-1 rounded-full bg-black/[0.06] text-[11.5px] text-gray-500">
            오늘
          </span>
        </div>

        {/* Safety card */}
        <div className="mx-0 mb-3 p-3 bg-white border border-gray-200 rounded-[14px] shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0 text-sm">🔒</div>
            <div>
              <div className="text-[12px] font-bold text-gray-900">전용 안전 링크</div>
              <div className="text-[11px] text-gray-500 leading-snug">답장 내용은 세무사 사무소만 확인할 수 있어요</div>
            </div>
          </div>
        </div>

        {/* Greeting bubbles (them) */}
        <ChatBubbleThem>
          안녕하세요 <b className="text-blue-600">{session.client_name}</b> 사장님,<br />
          {session.period} 직원 급여 자료 부탁드려요 🙏
        </ChatBubbleThem>
        <ChatBubbleThem>
          아래 <b>편한 방법</b>으로 보내주시면 돼요.<br />
          제일 빠른 건 <b>&quot;전월과 똑같아요&quot;</b> 한 번 탭이에요.
        </ChatBubbleThem>

        {/* Quick actions */}
        <div className="pl-10 space-y-2 mb-3">
          <button
            onClick={submitSameAsPrev}
            disabled={submitting}
            className="flex items-center gap-3 w-full max-w-[78%] p-3.5 rounded-2xl bg-gradient-to-r from-blue-100 to-blue-200 border border-blue-200 text-left shadow-sm hover:shadow-md transition-shadow disabled:opacity-50"
          >
            <div className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center shrink-0 text-lg">⭐</div>
            <div className="flex-1 min-w-0">
              <div className="text-[14px] font-bold text-blue-900">전월과 똑같아요</div>
              <div className="text-[11.5px] text-blue-700">저번 달 자료 그대로 제출 · 한 번 탭</div>
            </div>
            <span className="text-blue-400 text-lg shrink-0">›</span>
          </button>

          <div className="flex gap-2 max-w-[78%]">
            <label className="flex-1 flex flex-col items-center gap-1 py-2.5 px-2 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 transition-colors">
              <span className="text-lg">📷</span>
              <span className="text-[11px] font-semibold text-gray-700">사진·파일</span>
              <input type="file" className="hidden" accept="audio/*,.mp3,.m4a,.wav,.xlsx,.xls,.csv,.png,.jpg,.jpeg"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
            </label>
            <button onClick={() => setMode("text")} className="flex-1 flex flex-col items-center gap-1 py-2.5 px-2 bg-white border border-gray-200 rounded-xl hover:border-gray-300 transition-colors">
              <span className="text-lg">✏️</span>
              <span className="text-[11px] font-semibold text-gray-700">직접 적기</span>
            </button>
          </div>
        </div>

        {/* User text input (expanded) */}
        {mode === "text" && (
          <div className="flex justify-end mb-2">
            <div className="max-w-[82%] w-full space-y-2">
              <textarea
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={"예) 김연호 100만원, 박민수 신규입사 150만원, 이영수는 이번달 퇴사했어요"}
                className="w-full rounded-2xl bg-white border border-gray-300 px-3.5 py-3 text-[14px] text-gray-900 leading-relaxed outline-none focus:border-blue-500 resize-none"
                autoFocus
              />
              <div className="flex gap-2 justify-end">
                <button onClick={() => { setMode("idle"); setText(""); }}
                  className="px-3.5 py-2 rounded-xl border border-gray-300 text-[13px] text-gray-700 hover:bg-gray-50">
                  취소
                </button>
                <Button onClick={submit} disabled={submitting || !text.trim()}>
                  {submitting ? "전송 중..." : "전송"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Processing indicator */}
        {mode === "processing" && (
          <div className="flex gap-2 items-end mb-2">
            <div className="w-8 h-8 rounded-[10px] bg-amber-50 text-amber-700 flex items-center justify-center shrink-0 text-sm">🤖</div>
            <div className="max-w-[78%]">
              <div className="bg-white border border-gray-200 rounded-[4px_16px_16px_16px] p-3 shadow-sm min-w-[200px]">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                  <span className="text-[12.5px] font-bold text-gray-900">자료 읽고 있어요</span>
                </div>
                <div className="h-[5px] rounded-full bg-gray-200 overflow-hidden mb-1.5">
                  <div className="h-full rounded-full bg-gradient-to-r from-amber-200 to-amber-500 animate-pulse" style={{ width: "72%" }} />
                </div>
                <div className="text-[11px] text-gray-500">분석 중… 약 10초</div>
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex justify-end mb-2">
            <div className="bg-red-50 border border-red-600/20 rounded-2xl px-3.5 py-2.5 text-[13px] text-red-600 max-w-[82%]">
              {error}
            </div>
          </div>
        )}

        {/* Result summary card */}
        {result && (
          <div className="flex gap-2 items-end mb-2">
            <div className="w-8 shrink-0" />
            <div className="max-w-[88%] w-full">
              <div className="bg-white border border-gray-200 rounded-[4px_18px_18px_18px] overflow-hidden shadow-md">
                <div className="px-3.5 py-3 border-b border-gray-200 bg-gradient-to-b from-blue-50 to-white">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-blue-600">✅</span>
                    <span className="text-[13px] font-bold text-blue-600">정리 완료</span>
                  </div>
                  <div className="text-[11.5px] text-gray-500">
                    {session.period} {session.client_name} 급여 · 직원 {result.matched + result.new_hire_suspected + result.resignation_suspected + result.ambiguous}명 확인
                  </div>
                </div>

                <div className="grid grid-cols-4 py-2.5 px-1 border-b border-gray-200">
                  {([
                    ["기존", result.matched, "gray-900"],
                    ["신규", result.new_hire_suspected, "blue-600"],
                    ["퇴사", result.resignation_suspected, "gray-500"],
                    ["확인", result.ambiguous + (result.needs_followup ?? 0), "red-600"],
                  ] as const).map(([label, val, tone], i) => (
                    <div key={i} className="flex flex-col items-center gap-0.5" style={{ borderRight: i < 3 ? "1px solid #E3E3E5" : "none" }}>
                      <span className={`text-xl font-extrabold tabular-nums text-${tone}`}>{val}</span>
                      <span className="text-[11px] text-gray-500">{label}</span>
                    </div>
                  ))}
                </div>

                <div className="px-3.5 py-2.5 bg-gray-50 text-[12.5px] text-gray-700">
                  세무사가 검증 후 추가 확인 사항이 있으면 다시 연락드릴게요.
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="h-2" />
      </div>

      {/* Bottom input bar */}
      <div className="px-3 py-2 bg-white border-t border-gray-200 flex items-center gap-2 shrink-0">
        <label className="w-9 h-9 rounded-full bg-gray-50 flex items-center justify-center text-gray-700 cursor-pointer shrink-0 hover:bg-gray-200 transition-colors">
          <span className="text-lg">+</span>
          <input type="file" className="hidden" accept="audio/*,.mp3,.m4a,.wav,.xlsx,.xls,.csv,.png,.jpg,.jpeg"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
        </label>
        <div
          onClick={() => setMode("text")}
          className="flex-1 h-9 bg-gray-50 rounded-full px-3.5 flex items-center text-[13.5px] text-gray-500 cursor-text"
        >
          메시지 입력…
        </div>
        <button
          onClick={() => { if (text.trim()) submit(); else setMode("text"); }}
          className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-[0_4px_12px_-4px_rgba(19,112,206,0.5)]"
        >
          <span className="text-sm">↑</span>
        </button>
      </div>
    </div>
  );
}

function ChatBubbleThem({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 items-end mb-1">
      <div className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-blue-600 to-blue-600 text-white flex items-center justify-center shrink-0 text-[13px] font-extrabold">
        조
      </div>
      <div className="max-w-[78%]">
        <div className="bg-white border border-gray-200 rounded-[4px_16px_16px_16px] px-3.5 py-2.5 text-[14px] text-gray-900 leading-relaxed shadow-sm">
          {children}
        </div>
      </div>
    </div>
  );
}
