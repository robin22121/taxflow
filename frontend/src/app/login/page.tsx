"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, setTokens } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import type { CurrentUser, TokenPair } from "@/lib/types";
import { type LoginMode, setLoginMode } from "@/lib/login-mode";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loginCode, setLoginCode] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<LoginMode>("demo");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      // 사업자번호는 하이픈을 빼고 보내고, 관리자 계정(이메일 형식)은 그대로 보낸다.
      const loginId = email.includes("@") ? email.trim() : email.replace(/[^0-9]/g, "");
      const res = await api<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        json: { email: loginId, login_code: loginCode.trim() || null, password },
      });
      setTokens(res.access_token, res.refresh_token);
      const me = await api<CurrentUser>("/api/v1/auth/me");
      setLoginMode(mode);
      router.push(me.is_superadmin ? "/admin" : "/dashboard?landing=1");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-gray-50">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-9 h-9 rounded-xl bg-gray-900 text-white flex items-center justify-center text-base font-extrabold">
            이
          </div>
          <span className="text-xl font-bold tracking-tight text-black">이지원천</span>
        </div>

        <Card className="p-6">
          <h1 className="text-lg font-semibold tracking-tight text-gray-900 mb-1">로그인</h1>
          <p className="text-[13px] text-gray-500 mb-5">세무사 사무소 계정으로 시작하세요</p>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">모드</label>
              <div className="grid grid-cols-2 gap-2 text-[12px]">
                {(
                  [
                    { value: "demo", label: "데모버전" },
                    { value: "agent", label: "이지원 버전" },
                  ] as const
                ).map((opt) => (
                  <label
                    key={opt.value}
                    className={
                      "flex items-center justify-center gap-1.5 rounded-md border px-2 py-2 cursor-pointer " +
                      (mode === opt.value
                        ? "border-gray-900 bg-gray-900 text-white"
                        : "border-gray-300 text-gray-700 hover:bg-gray-50")
                    }
                  >
                    <input
                      type="radio"
                      name="loginMode"
                      value={opt.value}
                      checked={mode === opt.value}
                      onChange={() => setMode(opt.value)}
                      className="sr-only"
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
              <p className="text-[11px] text-gray-400 mt-1.5">
                {mode === "demo"
                  ? "이 PC에 위하고 T·홈택스가 로그인돼 있는 것으로 가정하고 시뮬레이션합니다."
                  : "별도 이지원 노트북에서 자동화가 실행됩니다."}
              </p>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">
                아이디 (사업자번호)
              </label>
              <Input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="0000000000"
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">
                코드 <span className="text-gray-400 font-normal">(직원계정만 — 대표는 비워두세요)</span>
              </label>
              <Input
                type="text"
                value={loginCode}
                onChange={(e) => setLoginCode(e.target.value.slice(0, 1))}
                placeholder="a, b, c…"
                autoComplete="off"
                maxLength={1}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">
                비밀번호
              </label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {err && <p className="text-[13px] text-red-600">{err}</p>}
            <Button className="w-full" disabled={loading}>
              {loading ? "로그인 중..." : "로그인"}
            </Button>
          </form>

          <p className="text-center text-[12px] text-gray-500 mt-4">
            계정이 없으신가요?{" "}
            <a href="/register" className="text-blue-600 hover:underline font-medium">
              회원가입
            </a>
          </p>
        </Card>
      </div>
    </div>
  );
}
