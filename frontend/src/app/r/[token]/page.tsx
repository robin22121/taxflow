"use client";

import { use, useEffect, useState } from "react";

import { api, apiUpload } from "@/lib/api";
import { Button, Card, Textarea } from "@/components/ui";

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

  useEffect(() => {
    api<SessionInfo>(`/api/v1/public/r/${token}`)
      .then(setSession)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  async function submit() {
    if (!text.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api<SubmitResult>(`/api/v1/public/r/${token}/submit`, {
        method: "POST",
        json: { text },
      });
      setResult(res);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !session) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md text-center">
          <p className="text-red-600">{error}</p>
        </Card>
      </div>
    );
  }
  if (!session) return <p className="p-6">로딩 중...</p>;

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-lg space-y-4">
        <div>
          <div className="text-xs text-gray-500">{session.period} 원천세 자료 요청</div>
          <h1 className="text-xl font-semibold">{session.client_name}</h1>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          이번 달 직원별 인건비를 자유롭게 입력해주세요. 형식은 정해져 있지 않아요.
        </p>
        <Textarea
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"예) 김연호 100만원, 박민수 신규입사 150만원, 이영수는 이번달 퇴사했어요. 나머지는 저번달과 동일."}
        />
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>또는 파일 업로드:</span>
          <input
            type="file"
            accept="audio/*,.mp3,.m4a,.wav,.xlsx,.xls,.csv,.png,.jpg,.jpeg"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              setSubmitting(true);
              setError(null);
              try {
                const r = await apiUpload<SubmitResult>(`/api/v1/public/r/${token}/upload`, f);
                setResult(r);
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setSubmitting(false);
                e.target.value = "";
              }
            }}
            className="text-xs"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {result && (
          <Card className="bg-green-50 dark:bg-green-950/30 border-green-200">
            <p className="text-sm font-medium text-green-800 dark:text-green-300">전송 완료!</p>
            <p className="text-xs text-green-700 dark:text-green-400 mt-1">
              기존직원 {result.matched}명 · 신규 {result.new_hire_suspected}명 · 퇴사 {result.resignation_suspected}명 · 확인필요 {result.ambiguous + (result.needs_followup ?? 0)}명
            </p>
            <p className="text-xs text-green-700 dark:text-green-400 mt-1">
              세무사가 검증 후 추가 확인 사항이 있으면 다시 연락드릴게요.
            </p>
          </Card>
        )}
        <Button className="w-full" onClick={submit} disabled={submitting || !text.trim()}>
          {submitting ? "전송 중..." : "전송"}
        </Button>
      </Card>
    </div>
  );
}
