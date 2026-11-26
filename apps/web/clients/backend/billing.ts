import { apiJson, expectedUserHeaders } from "./http";

export type BillingPlan = {
  plan_id: string; name: string; daily_tokens: number; amount: number;
  currency: string; duration_days: number; purchasable: boolean; test_price: boolean;
};
export type Subscription = {
  plan_id: string | null; status: "unassigned" | "active" | "expired" | "disabled";
  expires_at: string | null; source: string | null;
};
export type BillingOrder = {
  order_id: string; plan_id: string; amount: number; currency: string;
  channel: "wechat" | "alipay"; mode: "mock" | "live";
  payment_status: "pending" | "paid" | "closed";
  fulfillment_status: "pending" | "completed"; fulfillment_error: string | null;
  created_at: string; payment: { kind?: string; code_url?: string; redirect_url?: string };
};
export const billing = {
  plans: (userId: string) => apiJson<{ items: BillingPlan[]; payment_mode: string }>("/billing/plans", { headers: expectedUserHeaders(userId) }),
  subscription: (userId: string) => apiJson<Subscription>("/billing/subscription", { headers: expectedUserHeaders(userId) }),
  orders: (userId: string) => apiJson<{ items: BillingOrder[] }>("/billing/orders", { headers: expectedUserHeaders(userId) }),
  create: (userId: string, plan_id: string, channel: string) => apiJson<BillingOrder>("/billing/orders", {
    method: "POST", headers: expectedUserHeaders(userId), body: JSON.stringify({ plan_id, channel }),
  }),
  action: (userId: string, id: string, action: "refresh" | "mock-pay" | "payment") => apiJson<BillingOrder>(
    `/billing/orders/${encodeURIComponent(id)}/${action}`, { method: "POST", headers: expectedUserHeaders(userId) }),
};
