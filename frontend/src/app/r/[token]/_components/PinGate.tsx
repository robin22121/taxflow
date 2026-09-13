"use client";

import { useState } from "react";

import { api } from "@/lib/api";

import { Modal } from "./Modal";
import styles from "./portal.module.css";

type UnlockResponse = { grant: string; expires_in: number };

export function PinGate({
  token,
  open,
  onClose,
  onGranted,
}: {
  token: string;
  open: boolean;
  onClose: () => void;
  onGranted: (grant: string) => void;
}) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (pin.length < 4) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<UnlockResponse>(`/api/v1/public/r/${token}/unlock`, {
        method: "POST",
        json: { pin },
      });
      onGranted(res.grant);
      setPin("");
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        setPin("");
        setError(null);
        onClose();
      }}
      title="PIN 입력"
      footer={
        <>
          <button
            type="button"
            className={styles.ctaSecondary}
            onClick={() => {
              setPin("");
              setError(null);
              onClose();
            }}
          >
            취소
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            onClick={submit}
            disabled={busy || pin.length < 4}
          >
            {busy ? "확인 중…" : "확인"}
          </button>
        </>
      }
    >
      <p className="text-[13px] text-[var(--muted)] mb-3">
        직원별 급여·전월 명세를 보려면 담당 세무사에게 받은 PIN을 입력해 주세요.
      </p>
      <input
        type="text"
        inputMode="numeric"
        autoFocus
        maxLength={8}
        placeholder="PIN 6자리"
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        className={styles.input}
        style={{ textAlign: "center", letterSpacing: "0.3em", fontSize: 18 }}
      />
      {error && <p className="mt-2 text-[12.5px] text-red-600">{error}</p>}
    </Modal>
  );
}
