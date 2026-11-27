export type UsageWindow = {
  rule_id: string; metric: string; purpose: string; capability_id: string | null;
  limit: number; used: number; held: number; remaining: number;
  window_start: string | null; window_end: string | null;
  window_type: string; duration_seconds: number | null; accounting_basis: string;
};
export type AdminUser = {
  user_id: string; name: string | null; email: string; created_at: string;
  plan_id: string | null; policy_revision: string | null;
  expires_at: string | null; source: string | null;
  entitlement_enabled: boolean | null; entitlement_status: string; model_calls_enabled: boolean; usage_windows: UsageWindow[];
};
export type AdminUsers = {
  items: AdminUser[]; total: number; page: number; page_size: number; plans: string[];
  stats: { total_users: number; free_users: number; abnormal_users: number };
  updated_at: string; usage_status: string; usage_note: string;
};
export type Plan = {plan_id: 'basic'|'pro'|'research'; name:string; daily_tokens:number; deep_research:boolean; policy_revision:string|null; published:boolean; model_risk_ready:boolean; capabilities:string[]; published_at:string|null};
