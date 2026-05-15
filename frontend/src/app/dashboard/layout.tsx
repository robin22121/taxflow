"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, clearTokens, getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { Button, Input, Modal } from "@/components/ui";

const NAV_ITEMS = [
  { href: "/dashboard", label: "월별 신고" },
  { href: "/dashboard/clients", label: "거래처" },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const { data: me, isError } = useMe();
  const [showMenu, setShowMenu] = useState(false);
  const [showProfile, setShowProfile] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && !getToken()) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    if (isError) router.replace("/login");
  }, [isError, router]);

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Top nav bar */}
      <header className="flex items-center justify-between px-3 sm:px-5 border-b border-gray-200 bg-white shrink-0 h-12">
        <div className="flex items-center gap-3 sm:gap-6 min-w-0">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-2 shrink-0">
            <div className="w-[22px] h-[22px] rounded-md bg-gray-900 text-white flex items-center justify-center text-[11px] font-extrabold">
              이
            </div>
            <span className="text-[14px] font-bold tracking-tight text-black hidden sm:inline">이지원천</span>
          </Link>

          {/* Nav tabs */}
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={
                    "px-2.5 sm:px-3 py-1.5 rounded-full text-[12px] sm:text-[13px] font-medium transition-colors " +
                    (active
                      ? "bg-gray-900 text-white"
                      : "text-gray-600 hover:bg-gray-100")
                  }
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User menu */}
        <div className="relative shrink-0">
          <button
            onClick={() => setShowMenu((v) => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full hover:bg-gray-100 transition-colors"
          >
            <div className="w-6 h-6 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center text-[11px] font-bold">
              {(me?.name ?? "?").charAt(0)}
            </div>
            <span className="text-[12px] font-medium text-gray-700 hidden sm:inline max-w-[120px] truncate">
              {me?.name ?? "로딩중"}
            </span>
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          {showMenu && (<>
            <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
            <div className="absolute right-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-xl shadow-lg z-50 py-1 overflow-hidden">
              <div className="px-3 py-2.5 border-b border-gray-100">
                <div className="text-[13px] font-semibold text-gray-900">{me?.name}</div>
                <div className="text-[11px] text-gray-500 mt-0.5">{me?.office_name ?? ""}</div>
                <div className="text-[11px] text-gray-400">{me?.email}</div>
              </div>
              <button onClick={() => { setShowMenu(false); setShowProfile(true); }} className="w-full text-left px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                <span>내 정보</span>
              </button>
              <Link href="/dashboard/settings" onClick={() => setShowMenu(false)} className="block px-3 py-2 text-[12px] text-gray-700 hover:bg-gray-50">
                사무소 설정
              </Link>
              <div className="border-t border-gray-100">
                <button onClick={() => { setShowMenu(false); logout(); }} className="w-full text-left px-3 py-2 text-[12px] text-red-600 hover:bg-red-50">
                  로그아웃
                </button>
              </div>
            </div>
          </>)}
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 min-w-0 bg-gray-50">
        <div className="p-4 sm:p-6 pb-24">{children}</div>
      </main>

      {/* Profile modal */}
      {showProfile && me && (
        <ProfileModal me={me} onClose={() => setShowProfile(false)} onSaved={() => { qc.invalidateQueries({ queryKey: ["me"] }); setShowProfile(false); }} />
      )}
    </div>
  );
}

function ProfileModal({ me, onClose, onSaved }: { me: NonNullable<ReturnType<typeof useMe>["data"]>; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: me.name,
    office_representative: me.office_representative ?? "",
    office_phone: me.office_phone ?? "",
    office_email: me.office_email ?? "",
    office_address: me.office_address ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await api("/api/v1/auth/me", { method: "PATCH", json: form });
      onSaved();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function copyCode() {
    if (!me.short_code) return;
    navigator.clipboard.writeText(me.short_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Modal open onClose={onClose} title="내 정보">
      <div className="space-y-4">
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 flex items-center justify-between">
          <div>
            <div className="text-[10px] text-gray-400 uppercase tracking-wider">사무소 인가코드</div>
            <div className="text-[20px] font-bold tracking-[0.12em] text-gray-900 font-mono">{me.short_code ?? "—"}</div>
          </div>
          <button onClick={copyCode} className="text-[11px] text-blue-600 font-medium hover:underline">{copied ? "복사됨" : "복사"}</button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-medium text-gray-600 mb-1">담당자명</label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-gray-600 mb-1">대표자명</label>
            <Input value={form.office_representative} onChange={(e) => setForm({ ...form, office_representative: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-600 mb-1">사무소 전화번호</label>
          <Input value={form.office_phone} onChange={(e) => setForm({ ...form, office_phone: e.target.value })} />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-600 mb-1">사무소 이메일</label>
          <Input type="email" value={form.office_email} onChange={(e) => setForm({ ...form, office_email: e.target.value })} />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-600 mb-1">사무소 주소</label>
          <Input value={form.office_address} onChange={(e) => setForm({ ...form, office_address: e.target.value })} />
        </div>
        <div className="text-[11px] text-gray-400">
          아이디 (사업자번호): <span className="font-medium text-gray-600">{me.email}</span> · 사무소명: <span className="font-medium text-gray-600">{me.office_name}</span>
        </div>
        {err && <p className="text-[12px] text-red-600">{err}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>취소</Button>
          <Button onClick={save} disabled={saving}>{saving ? "저장중..." : "저장"}</Button>
        </div>
      </div>
    </Modal>
  );
}
