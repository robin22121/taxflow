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
  CurrentUser,
  Employee,
  Filing,
  FilingDashboard,
  ImportEmployeeResult,
  ImportPayrollResult,
  PayrollEntry,
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

export function useClientDetail(clientId: string) {
  return useQuery({
    queryKey: ["clients", clientId],
    queryFn: () => api<Client>(`/api/v1/clients/${clientId}`),
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
    mutationFn: () =>
      api(`/api/v1/filings/${filingId}/request`, { method: "POST", json: {} }),
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
