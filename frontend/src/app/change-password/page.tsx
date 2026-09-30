"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { Button, Card, Input } from "@/components/ui";

export default function ChangePasswordPage() {
  const router = useRouter();
  const { data: me } = useMe();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPassword2, setNewPassword2] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (newPassword !== newPassword2) {
      setErr("새 비밀번호가 서로 다릅니다");
      return;
    }
    setLoading(true);
    try {
      await api("/api/v1/auth/change-password", {
        method: "POST",
        json: { current_password: currentPassword, new_password: newPassword },
      });
      router.push("/dashboard");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  if (typeof window !== "undefined" && !getToken()) {
    router.replace("/login");
    return null;
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
          <h1 className="text-lg font-semibold tracking-tight text-gray-900 mb-1">비밀번호 변경</h1>
          <p className="text-[13px] text-gray-500 mb-5">
            {me?.must_change_password
              ? "대표세무사가 지정한 초기 비밀번호입니다. 계속하려면 새 비밀번호로 변경해 주세요."
              : "새 비밀번호로 변경합니다."}
          </p>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">현재 비밀번호</label>
              <Input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">새 비밀번호</label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
              <p className="text-[11px] text-gray-400 mt-1">6자리 이상, 특수문자 포함</p>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-gray-700 mb-1.5">새 비밀번호 확인</label>
              <Input
                type="password"
                value={newPassword2}
                onChange={(e) => setNewPassword2(e.target.value)}
                required
              />
            </div>
            {err && <p className="text-[13px] text-red-600">{err}</p>}
            <Button className="w-full" disabled={loading}>
              {loading ? "변경 중..." : "비밀번호 변경"}
            </Button>
          </form>

          <button
            onClick={logout}
            className="w-full text-center text-[12px] text-gray-400 hover:text-gray-600 mt-4"
          >
            로그아웃
          </button>
        </Card>
      </div>
    </div>
  );
}
