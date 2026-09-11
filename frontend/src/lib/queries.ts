"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "./api";
import { apiUpload } from "./api";
import type {
  AdminOffice,
  AdminOfficeDetail,
  ArchivePeriod,
  Client,
  ClientInviteResult,
  CurrentUser,
  Employee,
  EmployeeChangeRequest,
  Filing,
  FilingDashboard,
  FilingResultPatch,
  ImportEmployeeResult,
  ImportPayrollResult,
  InsuranceSummary,
  PayrollDefault,
  PayrollDefaultPatch,
  PayrollEntry,
  PayrollHistoryPeriod,
  PortalLink,
  PortalPinStatus,
  Promotion,
  SessionAttachment,
  SessionTimelineEvent,
} from "./types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api<CurrentUser>("/api/v1/auth/me"),
    retry: false,
  });
}

export function useFilings() {
  return useQuery({
    queryKey: ["filings"],
    queryFn: () => api<Filing[]>("/api/v1/filings"),
  });
}

export function useFilingDashboard(filingId: string) {
  return useQuery({
    queryKey: ["filings", filingId, "dashboard"],
    queryFn: () => api<FilingDashboard>(`/api/v1/filings/${filingId}/dashboard`),
    refetchInterval: 5000,
  });
}

export function useConfirmWithClient(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { sessionId: string; channel?: "auto" | "email" | "kakao" | "sms" }) =>
      api<{
        sent: boolean;
        channel: string;
        error: string | null;
        entry_count: number;
      }>(
        `/api/v1/filings/${filingId}/sessions/${vars.sessionId}/confirm-with-client${vars.channel ? `?channel=${vars.channel}` : ""}`,
        { method: "POST", json: {} },
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["filings", filingId, "dashboard"] }),
  });
}

export function useSessionAttachments(filingId: string, sessionId: string | null) {
  return useQuery({
    queryKey: ["filings", filingId, "sessions", sessionId, "attachments"],
    queryFn: () =>
      api<SessionAttachment[]>(
        `/api/v1/filings/${filingId}/sessions/${sessionId}/attachments`,
      ),
    enabled: !!sessionId,
  });
}

export function useSessionTimeline(filingId: string, sessionId: string | null) {
  return useQuery({
    queryKey: ["filings", filingId, "sessions", sessionId, "timeline"],
    queryFn: () =>
      api<SessionTimelineEvent[]>(
        `/api/v1/filings/${filingId}/sessions/${sessionId}/timeline`,
      ),
    enabled: !!sessionId,
  });
}

export function useFilingEntries(filingId: string) {
  return useQuery({
    queryKey: ["filings", filingId, "entries"],
    queryFn: () => api<PayrollEntry[]>(`/api/v1/filings/${filingId}/entries`),
  });
}

export function useInsuranceSummary(filingId: string, clientId: string | null) {
  return useQuery({
    queryKey: ["filings", filingId, "insurance-summary", clientId],
    queryFn: () => {
      const qs = clientId ? `?client_id=${clientId}` : "";
      return api<InsuranceSummary>(
        `/api/v1/filings/${filingId}/insurance-summary${qs}`,
      );
    },
    enabled: !!filingId,
  });
}

export function useClients() {
  return useQuery({
    queryKey: ["clients"],
    queryFn: () => api<Client[]>("/api/v1/clients"),
  });
}

export function useCreateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      business_name: string;
      business_number?: string | null;
      representative?: string | null;
      contact_phone?: string | null;
      contact_email?: string | null;
      is_corporation?: boolean;
    }) =>
      api<Client>("/api/v1/clients", { method: "POST", json: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });
}

export function useBulkUploadClients() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      apiUpload<Client[]>("/api/v1/clients/bulk-upload", file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });
}

export function useClientDetail(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId],
    queryFn: () => api<Client>(`/api/v1/clients/${clientId}`),
  });
}

