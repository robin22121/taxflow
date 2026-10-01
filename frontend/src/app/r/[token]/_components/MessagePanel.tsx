"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { useRef, useState } from "react";

import { api, apiSend } from "@/lib/api";

import { Modal } from "./Modal";
import styles from "./portal.module.css";
import type { PortalMessageItem, PortalMessageThread } from "./types";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Bubble({ msg }: { msg: PortalMessageItem }) {
  const isOwner = msg.sender_type === "OWNER";
  return (
    <div className={clsx(styles.chatBubbleRow, isOwner && styles.chatBubbleRowOwner)}>
      <div style={{ maxWidth: "80%" }}>
        {!isOwner && (
          <div className={styles.chatMeta}>{msg.staff_name ?? "담당 직원"}</div>
        )}
        <div
          className={clsx(
            styles.chatBubble,
            isOwner ? styles.chatBubbleOwner : styles.chatBubbleStaff,
          )}
        >
          {msg.body && <div style={{ whiteSpace: "pre-wrap" }}>{msg.body}</div>}
          {msg.attachment_url && (
            <a
              href={msg.attachment_url}
              target="_blank"
              rel="noreferrer"
              className={styles.chatAttachment}
              style={{ color: isOwner ? "#ffffff" : "var(--blue-2)" }}
            >
              📎 {msg.attachment_name ?? "첨부파일"}
            </a>
          )}
        </div>
        <div className={clsx(styles.chatMeta, isOwner && "text-right")}>
          {formatTime(msg.created_at)}
        </div>
      </div>
    </div>
  );
}

export function MessagePanel({ token }: { token: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const threadQ = useQuery({
    queryKey: ["portal", token, "messages"],
    queryFn: () => api<PortalMessageThread>(`/api/v1/public/r/${token}/messages`),
    enabled: open,
    refetchOnWindowFocus: false,
  });

  const staffName = threadQ.data?.staff_name ?? null;
  const items = threadQ.data?.items ?? [];

  async function send(file?: File) {
    if (!text.trim() && !file) return;
    setSending(true);
    setErr(null);
    try {
      const form = new FormData();
      if (text.trim()) form.append("body", text.trim());
      if (file) form.append("file", file);
      await apiSend(`/api/v1/public/r/${token}/messages`, form);
      setText("");
      if (fileRef.current) fileRef.current.value = "";
      await qc.invalidateQueries({ queryKey: ["portal", token, "messages"] });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={styles.chatFab}
        onClick={() => setOpen(true)}
        aria-label="메시지"
      >
        <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
          <path
            d="M3 5.5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-3.5 3v-3H5a2 2 0 0 1-2-2v-6Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="메시지">
        <p className={styles.chatNotice}>
          AI가 아닌 담당 직원{staffName ? ` ${staffName}님` : ""}이 직접 확인 후 답변합니다.
          급한 연락은 기존 카카오톡이나 전화로 부탁드려요 — 답변에 별도 알림은 가지 않습니다.
        </p>

        <div className={styles.chatThread}>
          {threadQ.isLoading && (
            <div className="text-[13px] text-[var(--muted)] py-6 text-center">불러오는 중…</div>
          )}
          {!threadQ.isLoading && items.length === 0 && (
            <div className="text-[13px] text-[var(--muted)] py-6 text-center">
              아직 메시지가 없습니다. 자료 제출 중 궁금한 점을 남겨 주세요.
            </div>
          )}
          {items.map((m) => (
            <Bubble key={m.id} msg={m} />
          ))}
        </div>

        {err && <p className="text-[12px] text-red-600 mt-2">{err}</p>}

        <div className={styles.chatComposer}>
          <button
            type="button"
            className={styles.chatAttachBtn}
            onClick={() => fileRef.current?.click()}
            disabled={sending}
            aria-label="파일 첨부"
          >
            +
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.xlsx,.xls,.csv,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void send(f);
            }}
          />
          <textarea
            className={styles.chatTextarea}
            rows={1}
            placeholder="메시지를 입력하세요"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            disabled={sending}
          />
          <button
            type="button"
            className={styles.ctaPrimary}
            style={{ padding: "9px 16px", fontSize: "13px" }}
            disabled={sending || !text.trim()}
            onClick={() => void send()}
          >
            전송
          </button>
        </div>
      </Modal>
    </>
  );
}
