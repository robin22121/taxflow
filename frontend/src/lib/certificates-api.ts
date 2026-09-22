"use client";

// 증명원 발급 메뉴 API 클라이언트 (backend/app/api/certificates.py). plan/17 §4-9.

import { api, apiBlob } from "./api";
import type { RpaJob } from "./rpa-api";

export type CertCategory = "HOMETAX" | "WETAX" | "EMPLOYEE";

export type CatalogItem = {
  code: string;
  category: CertCategory;
  title: string;
  available: boolean;
  period: boolean; // 기간 입력 필요 → 최근 1·3·5년
  note: string | null; // 발급 대상 제한 안내
};

export const PERIOD_YEARS = [1, 3, 5] as const;
export type PeriodYears = (typeof PERIOD_YEARS)[number];

export type CertificateIssue = {
  id: string;
  client_id: string;
  rpa_job_id: string;
  employee_id: string | null;
  cert_type: string;
  title: string;
  options: Record<string, unknown> | null;
  status: "REQUESTED" | "RUNNING" | "ISSUED" | "FAILED" | "CANCELED";
  business_number: string | null;
  business_name: string;
  issued_at: string | null;
  local_path: string | null;
  file_name: string | null;
  has_file: boolean;
  expires_at: string | null;
  failure_reason: string | null;
  folder_open_requested_at: string | null;
  folder_opened_at: string | null;
  deliveries: { channel: string; to: string; at: string; accepted: boolean }[] | null;
  created_at: string;
};

export type CertificateJob = { job: RpaJob; issues: CertificateIssue[] };

export type DeliverResult = { accepted: boolean; channel: string; to: string; body: string; error: string | null };

export function getCatalog(): Promise<CatalogItem[]> {
  return api<CatalogItem[]>("/api/v1/certificates/catalog");
}

export type IssueRequestInput = {
  clientId: string;
  certTypes: string[];
  rrnDisclosed: boolean;
  periodYears: PeriodYears;
  employeeIds: string[]; // 직원용 증명서 대상
  purpose: string; // 직원용 증명서 '용도'
};

export function createIssueRequest(input: IssueRequestInput): Promise<CertificateJob> {
  return api<CertificateJob>("/api/v1/certificates/issue-requests", {
    method: "POST",
    json: {
      client_id: input.clientId,
      cert_types: input.certTypes,
      rrn_disclosed: input.rrnDisclosed,
      period_years: input.periodYears,
      employee_ids: input.employeeIds,
      purpose: input.purpose || null,
    },
  });
}

export function getCertificateJob(jobId: string): Promise<CertificateJob> {
  return api<CertificateJob>(`/api/v1/certificates/jobs/${jobId}`);
}

export function requestOpenFolder(jobId: string): Promise<CertificateJob> {
  return api<CertificateJob>(`/api/v1/certificates/jobs/${jobId}/open-folder`, { method: "POST" });
}

export function deliverCertificates(jobId: string, channel: "sms" | "alimtalk", phone: string): Promise<DeliverResult> {
  return api<DeliverResult>(`/api/v1/certificates/jobs/${jobId}/deliver`, {
    method: "POST",
    json: { channel, phone },
  });
}

export function getIssueFile(issueId: string): Promise<Blob> {
  return apiBlob(`/api/v1/certificates/issues/${issueId}/file`);
}