export function useUpdateClient(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<Client>) =>
      api<Client>(`/api/v1/clients/${clientId}`, { method: "PATCH", json: patch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients", clientId] });
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

export function useSendClientInvite(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<ClientInviteResult>(`/api/v1/clients/${clientId}/invite`, {
        method: "POST",
        json: {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients", clientId] });
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

/* ─── 사업주 포털 — 상설 링크 · PIN (plan/12-owner-portal.md §4.3) ─── */

export function usePortalLink(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "portal-link"],
    queryFn: () => api<PortalLink>(`/api/v1/clients/${clientId}/portal-link`),
  });
}

export function useRotatePortalLink(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<PortalLink>(`/api/v1/clients/${clientId}/portal-link/rotate`, {
        method: "POST",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "portal-link"] }),
  });
}

export function usePortalPinStatus(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "portal-pin"],
    queryFn: () => api<PortalPinStatus>(`/api/v1/clients/${clientId}/portal-pin`),
  });
}

export function useIssuePortalPin(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ pin: string }>(`/api/v1/clients/${clientId}/portal-pin`, {
        method: "POST",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "portal-pin"] }),
  });
}

export function useClientEmployees(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "employees"],
    queryFn: () => api<Employee[]>(`/api/v1/clients/${clientId}/employees`),
  });
}

export function useImportEmployees(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      apiUpload<ImportEmployeeResult>(
        `/api/v1/clients/${clientId}/import-employees`,
        file,
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "employees"] }),
  });
}

export function usePayrollDefault(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "payroll-default"],
    queryFn: () =>
      api<PayrollDefault>(`/api/v1/clients/${clientId}/payroll-default`),
  });
}

export function useUpdatePayrollDefault(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: PayrollDefaultPatch) =>
      api<PayrollDefault>(`/api/v1/clients/${clientId}/payroll-default`, {
        method: "PUT",
        json: patch,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "payroll-default"] }),
  });
}

export function useResetPayrollDefault(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<PayrollDefault>(`/api/v1/clients/${clientId}/payroll-default/reset`, {
        method: "POST",
        json: {},
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "payroll-default"] }),
  });
}

export function useImportPayroll(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { file: File; period: string }) =>
      apiUpload<ImportPayrollResult>(
        `/api/v1/clients/${clientId}/import-payroll?period=${vars.period}`,
        vars.file,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filings"] });
      qc.invalidateQueries({ queryKey: ["clients", clientId, "payroll-history"] });
    },
  });
}

export function useClientPayrollHistory(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "payroll-history"],
    queryFn: () =>
      api<PayrollHistoryPeriod[]>(
        `/api/v1/clients/${clientId}/payroll-history`,
      ),
  });
}

/* ─── 보관함 — 신고 결과 기입·문서 업로드 (plan/12-owner-portal.md §3.4, §5.4) ─── */

export function useClientArchive(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId, "filing-results"],
    queryFn: () =>
      api<ArchivePeriod[]>(`/api/v1/clients/${clientId}/filing-results`),
  });
}

export function useUpsertFilingResult(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ period, patch }: { period: string; patch: FilingResultPatch }) =>
      api(`/api/v1/clients/${clientId}/filing-results/${period}`, {
        method: "PUT",
        json: patch,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "filing-results"] }),
  });
}

export function useUploadFilingDocument(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      period,
      kind,
      file,
    }: {
      period: string;
      kind: "receipt" | "payment-slip";
      file: File;
    }) =>
      apiUpload(
        `/api/v1/clients/${clientId}/filing-results/${period}/documents/${kind}`,
        file,
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["clients", clientId, "filing-results"] }),
  });
}

export function useUpdateEntry(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; patch: Partial<PayrollEntry> }) =>
      api<PayrollEntry>(`/api/v1/filings/${filingId}/entries/${vars.id}`, {
        method: "PATCH",
        json: vars.patch,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filings", filingId] });
    },
  });
}

