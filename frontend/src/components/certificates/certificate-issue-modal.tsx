"use client";

// 증명원 발급 팝업 — plan/17-certificate-issuance.md §4-9.
//
// ① 거래처 선택 (선택된 거래처가 없을 때) → ② 홈택스·지방세·직원용 증명원 선택 → [발급]
// → ③ 진행 → ④ 완료 알림 [확인] → ⑤ 다음 작업: [폴더 열어 확인] 먼저, 그다음 문자·카톡·팩스.
// 하단 작업바에서 이미 요청한 건을 열 때는 jobId 로 ③부터 시작한다.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, Input, Modal } from "@/components/ui";
import { useClients } from "@/lib/queries";
import type { Client } from "@/lib/types";
import {
  type CertCategory,
  type CertificateIssue,
  createIssueRequest,
  deliverCertificates,
  getCatalog,
  getCertificateJob,
  getIssueFile,
  requestOpenFolder,
} from "@/lib/certificates-api";

type Step = "client" | "select" | "progress" | "done" | "next";

const TABS: { key: CertCategory; label: string }[] = [
  { key: "HOMETAX", label: "홈택스" },
  { key: "WETAX", label: "지방세" },
  { key: "EMPLOYEE", label: "직원용" },
];

const ISSUE_STATE: Record<CertificateIssue["status"], { text: string; cls: string }> = {
  REQUESTED: { text: "대기", cls: "text-gray-500" },
  RUNNING: { text: "발급중", cls: "text-blue-600" },
  ISSUED: { text: "발급 완료", cls: "text-emerald-600" },
  FAILED: { text: "실패", cls: "text-red-600" },
  CANCELED: { text: "취소", cls: "text-gray-400" },
};

type Props = {
  onClose: () => void;
  initialClientId?: string | null;
  initialTab?: CertCategory;
  /** 하단 작업바에서 기존 요청을 열 때 */
  jobId?: string;
};

export function CertificateIssueModal({ onClose, initialClientId, initialTab = "HOMETAX", jobId: initialJobId }: Props) {
  const qc = useQueryClient();
  const [clientId, setClientId] = useState<string | null>(initialClientId ?? null);
  const [jobId, setJobId] = useState<string | null>(initialJobId ?? null);
  const [step, setStep] = useState<Step>(initialJobId ? "progress" : initialClientId ? "select" : "client");
  const [tab, setTab] = useState<CertCategory>(initialTab);
  const [checked, setChecked] = useState<string[]>([]);
  const [rrnDisclosed, setRrnDisclosed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: clients = [] } = useClients();
  const { data: catalog = [] } = useQuery({ queryKey: ["certificates", "catalog"], queryFn: getCatalog });

  const { data: jobData } = useQuery({
    queryKey: ["certificates", "job", jobId],
    queryFn: () => getCertificateJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 3000;
      const running = d.job.status === "PENDING" || d.job.status === "RUNNING";
      // 폴더 열기를 요청했으면 에이전트가 열 때까지 계속 본다
      const folderPending = d.issues.some((i) => i.folder_open_requested_at && !i.folder_opened_at);
      return running || folderPending ? 3000 : false;
    },
  });
  // 작업바에서 열었으면 거래처는 작업에서 가져온다
  const client = clients.find((c) => c.id === (clientId ?? jobData?.job.client_id)) ?? null;
  const finished = jobData && jobData.job.status !== "PENDING" && jobData.job.status !== "RUNNING";
  // 진행 화면에서 끝나면 완료 알림으로 (렌더 중 파생 — effect 없이)
  const shownStep: Step = step === "progress" && finished ? (initialJobId ? "next" : "done") : step;

  const issue = useMutation({
    mutationFn: () => createIssueRequest(clientId!, checked, rrnDisclosed),
    onSuccess: (data) => {
      setJobId(data.job.id);
      setStep("progress");
      setError(null);
      qc.invalidateQueries({ queryKey: ["rpa", "jobs"] });
    },
    onError: (e) => setError((e as Error).message),
  });

  const title = client ? `증명원 발급 · ${client.business_name}` : "증명원 발급";

  return (
    <Modal open onClose={onClose} title={title} size="lg" footer={footer()}>
      {error && <p className="mb-3 text-[12px] text-red-600">{error}</p>}
      {shownStep === "client" && (
        <ClientPicker clients={clients} onPick={(id) => { setClientId(id); setStep("select"); }} />
      )}
      {shownStep === "select" && (
        <SelectStep
          catalog={catalog}
          tab={tab}
          setTab={setTab}
          checked={checked}
          toggle={(code) => setChecked((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))}
          rrnDisclosed={rrnDisclosed}
          setRrnDisclosed={setRrnDisclosed}
          onChangeClient={() => setStep("client")}
          clientLabel={client ? `${client.business_name}${client.business_number ? ` (${client.business_number})` : ""}` : ""}
        />
      )}
      {shownStep === "progress" && <ProgressStep issues={jobData?.issues ?? []} />}
      {shownStep === "done" && jobData && <DoneStep issues={jobData.issues} />}
      {shownStep === "next" && jobData && (
        <NextStep jobId={jobData.job.id} issues={jobData.issues} defaultPhone={client?.contact_phone ?? ""} />
      )}
    </Modal>
  );

  function footer() {
    if (shownStep === "select") {
      return <>
        <Button variant="ghost" onClick={onClose}>취소</Button>
        <Button onClick={() => issue.mutate()} disabled={!checked.length || issue.isPending}>
          {issue.isPending ? "요청중..." : `발급 (${checked.length})`}
        </Button>
      </>;
    }
    if (shownStep === "progress") {
      return <Button variant="ghost" onClick={onClose}>닫기 (하단 작업바에서 계속 확인)</Button>;
    }
    if (shownStep === "done") {
      return <Button onClick={() => setStep("next")}>확인</Button>;
    }
    return <Button variant="ghost" onClick={onClose}>닫기</Button>;
  }
}

