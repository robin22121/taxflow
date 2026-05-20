"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useMe, useChangePassword } from "@/lib/queries";
import { Button, Card, Input, Badge } from "@/components/ui";

const TABS = [
  { key: "profile", label: "프로필" },
  { key: "password", label: "비밀번호 변경" },
  { key: "subscription", label: "구독내역" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const PW_SPECIALS = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`";

function passwordError(pw: string): string | null {
  if (pw.length < 6) return "비밀번호는 6자리 이상이어야 합니다";
  if (![...pw].some((c) => PW_SPECIALS.includes(c)))
    return "비밀번호에 특수문자를 포함해야 합니다";
  return null;
}

export default function AccountPage() {
  const { data: me, isLoading } = useMe();
  const [tab, setTab] = useState<TabKey>("profile");

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">내 정보</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          프로필·비밀번호·구독 정보를 관리합니다.
        </p>
      </div>

      {/* Tab nav — layout.tsx pill 스타일과 동일 */}
      <nav className="flex items-center gap-1 border-b border-gray-200 pb-3">
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                "px-3 py-1.5 rounded-full text-[13px] font-medium transition-colors " +
                (active
                  ? "bg-gray-900 text-white"
                  : "text-gray-600 hover:bg-gray-100")
              }
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      {isLoading || !me ? (
        <Card className="p-5 space-y-3">
          <div className="h-4 w-32 bg-gray-100 rounded animate-pulse" />
          <div className="h-9 w-full bg-gray-100 rounded animate-pulse" />
          <div className="h-9 w-full bg-gray-100 rounded animate-pulse" />
        </Card>
      ) : tab === "profile" ? (
        <ProfileTab me={me} />
      ) : tab === "password" ? (
        <PasswordTab />
      ) : (
        <SubscriptionTab />
      )}
    </div>
  );
}

function ProfileTab({ me }: { me: NonNullable<ReturnType<typeof useMe>["data"]> }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: me.name,
    office_representative: me.office_representative ?? "",
    office_phone: me.office_phone ?? "",
    office_email: me.office_email ?? "",
    office_address: me.office_address ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  async function save() {
    setSaving(true);
    setErr(null);
    setSaved(false);
    try {
      await api("/api/v1/auth/me", { method: "PATCH", json: form });
      await qc.invalidateQueries({ queryKey: ["me"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
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
    <div className="space-y-5">
      <Card className="p-5 flex items-center justify-between">
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider">사무소 인가코드</div>
          <div className="text-[22px] font-bold tracking-[0.14em] text-gray-900 font-mono mt-0.5">
            {me.short_code ?? "—"}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">
            카카오톡 채널에서 직원이 이 코드를 입력하면 사무소에 연결됩니다.
          </div>
        </div>
        <Button variant="secondary" onClick={copyCode} className="shrink-0">
          {copied ? "복사됨" : "복사"}
        </Button>
      </Card>

      <Card className="p-5 space-y-4">
        <h2 className="text-[14px] font-semibold text-gray-900">프로필</h2>
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

        <div className="border-t border-gray-100 pt-3 space-y-2">
          <ReadOnlyRow label="아이디 (사업자번호)" value={me.email} />
          <ReadOnlyRow label="사무소명" value={me.office_name ?? "—"} />
          <p className="text-[11px] text-gray-400">아이디·사무소명은 변경할 수 없습니다.</p>
        </div>

        {err && <p className="text-[12px] text-red-600">{err}</p>}
        <div className="flex items-center justify-end gap-3">
          {saved && <span className="text-[12px] text-green-600">저장되었습니다</span>}
          <Button onClick={save} disabled={saving}>{saving ? "저장중..." : "저장"}</Button>
        </div>
      </Card>
    </div>
  );
}

function ReadOnlyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[12px] text-gray-500">{label}</span>
      <span className="text-[13px] font-medium text-gray-900">{value}</span>
    </div>
  );
}

function PasswordTab() {
  const changePw = useChangePassword();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const localError = useMemo(() => {
    if (!next && !confirm) return null;
    const pe = passwordError(next);
    if (pe) return pe;
    if (next !== confirm) return "새 비밀번호가 일치하지 않습니다";
    return null;
  }, [next, confirm]);

  const canSubmit =
    cur.length > 0 && next.length > 0 && confirm.length > 0 && !localError && !changePw.isPending;

  async function submit() {
    setErr(null);
    setDone(false);
    const pe = passwordError(next);
    if (pe) return setErr(pe);
    if (next !== confirm) return setErr("새 비밀번호가 일치하지 않습니다");
    try {
      await changePw.mutateAsync({ current_password: cur, new_password: next });
      setDone(true);
      setCur("");
      setNext("");
      setConfirm("");
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <Card className="p-5 space-y-4">
      <div>
        <h2 className="text-[14px] font-semibold text-gray-900">비밀번호 변경</h2>
        <p className="text-[12px] text-gray-500 mt-0.5">
          6자리 이상, 특수문자를 포함해야 합니다.
        </p>
      </div>
      <div>
        <label className="block text-[11px] font-medium text-gray-600 mb-1">현재 비밀번호</label>
        <Input type="password" value={cur} autoComplete="current-password" onChange={(e) => setCur(e.target.value)} />
      </div>
      <div>
        <label className="block text-[11px] font-medium text-gray-600 mb-1">새 비밀번호</label>
        <Input type="password" value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
      </div>
      <div>
        <label className="block text-[11px] font-medium text-gray-600 mb-1">새 비밀번호 확인</label>
        <Input type="password" value={confirm} autoComplete="new-password" onChange={(e) => setConfirm(e.target.value)} />
      </div>

      {localError && <p className="text-[12px] text-red-600">{localError}</p>}
      {err && !localError && <p className="text-[12px] text-red-600">{err}</p>}
      {done && <p className="text-[12px] text-green-600">비밀번호가 변경되었습니다.</p>}

      <div className="flex justify-end">
        <Button onClick={submit} disabled={!canSubmit}>
          {changePw.isPending ? "변경중..." : "비밀번호 변경"}
        </Button>
      </div>
    </Card>
  );
}

function SubscriptionTab() {
  return (
    <div className="space-y-5">
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-gray-900">현재 요금제</h2>
          <Badge tone="info">베타</Badge>
        </div>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[24px] font-bold text-gray-900">무료</div>
            <div className="text-[12px] text-gray-500 mt-0.5">
              베타 기간 동안 모든 기능을 무료로 사용할 수 있습니다.
            </div>
          </div>
          <Button variant="secondary" disabled title="결제 기능 준비 중">
            요금제 변경
          </Button>
        </div>
        <div className="border-t border-gray-100 pt-3 grid grid-cols-2 gap-3">
          <ReadOnlyRow label="다음 결제일" value="—" />
          <ReadOnlyRow label="결제 수단" value="등록 안 됨" />
        </div>
      </Card>

      <Card className="p-5 space-y-3">
        <h2 className="text-[14px] font-semibold text-gray-900">결제 내역</h2>
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center">
          <p className="text-[13px] text-gray-500">결제 내역이 없습니다.</p>
          <p className="text-[11px] text-gray-400 mt-1">
            유료 전환 시 결제 내역이 여기에 표시됩니다.
          </p>
        </div>
      </Card>

      <div className="rounded-lg bg-blue-50 border border-blue-100 p-3">
        <p className="text-[12px] text-blue-700">
          <span className="font-semibold">안내:</span> 결제·구독 기능은 준비 중입니다.
          정식 출시 시 요금제와 결제 수단을 이 화면에서 관리할 수 있습니다.
        </p>
      </div>
    </div>
  );
}