export function useDeleteEntry(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) =>
      api(`/api/v1/filings/${filingId}/entries/${entryId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filings", filingId] });
    },
  });
}

export function useCreateFiling() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (period: string) =>
      api<Filing>("/api/v1/filings", { method: "POST", json: { period } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filings"] }),
  });
}

export function useSendInvite(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api(`/api/v1/filings/${filingId}/invite`, { method: "POST", json: {} }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["filings", filingId, "dashboard"] }),
  });
}

export function useRequestCollection(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      api(`/api/v1/filings/${filingId}/sessions/${sessionId}/request`, {
        method: "POST",
        json: {},
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["filings", filingId, "dashboard"] }),
  });
}

export function useSubmitMessage(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      sessionId: string;
      text: string;
      channel: string;
      sender_name: string;
      received_date: string;
    }) =>
      api(`/api/v1/collect/sessions/${vars.sessionId}/messages`, {
        method: "POST",
        json: {
          text: vars.text,
          channel: vars.channel,
          sender_name: vars.sender_name,
          received_date: vars.received_date,
        },
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["filings", filingId] }),
  });
}

// ── AI 파싱 미리보기 → 검토 → 반영 ──────────────────────────

export type ParsedEntryPreview = {
  raw_name: string;
  employee_id: string | null;
  employee_name: string | null;
  income_type: string;
  total_amount: number;
  // null = 원시자료에 항목 없음(거래처 기본값·자체 계산으로 채움), 0 = 원시자료가 0원이라고 명시
  non_taxable: number | null;
  meal_amount: number | null;
  car_amount: number | null;
  childcare_amount: number | null;
  // 회사가 이미 적용한 4대보험 실제 공제액 — 있으면 재계산하지 않는다
  national_pension: number | null;
  health_insurance: number | null;
  employment_insurance: number | null;
  longterm_care: number | null;
  match_status: string;
  prev_amount: number | null;
  needs_followup: boolean;
  anomaly_notes: Record<string, unknown> | null;
  /** 이번 달에 이미 있는 항목이면 "update" — 새로 만들지 않고 그 항목을 고친다. */
  mode: "create" | "update";
  entry_id: string | null;
  existing_amount: number | null;
  /** 신규 입사자를 이 항목과 함께 직원 마스터에 등록할 때만 채운다. */
  new_employee?: NewEmployeeInput | null;
};

/** 검토 화면에서 신규 입사자를 그 자리에 등록할 때 보내는 인적사항. */
export type NewEmployeeInput = {
  rrn?: string | null;
  hired_at?: string | null;
  employee_code?: string | null;
  department?: string | null;
  position?: string | null;
  job_type?: string | null;
};

export type CollectPreview = {
  session_id: string;
  source_text: string;
  channel: string;
  kind: string | null;
  attachments: Record<string, unknown>[] | null;
  entries: ParsedEntryPreview[];
  new_hire_suspected: number;
  resignation_suspected: number;
  ambiguous: number;
  unconfirmed: number;
  new_hire_followups?: Record<string, unknown>[];
  resignation_followups?: Record<string, unknown>[];
  ambiguous_followups?: Record<string, unknown>[];
  unconfirmed_followups?: Record<string, unknown>[];
};

/** 선택한 급여항목의 직원을 퇴사 처리한다 (급여항목은 남긴다). */
export function useResignEmployees(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { entryIds: string[]; resigned_at: string }) =>
      api<{ resigned: string[]; skipped: string[] }>(
        `/api/v1/filings/${filingId}/entries/resign`,
        { method: "POST", json: { entry_ids: vars.entryIds, resigned_at: vars.resigned_at } },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filings", filingId] }),
  });
}

/** 급여파일을 AI로 읽어 항목만 미리 받아온다 (저장 안 함). */
export function usePreviewUpload() {
  return useMutation({
    mutationFn: (vars: { sessionId: string; file: File }) =>
      apiUpload<CollectPreview>(
        `/api/v1/collect/sessions/${vars.sessionId}/upload/preview`,
        vars.file,
      ),
  });
}

/** 전월 급여자료를 이번 달 후보로 불러온다 (AI 미사용, 저장 안 함). */
export function usePreviewCarryForward() {
  return useMutation({
    mutationFn: (vars: { sessionId: string }) =>
      api<CollectPreview>(`/api/v1/collect/sessions/${vars.sessionId}/carry-forward/preview`, {
        method: "POST",
        json: {},
      }),
  });
}

/** 검토·수정한 항목을 실제로 반영한다. */
export function useCommitEntries(filingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      sessionId: string;
      text: string;
      channel: string;
      sender_name: string;
      received_date: string;
      attachments: Record<string, unknown>[] | null;
      entries: ParsedEntryPreview[];
    }) =>
      api(`/api/v1/collect/sessions/${vars.sessionId}/messages/commit`, {
        method: "POST",
        json: {
          text: vars.text,
          channel: vars.channel,
          sender_name: vars.sender_name,
          received_date: vars.received_date,
          attachments: vars.attachments,
          entries: vars.entries,
        },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filings", filingId] }),
  });
}

// ── 서버 관리자: 사무소 회원 관리 ───────────────────────────
export function useAdminOffices(statusFilter?: string) {
  const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
  return useQuery({
    queryKey: ["admin", "offices", statusFilter ?? "ALL"],
    queryFn: () => api<AdminOffice[]>(`/api/v1/admin/offices${qs}`),
    retry: false,
  });
}

export function useAdminOfficeDetail(officeId: string | null) {
  return useQuery({
    queryKey: ["admin", "office", officeId],
    queryFn: () => api<AdminOfficeDetail>(`/api/v1/admin/offices/${officeId}`),
    enabled: !!officeId,
  });
}

function invalidateAdmin(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["admin"] });
}

export function useApproveOffice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (officeId: string) =>
      api(`/api/v1/admin/offices/${officeId}/approve`, { method: "POST", json: {} }),
    onSuccess: () => invalidateAdmin(qc),
  });
}

export function useRejectOffice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (officeId: string) =>
      api(`/api/v1/admin/offices/${officeId}/reject`, { method: "POST", json: {} }),
    onSuccess: () => invalidateAdmin(qc),
  });
}

export function useUpdateOffice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      officeId: string;
      customer_class?: string;
      subscription_start?: string | null;
      subscription_end?: string | null;
      admin_memo?: string | null;
    }) => {
      const { officeId, ...body } = vars;
      return api(`/api/v1/admin/offices/${officeId}`, { method: "PATCH", json: body });
    },
    onSuccess: () => invalidateAdmin(qc),
  });
}

export function useAddPromotion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      officeId: string;
      name: string;
      discount?: string | null;
      start_date?: string | null;
      end_date?: string | null;
      memo?: string | null;
    }) => {
      const { officeId, ...body } = vars;
      return api<Promotion>(`/api/v1/admin/offices/${officeId}/promotions`, {
        method: "POST",
        json: body,
      });
    },
    onSuccess: () => invalidateAdmin(qc),
  });
}

export function useDeletePromotion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (promotionId: string) =>
      api(`/api/v1/admin/promotions/${promotionId}`, { method: "DELETE" }),
    onSuccess: () => invalidateAdmin(qc),
  });
}

export function useEmployeeChanges(status: "PENDING" | "ALL") {
  return useQuery({
    queryKey: ["employee-changes", status],
    queryFn: () =>
      api<EmployeeChangeRequest[]>(`/api/v1/employee-changes?status=${status}`),
  });
}

export function useReviewEmployeeChange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { requestId: string; action: "approve" | "reject" }) =>
      api<EmployeeChangeRequest>(
        `/api/v1/employee-changes/${vars.requestId}/${vars.action}`,
        { method: "POST" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["employee-changes"] });
      // 승인 시 직원 마스터가 바뀐다 — 거래처 화면의 직원 목록도 다시 받는다.
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
  });
}
