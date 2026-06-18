"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";

/* ============================================================
   베타 신청 — 랜딩 페이지 가입 폼 + 실시간 대기자 카운터
   백엔드: POST /api/v1/beta-signup, GET /api/v1/beta-signup/count
   ============================================================ */

type CountOut = { count: number; actual: number };

const SOFTWARE_OPTIONS = [
  "더존 SmartA",
  "더존 위하고(WEHAGO)",
  "세무사랑Pro",
  "택스원",
  "기타",
  "아직 없음",
];

const TRACK_LABEL: Record<string, string> = {
  beta: "베타 회원 (6개월 무료 + 이후 12개월 50% 할인)",
  earlybird: "얼리버드 회원 (6개월 무료 + 이후 6개월 50% 할인)",
  general: "사전 신청",
};

export function WaitlistCounter() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<CountOut>("/api/v1/beta-signup/count")
        .then((d) => {
          if (alive) setCount(d.count);
        })
        .catch(() => {
          /* 카운터 실패는 조용히 무시 — 폼은 정상 동작 */
        });
    load();
    const t = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-blue-600/20 bg-blue-600/8 px-3.5 py-1.5 text-[13px] font-semibold text-blue-700">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-600" />
      </span>
      현재{" "}
      <span className="t-num font-extrabold">
        {count === null ? "—" : count.toLocaleString("ko-KR")}
      </span>
      개 사무소가 대기 중
    </span>
  );
}

export function BetaSignupForm() {
  const [form, setForm] = useState({
    office_name: "",
    contact_name: "",
    phone: "",
    email: "",
    employee_count: "",
    client_count: "",
    current_software: "",
  });
  const [status, setStatus] = useState<"idle" | "submitting" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [track, setTrack] = useState<string>("general");

  const set = (k: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus("submitting");
    try {
      const res = await api<{ track: string }>("/api/v1/beta-signup", {
        method: "POST",
        json: {
          office_name: form.office_name.trim(),
          contact_name: form.contact_name.trim(),
          phone: form.phone.trim(),
          email: form.email.trim() || null,
          employee_count: form.employee_count ? Number(form.employee_count) : null,
          client_count: form.client_count ? Number(form.client_count) : null,
          current_software: form.current_software || null,
        },
      });
      setTrack(res.track);
      setStatus("done");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "신청 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
      );
      setStatus("idle");
    }
  }

  if (status === "done") {
    return (
      <div className="rounded-[18px] border border-blue-600/20 bg-blue-600/[0.04] p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-600 text-[22px] text-white">
          ✓
        </div>
        <h3 className="text-[18px] font-bold text-gray-900">신청이 접수되었습니다</h3>
        <p className="mt-2 text-[14px] leading-relaxed text-gray-600">
          <span className="font-semibold text-blue-700">{TRACK_LABEL[track] ?? TRACK_LABEL.general}</span>
          으로 등록되었습니다.
          <br />
          오픈 일정과 온보딩 안내를 연락처로 보내드리겠습니다.
        </p>
      </div>
    );
  }

  const inputCls =
    "w-full rounded-xl border border-gray-300 bg-white px-3.5 py-2.5 text-[14px] text-gray-900 outline-none transition-colors placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15";
  const labelCls = "mb-1.5 block text-[12.5px] font-medium text-gray-700";

  return (
    <form onSubmit={handleSubmit} className="rounded-[18px] border border-gray-200 bg-white p-6 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)] sm:p-8">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className={labelCls}>사무소명 *</label>
          <input
            required
            value={form.office_name}
            onChange={set("office_name")}
            placeholder="예) 조명신세무회계사무소"
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>담당자명 *</label>
          <input
            required
            value={form.contact_name}
            onChange={set("contact_name")}
            placeholder="예) 김철수"
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>연락처 *</label>
          <input
            required
            value={form.phone}
            onChange={set("phone")}
            placeholder="010-0000-0000"
            inputMode="tel"
            className={inputCls}
          />
        </div>
        <div className="sm:col-span-2">
          <label className={labelCls}>이메일</label>
          <input
            type="email"
            value={form.email}
            onChange={set("email")}
            placeholder="name@example.com"
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>사무소 직원 수</label>
          <input
            type="number"
            min={0}
            value={form.employee_count}
            onChange={set("employee_count")}
            placeholder="예) 5"
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>수임 거래처 수</label>
          <input
            type="number"
            min={0}
            value={form.client_count}
            onChange={set("client_count")}
            placeholder="예) 120"
            className={inputCls}
          />
        </div>
        <div className="sm:col-span-2">
          <label className={labelCls}>현재 사용 중인 세무 SW</label>
          <select
            value={form.current_software}
            onChange={set("current_software")}
            className={`${inputCls} appearance-none`}
          >
            <option value="">선택해 주세요</option>
            {SOFTWARE_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-600">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={status === "submitting"}
        className="mt-6 inline-flex w-full items-center justify-center rounded-full border border-blue-600 bg-blue-600 px-6 py-3 text-[14px] font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_10px_28px_-10px_rgba(19,112,206,0.55)] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status === "submitting" ? "신청 중…" : "베타 신청하기 →"}
      </button>
      <p className="mt-3 text-center text-[12px] text-gray-400">
        제출하신 정보는 베타 온보딩 안내 용도로만 사용됩니다.
      </p>
    </form>
  );
}
