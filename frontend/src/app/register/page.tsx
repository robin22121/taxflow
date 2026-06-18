"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import type { RegisterResponse } from "@/lib/types";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    business_number: "",
    password: "",
    passwordConfirm: "",
    office_name: "",
    address: "",
    representative: "",
    phone: "",
    email: "",
  });
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RegisterResponse | null>(null);

  function set(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [key]: e.target.value }));
  }

  function validate(): string | null {
    if (!form.business_number.replace(/-/g, "").match(/^\d{10}$/))
      return "사업자번호는 10자리 숫자여야 합니다";
    if (form.password.length < 6) return "비밀번호는 6자리 이상이어야 합니다";
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/~`]/.test(form.password))
      return "비밀번호에 특수문자를 포함해야 합니다";
    if (form.password !== form.passwordConfirm) return "비밀번호가 일치하지 않습니다";
    if (!form.office_name.trim()) return "상호를 입력해주세요";
    if (!form.representative.trim()) return "담당자명을 입력해주세요";
    if (!form.phone.trim()) return "연락처를 입력해주세요";
    if (!form.email.trim()) return "이메일을 입력해주세요";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) return "올바른 이메일 형식이 아닙니다";
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validationErr = validate();
    if (validationErr) {
      setErr(validationErr);
      return;
    }
    setErr(null);
    setLoading(true);
    try {
      const res = await api<RegisterResponse>("/api/v1/auth/register", {
        method: "POST",
        json: {
          business_number: form.business_number,
          password: form.password,
          office_name: form.office_name,
          address: form.address,
          representative: form.representative,
          phone: form.phone,
          email: form.email,
        },
      });
      setResult(res);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 bg-gray-50">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gray-900 text-white flex items-center justify-center text-base font-extrabold">
              이
            </div>
            <span className="text-xl font-bold tracking-tight text-black">이지원천</span>
          </div>
          <Card className="p-6 text-center">
            <div className="text-4xl mb-4">📨</div>
            <h1 className="text-lg font-semibold text-gray-900 mb-2">가입이 접수되었습니다</h1>
            <p className="text-[13px] text-gray-500 mb-4">
              {result.message ?? "서버 관리자 승인 후 로그인할 수 있습니다."}
            </p>
            <div className="bg-amber-50 border border-amber-200 rounded-xl py-3 px-4 mb-4">
              <div className="text-[12px] font-medium text-amber-700">승인 대기 중</div>
              <div className="text-[11px] text-amber-600 mt-0.5">
                승인이 완료되면 로그인하여 이용할 수 있습니다.
              </div>
            </div>
            <div className="bg-gray-50 border border-gray-200 rounded-xl py-4 px-6 mb-4">
              <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">사무소 인가코드</div>
              <div className="text-[28px] font-bold tracking-[0.15em] text-gray-900 font-mono">
                {result.short_code}
              </div>
            </div>
            <p className="text-[12px] text-gray-400 mb-6">
              인가코드가 담당자 연락처로 문자 발송되었습니다.
            </p>
            <Button className="w-full" onClick={() => router.push("/login")}>
              로그인 페이지로
            </Button>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-9 h-9 rounded-xl bg-gray-900 text-white flex items-center justify-center text-base font-extrabold">
            이
          </div>
          <span className="text-xl font-bold tracking-tight text-black">이지원천</span>
        </div>

        <Card className="p-6">
          <h1 className="text-lg font-semibold tracking-tight text-gray-900 mb-1">회원가입</h1>
          <p className="text-[13px] text-gray-500 mb-5">세무사사무소 정보를 입력해주세요</p>

          <form className="space-y-3" onSubmit={onSubmit}>
            <Field label="아이디 (사업자번호)" required>
              <Input
                type="text"
                value={form.business_number}
                onChange={set("business_number")}
                placeholder="000-00-00000"
                required
              />
            </Field>
            <Field label="비밀번호" required hint="특수문자 포함 6자리 이상">
              <Input
                type="password"
                value={form.password}
                onChange={set("password")}
                required
              />
            </Field>
            <Field label="비밀번호 확인" required>
              <Input
                type="password"
                value={form.passwordConfirm}
                onChange={set("passwordConfirm")}
                required
              />
            </Field>
            <Field label="상호" required>
              <Input
                type="text"
                value={form.office_name}
                onChange={set("office_name")}
                placeholder="OO세무사사무소"
                required
              />
            </Field>
            <Field label="주소">
              <Input
                type="text"
                value={form.address}
                onChange={set("address")}
                placeholder="서울특별시 강남구..."
              />
            </Field>
            <Field label="담당자" required>
              <Input
                type="text"
                value={form.representative}
                onChange={set("representative")}
                placeholder="홍길동"
                required
              />
            </Field>
            <Field label="담당자 연락처" required hint="인가코드가 이 번호로 발송됩니다">
              <Input
                type="tel"
                value={form.phone}
                onChange={set("phone")}
                placeholder="010-0000-0000"
                required
              />
            </Field>
            <Field label="이메일" required hint="거래처 회신 시 참조로 발송됩니다">
              <Input
                type="email"
                value={form.email}
                onChange={set("email")}
                placeholder="example@office.com"
                required
              />
            </Field>

            {err && <p className="text-[13px] text-red-600">{err}</p>}

            <Button className="w-full" disabled={loading}>
              {loading ? "가입 중..." : "가입하기"}
            </Button>
          </form>

          <p className="text-center text-[12px] text-gray-500 mt-4">
            이미 계정이 있으신가요?{" "}
            <Link href="/login" className="text-blue-600 hover:underline font-medium">
              로그인
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-gray-700 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-[11px] text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}
