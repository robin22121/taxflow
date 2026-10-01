"use client";

/* ═══ AI 도우미 — 사용법/법령/고객응대 3탭 Q&A 팝업 ═══
 * 상단 공용 네비(dashboard/layout.tsx)에서 연다. 원래 filings/[id]/page.tsx
 * 안에 있던 걸 전체 화면 공용으로 빼면서, 신고서 상세 전용 버튼은 삭제했다
 * (2026-10-01 사용자 지시).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { Modal } from "@/components/ui";

export type QaIntent = "howto" | "law" | "customer";
export type QaMessage = {
  role: "user" | "assistant";
  content: string;
  ts: number;
  intent?: QaIntent; // user 메시지에만 의미가 있다 — 답변은 직전 user 메시지의 intent 를 상속
};

export const QA_INTENT_META: Record<
  QaIntent,
  { label: string; hint: string; bubble: string; tag: string; dot: string; ph: string }
> = {
  howto: {
    label: "사용법",
    hint: "이지원천/위하고T/홈택스/사장님 포털/증명 등 본 서비스 사용 매뉴얼 (담당자용)",
    bubble: "bg-violet-600",
    tag: "text-violet-700",
    dot: "bg-violet-500",
    ph: "예) 위하고T로 원천세 신고서 전송하는 방법",
  },
  law: {
    label: "법령",
    hint: "소득세·부가세·원천세·상속·4대보험 등 세법·판례·예규·서식 (담당자용, MCP)",
    bubble: "bg-blue-600",
    tag: "text-blue-700",
    dot: "bg-blue-500",
    ph: "예) 퇴사자 4대보험 상실신고 기한",
  },
  customer: {
    label: "고객 응대",
    hint: "수임업체 카톡 문의 가정 — 그대로 복붙 가능한 친절한 답변 초안",
    bubble: "bg-emerald-600",
    tag: "text-emerald-700",
    dot: "bg-emerald-500",
    ph: "고객 카톡 문의를 붙여넣으세요",
  },
};

export function AiAssistantDialog({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<QaMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const [input, setInput] = useState("");
  const [intent, setIntent] = useState<QaIntent>("howto");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const askQuestion = useCallback(
    (question: string, askIntent: QaIntent) => {
      const q = question.trim();
      if (!q) return;
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      setMessages((prev) => [...prev, { role: "user", content: q, ts: Date.now(), intent: askIntent }]);
      setThinking(true);
      api<{ answer: string }>("/api/v1/qa", {
        method: "POST",
        json: { intent: askIntent, question: q, history },
      })
        .then((res) => {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: res.answer, ts: Date.now(), intent: askIntent },
          ]);
        })
        .catch((err: unknown) => {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `답변을 가져오지 못했습니다: ${err instanceof Error ? err.message : String(err)}`,
              ts: Date.now(),
              intent: askIntent,
            },
          ]);
        })
        .finally(() => setThinking(false));
    },
    [messages]
  );

  function submit() {
    const q = input.trim();
    if (!q || thinking) return;
    askQuestion(q, intent);
    setInput("");
  }

  const canSend = !!input.trim() && !thinking;

  return (
    <Modal open onClose={onClose} title="AI 도우미" size="lg">
      <div className="flex flex-col h-[60vh]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col justify-center gap-5 py-4">
              <div>
                <p className="text-[16px] font-bold text-gray-900 tracking-tight">무엇을 도와드릴까요?</p>
                <p className="mt-1 text-[13px] text-gray-500">답변 유형을 고른 뒤 질문을 입력하세요.</p>
              </div>
              <div className="grid grid-cols-3 gap-2.5">
                {(["howto", "law", "customer"] as QaIntent[]).map((k) => {
                  const meta = QA_INTENT_META[k];
                  const selected = k === intent;
                  return (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setIntent(k)}
                      className={`flex flex-col gap-2 rounded-[14px] p-3.5 text-left transition-colors ${
                        selected
                          ? "border-[1.5px] border-gray-900 bg-gray-50"
                          : "border border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          <span className={`w-[7px] h-[7px] rounded-full ${meta.dot}`} />
                          <span className="text-[13px] font-bold text-gray-900">{meta.label}</span>
                        </span>
                        {selected && (
                          <span className="w-4 h-4 rounded-full bg-gray-900 text-white text-[9px] flex items-center justify-center">
                            ✓
                          </span>
                        )}
                      </div>
                      <span className="text-[11.5px] leading-relaxed text-gray-500">{meta.hint}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="space-y-2.5">
              {messages.map((m, i) => {
                const meta = m.intent ? QA_INTENT_META[m.intent] : null;
                return (
                  <div
                    key={i}
                    className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
                  >
                    <div className="max-w-[80%]">
                      {meta && (
                        <div
                          className={`text-[10px] font-semibold mb-0.5 ${meta.tag} ${
                            m.role === "user" ? "text-right" : "text-left"
                          }`}
                        >
                          {meta.label}
                        </div>
                      )}
                      <div
                        className={`rounded-2xl px-3 py-2 text-[13px] whitespace-pre-wrap break-words ${
                          m.role === "user"
                            ? `${meta ? meta.bubble : "bg-blue-600"} text-white`
                            : "bg-gray-100 text-gray-900"
                        }`}
                      >
                        {m.content}
                      </div>
                    </div>
                  </div>
                );
              })}
              {thinking && (
                <div className="flex justify-start">
                  <div className="rounded-2xl px-3 py-2 text-[13px] bg-gray-100 text-gray-500">
                    답변 생성 중...
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="mt-3 pt-3 border-t border-gray-200">
          <textarea
            className="w-full min-h-[42px] max-h-32 text-[13px] border border-gray-200 rounded-lg px-2.5 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
            placeholder={QA_INTENT_META[intent].ph}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            disabled={thinking}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            {messages.length === 0 ? (
              <span className="inline-flex items-center gap-1.5 text-[12px] text-gray-600 bg-gray-100 rounded-full px-2.5 py-1">
                <span className={`w-1.5 h-1.5 rounded-full ${QA_INTENT_META[intent].dot}`} />
                {QA_INTENT_META[intent].label}
              </span>
            ) : (
              <div className="flex items-center gap-3">
                <div className="flex gap-0.5 bg-gray-100 rounded-full p-0.5">
                  {(["howto", "law", "customer"] as QaIntent[]).map((k) => {
                    const meta = QA_INTENT_META[k];
                    const selected = k === intent;
                    return (
                      <button
                        key={k}
                        type="button"
                        onClick={() => setIntent(k)}
                        className={`flex items-center gap-1.5 text-[12px] rounded-full px-2.5 py-1 transition-colors ${
                          selected ? "font-semibold text-gray-900 bg-white shadow-sm" : "text-gray-500 hover:text-gray-900"
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        {meta.label}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  onClick={() => setMessages([])}
                  className="text-[11px] text-gray-500 hover:text-gray-700 underline underline-offset-2"
                >
                  대화 새로 시작
                </button>
              </div>
            )}
            <div className="flex items-center gap-2.5 shrink-0">
              <span className="hidden sm:inline text-[11px] text-gray-400">Enter 전송 · Shift+Enter 줄바꿈</span>
              <button
                type="button"
                onClick={submit}
                disabled={!canSend}
                title={QA_INTENT_META[intent].hint}
                className={`w-8 h-8 rounded-[10px] flex items-center justify-center text-[14px] font-bold transition-colors ${
                  canSend ? "bg-gray-900 text-white hover:bg-black" : "bg-gray-200 text-gray-400"
                }`}
              >
                ↑
              </button>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-gray-400">
            법령 탭은 국가법령정보(law.go.kr) 조문을 찾아 근거로 답합니다. 관련 조문을 못 찾으면 추측하지 않고 확인이 필요하다고 안내하며, AI의 판단이 섞인 부분은 별도로 표시됩니다.
          </p>
        </div>
      </div>
    </Modal>
  );
}
