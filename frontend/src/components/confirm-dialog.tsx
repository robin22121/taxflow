"use client";

// 브라우저 확인창(window.confirm) 대신 쓰는 이지원천 확인 팝업.
// 자동화용 크롬에 에이전트(Playwright)가 붙어 있으면 브라우저 확인창이 자동으로 '취소'되어
// 사용자가 고르기 전에 닫힌다 (2026-09-27 급여항목 삭제). 페이지 안에 그리는 팝업은 영향이 없다.
//
// 사용:  const [confirm, confirmDialog] = useConfirm();
//        if (!(await confirm("삭제할까요?"))) return;   …   return <>{confirmDialog}…</>

import { useCallback, useState, type ReactNode } from "react";

import { Button, Modal } from "@/components/ui";

type Pending = { message: string; resolve: (ok: boolean) => void };

export function useConfirm(): [(message: string) => Promise<boolean>, ReactNode] {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback(
    (message: string) => new Promise<boolean>((resolve) => setPending({ message, resolve })),
    [],
  );

  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };

  const dialog = pending ? (
    <Modal open={true} onClose={() => close(false)} title="확인"
      footer={<>
        <Button variant="ghost" onClick={() => close(false)}>취소</Button>
        <Button onClick={() => close(true)}>확인</Button>
      </>}>
      <p className="text-[13px] text-gray-700 whitespace-pre-wrap">{pending.message}</p>
    </Modal>
  ) : null;

  return [confirm, dialog];
}
