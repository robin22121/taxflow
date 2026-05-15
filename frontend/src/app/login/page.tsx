"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, setTokens } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import type { TokenPair } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const res = await api<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        json: { email, password },
      });
      setTokens(res.access_token, res.refresh_token);
      router.push("/dashboard");
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
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">
                아이디 (사업자번호)
              </label>
              <Input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="0000000000"
                required
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
