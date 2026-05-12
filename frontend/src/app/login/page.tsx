"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, setTokens } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import type { TokenPair } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin1234!");
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
    <div className="flex min-h-screen items-center justify-center px-4 bg-paper-2">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-9 h-9 rounded-xl bg-ink text-white flex items-center justify-center text-base font-extrabold">
            이
          </div>
          <span className="text-xl font-bold tracking-tight">이지원천</span>
        </div>

        <Card className="p-6">
          <h1 className="text-lg font-semibold tracking-tight mb-1">로그인</h1>
          <p className="text-[13px] text-ink-3 mb-5">세무사 사무소 계정으로 시작하세요</p>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-[12px] font-medium text-ink-2 mb-1.5">
                이메일
              </label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-ink-2 mb-1.5">
                비밀번호
              </label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {err && <p className="text-[13px] text-alert">{err}</p>}
            <Button className="w-full" disabled={loading}>
              {loading ? "로그인 중..." : "로그인"}
            </Button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-4">
            <div className="flex-1 border-t border-ink-5" />
            <span className="text-[11px] text-ink-3">또는</span>
            <div className="flex-1 border-t border-ink-5" />
          </div>

          {/* Kakao button (visual only) */}
          <button
            type="button"
            className="w-full flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-[13px] font-medium transition-colors"
            style={{ background: "#FEE500", color: "#191919" }}
            onClick={() => alert("카카오 로그인은 추후 지원 예정입니다.")}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 3C6.48 3 2 6.58 2 10.94c0 2.8 1.86 5.27 4.66 6.67l-1.19 4.36a.35.35 0 00.53.38l5.05-3.33c.31.03.63.04.95.04 5.52 0 10-3.58 10-7.99C22 6.58 17.52 3 12 3z" />
            </svg>
            카카오로 시작
          </button>

          <p className="text-center text-[11px] text-ink-3 mt-4">
            비밀번호를 잊으셨나요?
          </p>
        </Card>
      </div>
    </div>
  );
}
