import { apiJson, expectedUserHeaders } from "./http";

export type BillingPlan = {
  plan_id: string; name: string; daily_tokens: number; amount: number;
  currency: string; duration_months: number; purchasable: boolean; test_price: boolean;
};
export type Subscription = {
  plan_id: string | null; status: "unassigned" | "active" | "expired" | "disabled";
  expires_at: string | null; source: string | null; transition_pending_reason?: string | null;
};
export type BillingOrder = {
  order_id: string; plan_id: string; amount: number; currency: string;
  channel: "wechat" | "alipay"; mode: "mock" | "live";
  payment_status: "pending" | "paid" | "closed";
  fulfillment_status: "pending" | "completed"; fulfillment_error: string | null;
  created_at: string; payment: { kind?: string; code_url?: string; redirect_url?: string };
  action?: "purchase" | "renew" | "upgrade"; subscription_expires_at?: string | null;
  quote_expires_at?: string | null;
};
export type BillingQuote = {
  action: "upgrade"; plan_id: string; amount: number; currency: string;
  quoted_at: string; quote_expires_at: string; quote_token: string;
  subscription_expires_at: string;
};
export const billing = {
  plans: (userId: string) => apiJson<{ items: BillingPlan[]; payment_mode: string }>("/billing/plans", { headers: expectedUserHeaders(userId) }),
  subscription: (userId: string) => apiJson<Subscription>("/billing/subscription", { headers: expectedUserHeaders(userId) }),
  orders: (userId: string) => apiJson<{ items: BillingOrder[] }>("/billing/orders", { headers: expectedUserHeaders(userId) }),
  quote: (userId: string, plan_id: string) => apiJson<BillingQuote>("/billing/quote", {
    method: "POST", headers: expectedUserHeaders(userId), body: JSON.stringify({ plan_id }),
  }),
  create: (userId: string, plan_id: string, channel: string, expected_quote?: Pick<BillingQuote, "quoted_at" | "quote_token">) => apiJson<BillingOrder>("/billing/orders", {
    method: "POST", headers: expectedUserHeaders(userId), body: JSON.stringify({ plan_id, channel, ...(expected_quote ? { expected_quote } : {}) }),
  }),
  action: (userId: string, id: string, action: "refresh" | "mock-pay" | "payment") => apiJson<BillingOrder>(
    `/billing/orders/${encodeURIComponent(id)}/${action}`, { method: "POST", headers: expectedUserHeaders(userId) }),
};
