"use client";

// 3게이트 정책의 API 클라이언트 (backend/app/api/rpa.py). plan/16-wehago-rpa.md §7.
//
// 게이트 1  POST /wehago-uploads         전송 (직원)
// 게이트 2  POST /productions            제작 (사무소 사용자)
// 게이트 3  POST /filing-results/{id}/publish  발송 확정 (사무소 사용자)
//           GET  /jobs?filing_id=…       진행 조회
//           GET  /notifications          알림 조회
//           POST /agents ·               노트북 에이전트 발급·목록·폐기
//           GET  /agents · DELETE /agents/{id}

import { api } from "./api";

export type RpaJobKind =
  | "WEHAGO_PAYROLL_INPUT"
  | "WEHAGO_BUSINESS_INPUT"
  | "WEHAGO_OTHER_INPUT"
  | "MONTHLY_PRODUCTION"
  | "CERTIFICATE_ISSUE"
  | "WEHAGO_MASTER_IMPORT_ALL"  // 위하고 전체 수임처 가져오기 (관리자)
  | "WEHAGO_CLIENT_IMPORT";  // 사업자번호 1건 가져오기

export type RpaJobStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED";

export type RpaJob = {
  id: string;
  kind: RpaJobKind;
  status: RpaJobStatus;
  monthly_filing_id: string | null;  // 증명원 발급 작업은 null
  client_id: string | null;  // 위하고 가져오기는 비어 있을 수 있음
  period: string | null;
  business_number: string | null;  // 전체 가져오기만 null
  business_name: string;
  agent_id: string | null;
  claimed_at: string | null;
  finished_at: string | null;
  result_message: string | null;
  step_progress: Record<string, unknown> | null;
  compare_diff: Record<string, unknown> | null;
  acknowledged_at: string | null;
  created_at: string;
};

