"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "./api";
import { apiUpload } from "./api";
import type {
  Client,
  ClientInviteResult,
  CurrentUser,
  Employee,
  Filing,
  FilingDashboard,
  ImportEmployeeResult,
  ImportPayrollResult,
  PayrollEntry,
  SessionAttachment,
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

export function useFilingEntries(filingId: string) {
  return useQuery({
    queryKey: ["filings", filingId, "entries"],
    queryFn: () => api<PayrollEntry[]>(`/api/v1/filings/${filingId}/entries`),
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

export function useImportPayroll(clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { file: File; period: string }) =>
      apiUpload<ImportPayrollResult>(
        `/api/v1/clients/${clientId}/import-payroll?period=${vars.period}`,
        vars.file,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filings"] }),
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
    mutationFn: (vars: { sessionId: string; text: string }) =>
      api(`/api/v1/collect/sessions/${vars.sessionId}/messages`, {
        method: "POST",
        json: { text: vars.text, channel: "manual" },
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["filings", filingId] }),
  });
}
