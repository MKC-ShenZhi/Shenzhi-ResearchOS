"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billing, type BillingOrder } from "@/clients/backend/billing";
import type { SettingsLocale } from "@/clients/settings";
import { Button } from "@/components/ui/button";

function PaymentCode({ value, label }: { value: string; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    void import("qrcode").then((qr) => {
      if (active && canvas.current) return qr.toCanvas(canvas.current, value, { width: 240, margin: 4 });
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [value]);
  return <div>{error ? <p role="alert">{label}: {value}</p> : <canvas ref={canvas} role="img" aria-label={label} className="max-w-full" />}</div>;
}

const text = {
  "zh-CN": {
    login: "请登录后查看和购买订阅。", title: "当前订阅", none: "未分配套餐", permanent: "长期权益",
    expires: "有效期至", active: "生效中", expired: "已到期", disabled: "已停用", unassigned: "未分配",
    test: "测试价格 · 不代表正式售价", mock: "当前为 Mock 支付（开发测试），不会真实扣款。",
    unavailable: "支付尚未启用", buy: "购买 / 续费", unpublished: "暂不可购买", days: "天", tokens: "Token / 天",
    method: "支付方式", wechat: "微信支付", alipay: "支付宝", recent: "近期订单", pay: "前往支付宝支付",
    scan: "请使用微信扫描二维码支付", confirm: "模拟支付成功", refresh: "查询支付 / 重试履约",
    pending: "等待支付", paid: "已支付，等待权益到账", completed: "支付完成，权益已到账", closed: "订单已关闭",
    prepare: "获取支付入口", loading: "加载中…", renew: "主动购买和续费；有效期内仅支持同套餐续费。管理员长期付费权益不能被购买覆盖。",
    drain: "请等待当前 Agent 任务及用量结算结束，再重试权益发放。", blocked: "当前权益已变更，暂时无法发放；请联系管理员处理此已支付订单。",
    managed: "当前权益由管理员维护，不能通过购买覆盖。", change: "有效期内不可切换套餐",
    conflict: "已有其他套餐的未完成订单，请先完成支付及权益到账，再购买其他套餐。",
    identity: "支付宝查询无法验证收款身份，请等待支付通知确认后再查询订单。",
  },
  en: {
    login: "Sign in to view and purchase subscriptions.", title: "Current subscription", none: "No plan assigned", permanent: "Permanent entitlement",
    expires: "Valid until", active: "Active", expired: "Expired", disabled: "Disabled", unassigned: "Unassigned",
    test: "Test prices · final pricing pending", mock: "Mock payment mode (development). No real charge.",
    unavailable: "Payments are disabled", buy: "Purchase / renew", unpublished: "Unavailable", days: "days", tokens: "tokens / day",
    method: "Payment method", wechat: "WeChat Pay", alipay: "Alipay", recent: "Recent orders", pay: "Continue to Alipay",
    scan: "Scan with WeChat to pay", confirm: "Simulate successful payment", refresh: "Check payment / retry fulfillment",
    pending: "Awaiting payment", paid: "Paid, awaiting fulfillment", completed: "Payment complete, entitlement delivered", closed: "Order closed",
    prepare: "Get payment link", loading: "Loading…", renew: "Manual purchases and renewals. Active subscriptions support same-plan renewal only. Permanent paid Admin grants are preserved.",
    drain: "Wait for current Agent tasks and usage settlement to finish, then retry fulfillment.", blocked: "Your entitlement has changed. Contact an administrator about this paid order.",
    managed: "Your current entitlement is managed by an administrator and cannot be replaced by a purchase.", change: "Plan change unavailable",
    conflict: "An unfinished order exists for another plan. Complete payment and fulfillment before buying another plan.",
    identity: "Alipay query cannot verify the recipient. Wait for the payment notification, then check again.",
  },
};

export function SubscriptionPanel({ locale, userId }: { locale: SettingsLocale; userId?: string }) {
  const t = text[locale];
  return userId ? <SubscriptionForUser key={userId} userId={userId} locale={locale} /> : <p>{t.login}</p>;
}

function SubscriptionForUser({ locale, userId }: { locale: SettingsLocale; userId: string }) {
  const t = text[locale];
  const cache = useQueryClient();
  const key = ["billing", userId];
  const [channel, setChannel] = useState<"wechat" | "alipay">("wechat");
  const query = useQuery({
    queryKey: key,
    queryFn: async () => {
      const [plans, subscription, orders] = await Promise.all([billing.plans(userId), billing.subscription(userId), billing.orders(userId)]);
      return { plans, subscription, orders };
    },
  });
  const mutation = useMutation({
    mutationFn: (input: { plan: string } | { order: BillingOrder; action: "refresh" | "mock-pay" | "payment" }) =>
      "plan" in input ? billing.create(userId, input.plan, channel) : billing.action(userId, input.order.order_id, input.action),
    onSettled: () => { void cache.invalidateQueries({ queryKey: key }); },
  });
  const data = query.data;
  const adminManaged = data?.subscription.status === "active" && data.subscription.source !== "billing";
  const error = mutation.error ?? query.error;
  return <div className="space-y-6">
    {error && <p role="alert" className="text-sm text-red-600">{error.message === "UNFINISHED_ORDER_PLAN_CONFLICT" ? t.conflict : error.message === "PAYMENT_QUERY_IDENTITY_UNVERIFIED" ? t.identity : error.message}</p>}
    {query.isPending && <p role="status">{t.loading}</p>}
    {data && <>
      <section className="rounded-2xl bg-card p-6 shadow-card">
        <h2 className="font-semibold text-ink">{t.title}</h2>
        <p className="mt-3">{data.subscription.plan_id ?? t.none} · {t[data.subscription.status]}</p>
        <p className="mt-2 text-sm text-muted">{data.subscription.expires_at ? `${t.expires} ${new Date(data.subscription.expires_at).toLocaleString(locale)}` : data.subscription.plan_id ? t.permanent : ""}</p>
      </section>
      <p className="text-sm text-muted">{t.renew}</p>
      {adminManaged && <p className="text-sm" role="status">{t.managed}</p>}
      <p className="text-sm">{data.plans.payment_mode === "mock" ? t.mock : data.plans.payment_mode === "disabled" ? t.unavailable : t.test}</p>
      <fieldset className="flex flex-wrap gap-4"><legend className="mb-2 text-sm font-medium">{t.method}</legend>
        {(["wechat", "alipay"] as const).map((value) => <label key={value} className="flex items-center gap-2 text-sm"><input type="radio" name="payment-channel" value={value} checked={channel === value} onChange={() => setChannel(value)} />{t[value]}</label>)}
      </fieldset>
      <div className="grid gap-4 md:grid-cols-3">{data.plans.items.map((plan) => <section key={plan.plan_id} className="rounded-2xl bg-card p-5 shadow-card">
        <h3 className="font-semibold">{locale === "en" ? plan.plan_id : plan.name}</h3>
        <p className="mt-3 text-xl">¥{(plan.amount / 100).toFixed(2)} / {plan.duration_days} {t.days}</p>
        <p className="mt-1 text-xs text-muted">{t.test}</p>
        <p className="my-4 text-sm">{plan.daily_tokens.toLocaleString(locale)} {t.tokens}</p>
        <Button disabled={!plan.purchasable || mutation.isPending || data.plans.payment_mode === "disabled" || adminManaged || data.subscription.status === "disabled" || (data.subscription.status === "active" && data.subscription.plan_id !== plan.plan_id)} onClick={() => mutation.mutate({ plan: plan.plan_id })}>{!plan.purchasable ? t.unpublished : data.subscription.status === "active" && data.subscription.plan_id !== plan.plan_id ? t.change : t.buy}</Button>
      </section>)}</div>
      <section><h2 className="mb-3 font-semibold">{t.recent}</h2><div className="space-y-4">{data.orders.items.map((order) => <article key={order.order_id} className="space-y-3 rounded-2xl bg-card p-5 shadow-card">
        <p className="text-sm">{order.plan_id} · ¥{(order.amount / 100).toFixed(2)} · {t[order.channel]}</p>
        <p className="break-all text-xs text-muted">{order.order_id}</p>
        <p role="status" className="text-sm font-medium">{order.fulfillment_status === "completed" ? t.completed : t[order.payment_status]}</p>
        {order.fulfillment_error && <p className="text-sm text-muted">{order.fulfillment_error === "ACTIVE_GRANTS_REQUIRE_DRAIN" ? t.drain : t.blocked}</p>}
        {order.payment_status === "pending" && <>
          {order.payment.code_url && <PaymentCode key={order.payment.code_url} value={order.payment.code_url} label={t.scan} />}
          {order.payment.redirect_url && <a className="text-primary underline" href={order.payment.redirect_url} target="_blank" rel="noopener noreferrer">{t.pay}</a>}
          {!order.payment.kind && <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "payment" })}>{t.prepare}</Button>}
          {order.mode === "mock" && data.plans.payment_mode === "mock" && <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "mock-pay" })}>{t.confirm}</Button>}
        </>}
        {order.payment_status !== "closed" && order.fulfillment_status !== "completed" && <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "refresh" })}>{t.refresh}</Button>}
      </article>)}</div></section>
    </>}
  </div>;
}