export type RpaAgent = {
  id: string;
  name: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type RpaAgentIssued = RpaAgent & { token: string };

export type FilingResult = {
  id: string;
  client_id: string;
  period: string;
  settled_tax: number | null;
  virtual_account: string | null;
  epayment_number: string | null;
  due_date: string | null;
  receipt_key: string | null;
  receipt_name: string | null;
  payment_slip_key: string | null;
  payment_slip_name: string | null;
  published_at: string | null;
  confirmed_by_user_id: string | null;
  source: string;
  created_at: string;
};

export type RpaNotificationKind = "GATE2_REVIEW" | "GATE3_PUBLISH" | "FAILURE" | "IMPORT_DONE";

export type RpaNotification = {
  id: string;
  kind: RpaNotificationKind;
  title: string;
  body: string;
  job_id: string | null;
  filing_result_id: string | null;
  read_at: string | null;
  resent_count: number;
  created_at: string;
};

// --- 게이트 1 : 전송 ---------------------------------------------------

export function createWehagoUploads(filingId: string, clientIds: string[]): Promise<RpaJob[]> {
  return api<RpaJob[]>("/api/v1/rpa/wehago-uploads", {
    method: "POST",
    json: { filing_id: filingId, client_ids: clientIds },
  });
}

/** 소득유형별 상태 표시 — 선택용이 아니라 읽기 전용 표시다 (plan/16 §4-1). */
export type IncomeTypeStatus = {
  income_type: "WAGE" | "BUSINESS" | "OTHER" | "DAILY";
  count: number;
  unapproved_count: number;
  automated: boolean;
  // 자료입력(게이트1)뿐 아니라 명세서 추가입력(게이트2 마감)까지 끝났는지 — 근로소득은
  // 자료입력만으로 true, 사업소득은 마감까지 성공해야 true (2026-10-01 결정).
  filing_complete: boolean;
};

/** 위하고 전송 모달용 — 거래처별 적용 지급일과 서버 쪽 차단 사유 (사업자번호·사원코드·지급일·진행 중). */
export type WehagoUploadPreview = {
  client_id: string;
  pay_date: string | null;
  blocked_reason: string | null;
  income_types: IncomeTypeStatus[];
};

export function previewWehagoUploads(filingId: string): Promise<WehagoUploadPreview[]> {
  return api<WehagoUploadPreview[]>(
    `/api/v1/rpa/wehago-uploads/preview?filing_id=${encodeURIComponent(filingId)}`,
  );
}

/** 소득유형 단위 선택 전송 — "데모버전" 로그인 전용. 거래처 단위 원자적 전송(createWehagoUploads)과
 * 별개 경로라 결과도 거래처 단위가 아니라 (거래처,소득유형) 단위로 하나씩 내려온다. */
export type WehagoSelectiveUploadSelection = { client_id: string; income_types: string[] };
export type WehagoSelectiveUploadResult = {
  client_id: string;
  income_type: string;
  job: RpaJob | null;
  skipped_reason: string | null;
};

export function createWehagoUploadsSelective(
  filingId: string,
  selections: WehagoSelectiveUploadSelection[],
): Promise<WehagoSelectiveUploadResult[]> {
  return api<WehagoSelectiveUploadResult[]>("/api/v1/rpa/wehago-uploads/selective", {
    method: "POST",
    json: { filing_id: filingId, selections },
  });
}

// --- 게이트 2 : 제작 ---------------------------------------------------

export function createProductions(filingId: string, clientIds: string[]): Promise<RpaJob[]> {
  return api<RpaJob[]>("/api/v1/rpa/productions", {
    method: "POST",
    json: { filing_id: filingId, client_ids: clientIds },
  });
}

// --- 게이트 3 : 발송 확정 ---------------------------------------------

export function publishFilingResult(filingResultId: string): Promise<FilingResult> {
  return api<FilingResult>(`/api/v1/rpa/filing-results/${filingResultId}/publish`, {
    method: "POST",
  });
}

// --- 작업 조회 ---------------------------------------------------------

export function listJobs(filingId?: string): Promise<RpaJob[]> {
  const qs = filingId ? `?filing_id=${encodeURIComponent(filingId)}` : "";
  return api<RpaJob[]>(`/api/v1/rpa/jobs${qs}`);
}

/** 하단 작업바 작업 — 다른 직원 작업은 서버가 거래처 정보(상호·사업자번호·귀속월·메시지 등)를 비워 보낸다. */
export type RpaActivityJob = Omit<RpaJob, "business_name"> & {
  business_name: string | null;
  requested_by_name: string | null;
  is_mine: boolean;
};

export type ActivityScope = "all" | "mine";

/** 하단 작업바 — 전체작업(사무소 직원 전체)·내작업.
 *  today: 대기·진행 중 + 오늘 끝난 작업(작업바 칩), days: 최근 N일 요청 작업([내역보기]),
 *  unacknowledged: 아직 [확인] 안 한 작업만. */
export function listActivity(
  scope: ActivityScope,
  opts: { today?: boolean; days?: number; unacknowledged?: boolean } = {},
): Promise<RpaActivityJob[]> {
  const qs = new URLSearchParams({ scope });
  if (opts.today) qs.set("today", "true");
  if (opts.days) qs.set("days", String(opts.days));
  if (opts.unacknowledged) qs.set("unacknowledged", "true");
  return api<RpaActivityJob[]>(`/api/v1/rpa/jobs/activity?${qs}`);
}

export function acknowledgeJob(jobId: string): Promise<RpaJob> {
  return api<RpaJob>(`/api/v1/rpa/jobs/${jobId}/acknowledge`, { method: "POST" });
}

export function cancelJob(jobId: string): Promise<RpaJob> {
  return api<RpaJob>(`/api/v1/rpa/jobs/${jobId}/cancel`, { method: "POST" });
}

// --- 알림 --------------------------------------------------------------

export function listNotifications(unreadOnly = false): Promise<RpaNotification[]> {
  const qs = unreadOnly ? "?unread_only=true" : "";
  return api<RpaNotification[]>(`/api/v1/rpa/notifications${qs}`);
}

export function markNotificationRead(id: string): Promise<RpaNotification> {
  return api<RpaNotification>(`/api/v1/rpa/notifications/${id}/read`, { method: "POST" });
}

// --- 에이전트 관리 (관리자) --------------------------------------------

export function issueAgent(name: string): Promise<RpaAgentIssued> {
  return api<RpaAgentIssued>("/api/v1/rpa/agents", { method: "POST", json: { name } });
}

export function listAgents(): Promise<RpaAgent[]> {
  return api<RpaAgent[]>("/api/v1/rpa/agents");
}

export function revokeAgent(id: string): Promise<void> {
  return api<void>(`/api/v1/rpa/agents/${id}`, { method: "DELETE" });
}

// --- 위하고 → 이지원천 가져오기 (plan/16 §12) ---------------------------

/** 수임처 1건 결과 — step_progress.clients[] (backend/app/api/rpa_import.py). */
export type ImportClientEntry = {
  business_number: string;
  business_name: string;
  status: "SUCCEEDED" | "FAILED";
  message?: string;
  client_id?: string;
  client_created?: boolean;
  employees?: number;
  employees_created?: number;
  employees_updated?: number;
  conflicts?: { target: string; field: string; current: string; wehago: string }[];
  possibly_removed?: string[];
};

export function importProgress(job: Pick<RpaJob, "step_progress">): { total: number | null; clients: ImportClientEntry[] } {
  const p = (job.step_progress ?? {}) as { total?: number; clients?: ImportClientEntry[] };
  return { total: p.total ?? null, clients: p.clients ?? [] };
}

/** 위하고 전체 수임처 가져오기 — 관리자만, 오래 걸림. */
export function createMasterImport(): Promise<RpaJob> {
  return api<RpaJob>("/api/v1/rpa/imports/master-all", { method: "POST" });
}

/** 사업자번호 1건 가져오기 — 없으면 새 거래처로 등록, 있으면 빈 칸만 채운다. */
export function createClientImport(businessNumber: string): Promise<RpaJob> {
  return api<RpaJob>("/api/v1/rpa/imports/clients", {
    method: "POST",
    json: { business_number: businessNumber },
  });
}

export function listImports(): Promise<RpaJob[]> {
  return api<RpaJob[]>("/api/v1/rpa/imports");
}

// --- 유틸: 작업을 client_id로 인덱싱 --------------------------------

// 게이트 1 "자동입력"은 소득유형별로 kind가 나뉜다 (근로=WEHAGO_PAYROLL_INPUT,
// 사업=WEHAGO_BUSINESS_INPUT, 기타=WEHAGO_OTHER_INPUT) — 거래처 하나가 여러 kind를
// 동시에 가질 수 있어 배열로 둔다.
const INPUT_KINDS: RpaJobKind[] = ["WEHAGO_PAYROLL_INPUT", "WEHAGO_BUSINESS_INPUT", "WEHAGO_OTHER_INPUT"];

export function indexJobsByClient(jobs: RpaJob[]): Record<string, { inputs: RpaJob[]; production?: RpaJob }> {
  const out: Record<string, { inputs: RpaJob[]; production?: RpaJob }> = {};
  // 오래된 것부터 담아 inputs 배열도 시간순, production은 최신이 이긴다.
  const sorted = [...jobs].sort((a, b) => a.created_at.localeCompare(b.created_at));
  for (const job of sorted) {
    if (!job.client_id) continue;
    const bucket = (out[job.client_id] ??= { inputs: [] });
    if (INPUT_KINDS.includes(job.kind)) bucket.inputs.push(job);
    else if (job.kind === "MONTHLY_PRODUCTION") bucket.production = job;
  }
  return out;
}

export type GateStage = "not_started" | "sending" | "input_done" | "producing" | "production_done" | "published" | "failed";

/** 거래처 하나의 3게이트 진행 단계 판정. RpaPanel에서 UI 표시용.
 *
 * inputs는 거래처가 가진 소득유형 수만큼 있을 수 있다(근로만 있으면 1개, 근로+사업이면 2개) —
 * 전부 성공해야 input_done, 하나라도 FAILED면 failed.
 */
export function gateStage(
  inputs: RpaJob[],
  production: RpaJob | undefined,
  filingResult: FilingResult | undefined,
): GateStage {
  if (production?.status === "FAILED" || inputs.some((j) => j.status === "FAILED")) return "failed";
  if (filingResult?.published_at) return "published";
  if (production?.status === "SUCCEEDED") return "production_done";
  if (production && (production.status === "PENDING" || production.status === "RUNNING")) return "producing";
  if (inputs.length > 0 && inputs.every((j) => j.status === "SUCCEEDED")) return "input_done";
  if (inputs.some((j) => j.status === "PENDING" || j.status === "RUNNING")) return "sending";
  return "not_started";
}