function ClientPicker({ clients, onPick }: { clients: Client[]; onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const term = q.replace(/-/g, "").trim();
    return clients.filter((c) => !term || c.business_name.includes(term) || (c.business_number ?? "").replace(/-/g, "").includes(term));
  }, [clients, q]);

  return (
    <div className="space-y-2">
      <p className="text-[12.5px] text-gray-600">증명원을 발급할 거래처를 선택하세요.</p>
      <Input autoFocus placeholder="상호 또는 사업자번호 검색" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-100">
        {list.length === 0 && <p className="px-3 py-3 text-[12px] text-gray-400">검색 결과가 없습니다.</p>}
        {list.map((c) => (
          <button key={c.id} onClick={() => onPick(c.id)} className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center justify-between">
            <span className="text-[13px] text-gray-800">{c.business_name}</span>
            <span className="text-[11.5px] text-gray-400">{c.business_number ?? "사업자번호 없음"}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SelectStep({
  catalog, tab, setTab, checked, toggle, rrnDisclosed, setRrnDisclosed, onChangeClient, clientLabel,
}: {
  catalog: Awaited<ReturnType<typeof getCatalog>>;
  tab: CertCategory;
  setTab: (t: CertCategory) => void;
  checked: string[];
  toggle: (code: string) => void;
  rrnDisclosed: boolean;
  setRrnDisclosed: (v: boolean) => void;
  onChangeClient: () => void;
  clientLabel: string;
}) {
  const items = catalog.filter((c) => c.category === tab);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
        <span className="text-[12.5px] text-gray-700">{clientLabel}</span>
        <button onClick={onChangeClient} className="text-[11.5px] text-blue-600 hover:underline">거래처 변경</button>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => {
          const n = catalog.filter((c) => c.category === t.key && checked.includes(c.code)).length;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={"px-3 py-1.5 text-[12.5px] font-medium -mb-px border-b-2 " + (tab === t.key ? "border-gray-900 text-gray-900" : "border-transparent text-gray-500 hover:text-gray-700")}>
              {t.label}{n > 0 && <span className="ml-1 text-blue-600">{n}</span>}
            </button>
          );
        })}
      </div>

      <div className="space-y-1.5">
        {items.map((item) => (
          <label key={item.code}
            className={"flex items-center justify-between rounded-lg border px-3 py-2 " + (item.available ? "border-gray-200 cursor-pointer hover:bg-gray-50" : "border-gray-100 bg-gray-50")}>
            <span className="flex items-center gap-2">
              <input type="checkbox" disabled={!item.available} checked={checked.includes(item.code)} onChange={() => toggle(item.code)} />
              <span className={"text-[12.5px] " + (item.available ? "text-gray-800" : "text-gray-400")}>{item.title}</span>
            </span>
            {!item.available && (
              <span className="text-[10.5px] font-semibold text-gray-400 border border-gray-200 bg-white rounded-full px-2 py-0.5">준비중</span>
            )}
          </label>
        ))}
      </div>

      {tab === "HOMETAX" && (
        <label className="flex items-center gap-2 text-[12px] text-gray-600">
          <input type="checkbox" checked={rrnDisclosed} onChange={(e) => setRrnDisclosed(e.target.checked)} />
          주민등록번호 공개 (제출처가 요구할 때만)
        </label>
      )}
    </div>
  );
}

function IssueList({ issues, showPath }: { issues: CertificateIssue[]; showPath?: boolean }) {
  return (
    <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
      {issues.map((i) => (
        <div key={i.id} className="px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[12.5px] text-gray-800">{i.title}</span>
            <span className={"text-[11.5px] font-medium " + ISSUE_STATE[i.status].cls}>{ISSUE_STATE[i.status].text}</span>
          </div>
          {showPath && i.local_path && <p className="mt-0.5 text-[11px] text-gray-400 break-all">{i.local_path}</p>}
          {i.failure_reason && <p className="mt-0.5 text-[11px] text-red-500 break-all">{i.failure_reason}</p>}
        </div>
      ))}
    </div>
  );
}

