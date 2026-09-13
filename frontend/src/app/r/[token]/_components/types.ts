export type PortalState =
  | "NONE"
  | "COLLECTING"
  | "REVIEWING"
  | "FILED"
  | "PAID"
  | "OVERDUE";

export type SessionInfo = {
  client_name: string;
  period: string;
  accepting: boolean;
  has_pin: boolean;
};

export type PortalStatusInfo = {
  state: PortalState;
  period: string | null;
  due_date: string | null;
  estimated_tax: number;
  settled_tax: number | null;
  virtual_account: string | null;
  epayment_number: string | null;
  has_receipt: boolean;
  has_payment_slip: boolean;
  tax_office_name: string;
};

export type LastMonthEntry = {
  name: string;
  income_type: string;
  total_amount: number;
};

export type LastMonthInfo = {
  period: string | null;
  employee_count: number;
  total_amount: number;
  total_tax: number;
  net_amount: number;
  entries: LastMonthEntry[] | null;
};

export type MonthlyCostPoint = {
  period: string;
  wage: number;
  business: number;
  daily: number;
  other: number;
  total: number;
};

export type MonthlyCostReport = {
  kpis: { total: number; monthly_avg: number; yoy_pct: number | null };
  series: MonthlyCostPoint[];
};

export type EmployeeRow = {
  id: string;
  name: string;
  status: string;
  position: string | null;
  department: string | null;
  income_type: string | null;
  hired_at: string | null;
};

export type EmployeeHistoryRow = {
  period: string;
  total_amount: number;
  tax: number;
  net_amount: number;
};

export type EmployeeDetail = {
  id: string;
  name: string;
  position: string | null;
  department: string | null;
  hired_at: string | null;
  resigned_at: string | null;
  status: string;
  income_type: string | null;
  total_ytd: number | null;
  monthly_avg: number | null;
  tax_ytd: number | null;
  history: EmployeeHistoryRow[] | null;
};

export type ArchiveRow = {
  period: string;
  estimated_tax: number;
  settled_tax: number | null;
  due_date: string | null;
  virtual_account: string | null;
  epayment_number: string | null;
  has_receipt: boolean;
  has_payment_slip: boolean;
};

export type PayrollRow = {
  name: string;
  total_amount: number;
  prev_amount: number | null;
};

export type SubmitResult = {
  matched: number;
  new_hire_suspected: number;
  resignation_suspected: number;
  ambiguous: number;
  needs_followup?: number;
  unconfirmed?: number;
};

export type ViewKey = "filing" | "payment" | "cost" | "employee";
