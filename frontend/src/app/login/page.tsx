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
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-xl font-semibold mb-1">TaxFlow AI</h1>
        <p className="text-sm text-gray-500 mb-6">세무사 사무소 로그인</p>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
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
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              비밀번호
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {err && <p className="text-sm text-red-600">{err}</p>}
          <Button className="w-full" disabled={loading}>
            {loading ? "로그인 중..." : "로그인"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
