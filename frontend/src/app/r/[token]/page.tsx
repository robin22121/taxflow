"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { use, useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";

import { PinGate } from "./_components/PinGate";
import { Shell } from "./_components/Shell";
import { CostView } from "./_views/CostView";
import { EmployeeView } from "./_views/EmployeeView";
import { FilingView } from "./_views/FilingView";
import { PaymentView } from "./_views/PaymentView";
import type {
  ArchiveRow,
  EmployeeRow,
  LastMonthInfo,
  PortalStatusInfo,
  SessionInfo,
  ViewKey,
} from "./_components/types";

export default function OwnerPortalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const grantKey = `taxflow_portal_grant_${token}`;
  const qc = useQueryClient();

  const [view, setView] = useState<ViewKey>("filing");
  const [grant, setGrant] = useState<string | null>(null);
  const [pinOpen, setPinOpen] = useState(false);

  const sessionQ = useQuery({
    queryKey: ["portal", token, "session"],
    queryFn: () => api<SessionInfo>(`/api/v1/public/r/${token}`),
  });
  const statusQ = useQuery({
    queryKey: ["portal", token, "status"],
    queryFn: () => api<PortalStatusInfo>(`/api/v1/public/r/${token}/status`),
  });
  const lastMonthQ = useQuery({
    queryKey: ["portal", token, "last-month", grant],
    queryFn: () =>
      api<LastMonthInfo>(`/api/v1/public/r/${token}/last-month`, {
        headers: grant ? { "X-Portal-Grant": grant } : undefined,
      }),
  });
  const archiveQ = useQuery({
    queryKey: ["portal", token, "archive"],
    queryFn: () =>
      api<ArchiveRow[]>(`/api/v1/public/r/${token}/archive`).catch(
        () => [] as ArchiveRow[],
      ),
  });
  const employeesQ = useQuery({
    queryKey: ["portal", token, "employees"],
    queryFn: () =>
      api<EmployeeRow[]>(
        `/api/v1/public/r/${token}/employees-v2?include_resigned=true`,
      ).catch(() => [] as EmployeeRow[]),
  });

  const session = sessionQ.data ?? null;
  const status = statusQ.data ?? null;
  const lastMonth = lastMonthQ.data ?? null;
  const archive = archiveQ.data ?? [];
  const employees = employeesQ.data ?? [];
  const linkError = sessionQ.error ?? statusQ.error ?? null;
  const gateOpen = grant != null;

  // 기존 grant 재사용 — sessionStorage에서 부활. `session` 로드 후 시도.
  useEffect(() => {
    if (grant != null) return;
    if (!sessionQ.data?.has_pin) return;
    const saved = sessionStorage.getItem(grantKey);
    if (!saved) return;
    // 실효성 검증 — grant로 last-month 재조회가 성공하면 유지
    api<LastMonthInfo>(`/api/v1/public/r/${token}/last-month`, {
      headers: { "X-Portal-Grant": saved },
    })
      .then(() => setGrant(saved))
      .catch(() => sessionStorage.removeItem(grantKey));
  }, [sessionQ.data?.has_pin, grantKey, token, grant]);

  const onGranted = useCallback(
    (g: string) => {
      sessionStorage.setItem(grantKey, g);
      setGrant(g);
    },
    [grantKey],
  );

  const refetchAll = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["portal", token] });
  }, [qc, token]);

  if (linkError && !session) {
    return (
      <main className="min-h-dvh bg-gray-50 flex items-center justify-center px-5">
        <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 text-center shadow-sm">
          <div className="text-[15px] font-semibold text-gray-900">링크를 열 수 없어요</div>
          <p className="mt-2 text-[13px] text-gray-500">{(linkError as Error).message}</p>
          <p className="mt-3 text-[12px] text-gray-400">세무사 사무소에 문의해 주세요.</p>
        </div>
      </main>
    );
  }

  if (!session || !status) {
    return (
      <main className="min-h-dvh bg-gray-50 flex items-center justify-center">
        <div className="text-[13px] text-gray-400">불러오는 중…</div>
      </main>
    );
  }

  return (
    <Shell
      clientName={session.client_name}
      taxOfficeName={status.tax_office_name}
      view={view}
      setView={setView}
    >
      {view === "filing" && (
        <FilingView
          token={token}
          status={status}
          lastMonth={lastMonth}
          gateOpen={gateOpen}
          onNeedPin={() => {
            if (session.has_pin) setPinOpen(true);
          }}
          onSubmitted={refetchAll}
          employees={employees}
        />
      )}
      {view === "payment" && (
        <PaymentView token={token} status={status} archive={archive} />
      )}
      {view === "cost" && <CostView token={token} />}
      {view === "employee" && (
        <EmployeeView
          token={token}
          employees={employees}
          gateOpen={gateOpen}
          grant={grant}
          onNeedPin={() => {
            if (session.has_pin) setPinOpen(true);
          }}
          onOpenHire={() => setView("filing")}
        />
      )}

      <PinGate
        token={token}
        open={pinOpen}
        onClose={() => setPinOpen(false)}
        onGranted={onGranted}
      />
    </Shell>
  );
}