function ProgressStep({ issues }: { issues: CertificateIssue[] }) {
  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-gray-600">자동화 PC 에서 홈택스 증명원을 발급하고 있습니다. 창을 닫아도 하단 작업바에서 이어서 확인할 수 있습니다.</p>
      <IssueList issues={issues} />
    </div>
  );
}

function DoneStep({ issues }: { issues: CertificateIssue[] }) {
  const ok = issues.filter((i) => i.status === "ISSUED").length;
  return (
    <div className="space-y-3">
      <p className="text-[14px] font-semibold text-gray-900">
        {ok === issues.length ? "증명원 발급이 완료되었습니다." : `${issues.length}건 중 ${ok}건 발급되었습니다.`}
      </p>
      <p className="text-[12.5px] text-gray-600">
        {ok > 0
          ? "원본은 자동화 PC 의 지정 폴더에 저장했습니다. [확인]을 누르면 다음 작업을 선택합니다."
          : "발급된 증명원이 없습니다. 실패 사유를 확인한 뒤 다시 요청하세요."}
      </p>
      <IssueList issues={issues} showPath />
    </div>
  );
}

function NextStep({ jobId, issues, defaultPhone }: { jobId: string; issues: CertificateIssue[]; defaultPhone: string }) {
  const qc = useQueryClient();
  const issued = issues.filter((i) => i.status === "ISSUED");
  const [folderChecked, setFolderChecked] = useState(issued.some((i) => i.folder_open_requested_at));
  const [phone, setPhone] = useState(defaultPhone);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opened = issued.length > 0 && issued.every((i) => i.folder_opened_at);

  const openFolder = useMutation({
    mutationFn: () => requestOpenFolder(jobId),
    onSuccess: (data) => {
      setFolderChecked(true);
      setError(null);
      qc.setQueryData(["certificates", "job", jobId], data);
    },
    onError: (e) => setError((e as Error).message),
  });

  const send = useMutation({
    mutationFn: (channel: "sms" | "alimtalk") => deliverCertificates(jobId, channel, phone),
    onSuccess: (r) => {
      setError(null);
      setMessage(r.accepted ? `${r.channel === "sms" ? "문자" : "카톡(알림톡)"} 발송 완료 → ${r.to}` : `발송 실패: ${r.error ?? "알 수 없는 오류"}`);
      qc.invalidateQueries({ queryKey: ["rpa", "jobs"] });
    },
    onError: (e) => setError((e as Error).message),
  });

  async function preview(issueId: string) {
    const url = URL.createObjectURL(await getIssueFile(issueId));
    window.open(url, "_blank");
  }

  if (!issued.length) {
    return <p className="text-[12.5px] text-gray-600">발급된 증명원이 없습니다. 실패 사유를 확인한 뒤 다시 요청하세요.</p>;
  }

  return (
    <div className="space-y-4">
      <section className="space-y-2">
        <h3 className="text-[12.5px] font-semibold text-gray-900">1. 발급본 확인</h3>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => openFolder.mutate()} disabled={openFolder.isPending}>
            {openFolder.isPending ? "요청중..." : "폴더 열어 확인"}
          </Button>
          {issued.map((i) => i.has_file && (
            <Button key={i.id} variant="ghost" onClick={() => preview(i.id)} className="!text-[12px]">{i.title} 미리보기</Button>
          ))}
        </div>
        {folderChecked && (
          <p className="text-[11.5px] text-gray-500">
            {opened ? "자동화 PC 에서 폴더를 열었습니다." : "자동화 PC 에 폴더 열기를 요청했습니다 (몇 초 걸릴 수 있습니다). 이 PC 가 아니면 미리보기로 확인하세요."}
          </p>
        )}
      </section>

      <section className={"space-y-2 " + (folderChecked ? "" : "opacity-50")}>
        <h3 className="text-[12.5px] font-semibold text-gray-900">2. 고객에게 보내기</h3>
        <p className="text-[11.5px] text-gray-500">다운로드 링크를 보냅니다. 링크는 발급일로부터 30일간 유효합니다.</p>
        <Input placeholder="받는 사람 휴대폰 번호" value={phone} onChange={(e) => setPhone(e.target.value)} disabled={!folderChecked} />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!folderChecked || !phone || send.isPending} onClick={() => send.mutate("sms")}>문자 발송</Button>
          <Button variant="secondary" disabled={!folderChecked || !phone || send.isPending} onClick={() => send.mutate("alimtalk")}>카톡(알림톡) 발송</Button>
          <Button variant="secondary" disabled title="팩스 게이트웨이 도입 후 제공">팩스 발송 (준비중)</Button>
        </div>
        {!folderChecked && <p className="text-[11.5px] text-gray-400">먼저 [폴더 열어 확인]으로 발급본을 확인하세요.</p>}
      </section>

      {message && <p className="text-[12px] text-emerald-700">{message}</p>}
      {error && <p className="text-[12px] text-red-600">{error}</p>}
    </div>
  );
}
