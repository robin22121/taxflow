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

export type PayrollEntry = {
  id: string;
  client_id: string;
  employee_id: string | null;
  raw_name: string;
  income_type: string;
  total_amount: number;
  non_taxable: number;
  taxable: number;
  income_tax: number;
  local_tax: number;
  payment_date: string | null;
  match_status: string;
  prev_amount: number | null;
  anomaly_notes: Record<string, unknown> | null;
  approved: boolean;
};
