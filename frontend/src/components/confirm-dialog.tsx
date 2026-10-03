"use client";

// 브라우저 확인창(window.confirm) 대신 쓰는 이지원천 확인 팝업.
// 자동화용 크롬에 에이전트(Playwright)가 붙어 있으면 브라우저 확인창이 자동으로 '취소'되어
// 사용자가 고르기 전에 닫힌다 (2026-09-27 급여항목 삭제). 페이지 안에 그리는 팝업은 영향이 없다.
//
// 사용:  const [confirm, confirmDialog] = useConfirm();
//        if (!(await confirm("삭제할까요?"))) return;   …   return <>{confirmDialog}…</>

import { useCallback, useState, type ReactNode } from "react";

import { Button, Input, Modal } from "@/components/ui";

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

// 한 줄 입력이 필요한 확인 팝업 — 삭제 사유처럼 선택 입력을 받는다. 취소하면 null, 확인하면 입력값(빈 문자열 가능).
//   const [prompt, promptDialog] = usePrompt();
//   const reason = await prompt("삭제할까요?", "삭제 사유 (선택)");  if (reason === null) return;
type PromptPending = { message: string; placeholder: string; resolve: (value: string | null) => void };

export function usePrompt(): [(message: string, placeholder?: string) => Promise<string | null>, ReactNode] {
  const [pending, setPending] = useState<PromptPending | null>(null);
  const [value, setValue] = useState("");

  const prompt = useCallback(
    (message: string, placeholder = "") =>
      new Promise<string | null>((resolve) => {
        setValue("");
        setPending({ message, placeholder, resolve });
      }),
    [],
  );

  const close = (result: string | null) => {
    pending?.resolve(result);
    setPending(null);
  };

  const dialog = pending ? (
    <Modal open={true} onClose={() => close(null)} title="확인"
      footer={<>
        <Button variant="ghost" onClick={() => close(null)}>취소</Button>
        <Button onClick={() => close(value.trim())}>확인</Button>
      </>}>
      <p className="text-[13px] text-gray-700 whitespace-pre-wrap mb-3">{pending.message}</p>
      <Input
        autoFocus
        value={value}
        placeholder={pending.placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") close(value.trim()); }}
      />
    </Modal>
  ) : null;

  return [prompt, dialog];
}
