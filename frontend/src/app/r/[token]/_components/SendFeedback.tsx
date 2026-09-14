"use client";

import styles from "./portal.module.css";

/** 제출 피드백 — 보내는 동안 움직이는 이모티콘 오버레이, 끝나면 완료 팝업. 모달(z-index 60) 위에 뜬다. */
export function SendFeedback({
  sending,
  sentOpen,
  onCloseSent,
}: {
  sending: boolean;
  sentOpen: boolean;
  onCloseSent: () => void;
}) {
  if (!sending && !sentOpen) return null;
  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/40 px-6"
      onClick={sending ? undefined : onCloseSent}
      role={sending ? "status" : "alertdialog"}
      aria-live="polite"
    >
      <div
        className="w-full max-w-[300px] rounded-2xl bg-[var(--card)] px-6 py-7 text-center shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {sending ? (
          <>
            <div className="text-[44px] leading-none animate-bounce" aria-hidden>
              📨
            </div>
            <div className="mt-4 text-[15px] font-bold text-[var(--navy)]">자료를 보내는 중입니다</div>
            <div className="mt-1 text-[12.5px] text-[var(--muted)]">잠시만 기다려 주세요…</div>
          </>
        ) : (
          <>
            <div className="text-[44px] leading-none" aria-hidden>
              ✅
            </div>
            <div className="mt-4 text-[15px] font-bold text-[var(--navy)]">전송이 완료되었습니다</div>
            <div className="mt-1 text-[12.5px] text-[var(--muted)]">세무사 사무소에서 확인 후 반영합니다.</div>
            <button
              type="button"
              className={styles.ctaPrimary}
              style={{ width: "100%", marginTop: 20 }}
              onClick={onCloseSent}
            >
              확인
            </button>
          </>
        )}
      </div>
    </div>
  );
}
