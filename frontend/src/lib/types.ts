export type CurrentUser = {
  id: string;
  email: string;
  name: string;
  tax_office_id: string;
  is_admin: boolean;
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

export type Filing = {
  id: string;
  period: string;
  status: string;
  total_clients: number;
  total_entries: number;
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

export type PayrollEntry = {
  id: string;
  client_id: string;
  employee_id: string | null;
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
};
