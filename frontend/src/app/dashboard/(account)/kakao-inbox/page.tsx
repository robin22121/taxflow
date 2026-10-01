"use client";

import { useDismissKakaoPending, useKakaoInbox, useMe } from "@/lib/queries";
import { Button, Card } from "@/components/ui";

export default function KakaoInboxPage() {
  const { data: me } = useMe();
  const { data: rows = [], isLoading } = useKakaoInbox();
  const dismiss = useDismissKakaoPending();

  if (me && me.role !== "OWNER") {
    return <p className="text-[13px] text-gray-500">대표(세무사) 계정만 접근할 수 있습니다.</p>;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">미분류함</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          카카오톡으로 들어왔지만 거래처명이 확인되지 않아 자동 매칭에 실패한 자료입니다.
          담당자가 정해지지 않은 사무소 공용 데이터라 대표 계정에서만 확인할 수 있습니다.
        </p>
      </div>

      <Card className="p-0 overflow-hidden">
        {isLoading && <div className="text-center py-6 text-gray-400 text-[13px]">불러오는 중...</div>}
        {!isLoading && rows.length === 0 && (
          <div className="text-center py-6 text-gray-400 text-[13px]">미분류 자료가 없습니다.</div>
        )}
        {rows.map((r) => (
          <div key={r.id} className="border-b border-gray-50 last:border-0 p-4 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div className="text-[12px] text-gray-400 tabular-nums">
                {new Date(r.created_at).toLocaleString("ko-KR")} · {r.plusfriend_key}
              </div>
              <Button
                variant="secondary"
                className="!text-[12px] !px-2.5 !py-1"
                onClick={() => dismiss.mutate(r.id)}
                disabled={dismiss.isPending}
              >
                처리완료(삭제)
              </Button>
            </div>
            {r.utterance && <p className="text-[13px] text-gray-800 whitespace-pre-wrap">{r.utterance}</p>}
            {r.file_text && <p className="text-[13px] text-gray-500 whitespace-pre-wrap">{r.file_text}</p>}
            {r.attachments_meta && (
              <p className="text-[12px] text-gray-400">첨부 {Object.keys(r.attachments_meta).length}건</p>
            )}
          </div>
        ))}
      </Card>
    </div>
  );
}
