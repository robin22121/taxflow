export type CurrentUser = {
  id: string;
  email: string;
  name: string;
  tax_office_id: string | null;
  is_admin: boolean;
  is_superadmin: boolean;
  short_code: string | null;
  office_name: string | null;
  office_phone: string | null;
  office_email: string | null;
  office_address: string | null;
  office_representative: string | null;
};

export type RegisterResponse = {
  office_id: string;
  short_code: string;
  approval_status: string;
  message: string;
};

// ── 서버 관리자 회원 관리 ───────────────────────────────
export type Promotion = {
  id: string;
  name: string;
  discount: string | null;
  start_date: string | null;
  end_date: string | null;
  memo: string | null;
  granted_by: string | null;
  created_at: string;
};

export type AdminOffice = {
  id: string;
  name: string;
  business_number: string | null;
  representative: string | null;
  phone: string | null;
  email: string | null;
  short_code: string | null;
  approval_status: "PENDING" | "APPROVED" | "REJECTED";
  customer_class: "TRIAL" | "REGULAR" | "VIP" | "CHURNED";
  subscription_start: string | null;
  subscription_end: string | null;
  admin_memo: string | null;
  approved_at: string | null;
  created_at: string;
  user_count: number;
  promotion_count: number;
};

export type AdminOfficeDetail = AdminOffice & {
  promotions: Promotion[];
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type Client = {
  id: string;
  business_name: string;
  business_number: string | null;
  representative: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  is_corporation: boolean;
  collect_email: string | null;
  invite_sent: boolean;
};

export type PayrollDefault = {
  meal_default: number;
  car_default: number;
  childcare_default: number;

  apply_national_pension: boolean;
  apply_health_insurance: boolean;
  apply_employment_insurance: boolean;
  apply_longterm_care: boolean;

  nps_rate_percent: number;
  hi_rate_percent: number;
  ltc_rate_percent: number;
  ei_rate_percent: number;

  note: string | null;

  system_nps_rate_percent: number;
  system_hi_rate_percent: number;
  system_ltc_rate_percent: number;
  system_ei_rate_percent: number;
};

export type PayrollDefaultPatch = Partial<Omit<PayrollDefault,
  | "system_nps_rate_percent"
  | "system_hi_rate_percent"
  | "system_ltc_rate_percent"
  | "system_ei_rate_percent"
>>;

export type ChannelAttempt = {
  channel: string;
  accepted: boolean;
  error: string | null;
};

export type ClientInviteResult = {
  sent: boolean;
  channels: string[];
  attempts?: ChannelAttempt[];  // 옛 백엔드 응답엔 없음 (배포 타이밍 대비)
  filing_period: string;
  detail: string | null;
};

export type Filing = {
  id: string;
  period: string;
  status: string;
  total_clients: number;
  total_entries: number;
};

export type SessionAttachment = {
  filename: string;
  storage_key: string;
  kind: string;  // "image" | "pdf" | "excel" | "csv" | "audio" | ...
  event_id: string;
  channel: string;
  received_at: string | null;
};

export type SessionTimelineEvent = {
  id: string;
  at: string | null;
  direction: "out" | "in" | "system";
  channel: string;
  event_type: string;
  label: string;
  sender_name: string | null;
  detail: string;
};

export type CollectionSession = {
  id: string;
  client_id: string;
  client_name: string;
  status: string;
  request_token: string;
  has_responses: boolean;
  has_anomalies: boolean;
  entry_count: number;
};

export type FilingDashboard = {
  filing: Filing;
  sessions: CollectionSession[];
};

export type Employee = {
  id: string;
  name: string;
  employee_code: string | null;
  hired_at: string | null;
  resigned_at: string | null;
  rrn_last4: string | null;
  status: string;
  business_type_code: string | null;
};

export type ImportEmployeeResult = {
  total_rows: number;
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
  employees: Employee[];
};

export type ImportPayrollResult = {
  period: string;
  total_rows: number;
  matched: number;
  unmatched: number;
  created_entries: number;
  errors: string[];
};

export type SourceEvent = {
  id: string;
  channel: string | null;
  sender_name: string | null;
  received_date: string | null;
  raw_text: string | null;
  created_at: string | null;
};

export type InsuranceKind = "acquisition" | "loss" | "change";

export type InsuranceTarget = {
  kind: InsuranceKind;
  client_id: string;
  employee_id: string;
  name: string;
  rrn_last4: string | null;
  monthly_wage: number;
  total_amount: number;
  national_pension: number;
  health_insurance: number;
  longterm_care: number;
  employment_insurance: number;
  // 자격취득 전용
  hired_at: string | null;
  acquisition_code: string | null;
  // 자격상실 전용
  resigned_at: string | null;
  loss_code: string | null;
  // 보수월액 변경 전용
  prev_amount: number | null;
  change_pct: number | null;
  reason_code: string | null;
  nps_eligible: boolean | null;
  nps_within_limit: boolean | null;
  nps_consent_required: boolean | null;
};

export type InsuranceSummary = {
  period: string;
  acquisitions: InsuranceTarget[];
  losses: InsuranceTarget[];
  changes: InsuranceTarget[];
};

export type PayrollEntry = {
  id: string;
  client_id: string;
  employee_id: string | null;
  collection_event_id: string | null;
  raw_name: string;
  income_type: string;
  a_code: string | null;
  business_type_code: string | null;
  total_amount: number;
  salary_amount: number | null;
  bonus_amount: number | null;
  non_taxable: number;
  meal_amount: number;
  car_amount: number;
  childcare_amount: number;
  taxable: number;
  national_pension: number;
  health_insurance: number;
  employment_insurance: number;
  longterm_care: number;
  income_tax: number;
  local_tax: number;
  payment_date: string | null;
  match_status: string;
  prev_amount: number | null;
  anomaly_notes: Record<string, unknown> | null;
  approved: boolean;
  source_event: SourceEvent | null;
};
