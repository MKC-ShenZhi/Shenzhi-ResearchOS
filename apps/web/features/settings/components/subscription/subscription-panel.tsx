"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billing, type BillingOrder, type BillingPlan } from "@/clients/backend/billing";
import type { SettingsLocale } from "@/clients/settings";
import Link from "next/link";
import { ArrowRight, Check, ChevronDown, CreditCard, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { UsagePanel } from "./usage-panel";
import { CheckoutDialog } from "./checkout-dialog";
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
  const [selected, setSelected] = useState<BillingPlan | null>(null);
  const ordersSection = useRef<HTMLElement>(null);
  const query = useQuery({
    queryKey: key,
    queryFn: async () => {
      const [plans, subscription, orders] = await Promise.all([billing.plans(userId), billing.subscription(userId), billing.orders(userId)]);
      return { plans, subscription, orders };
    },
  });
  const mutation = useMutation({
    mutationFn: (input: { order: BillingOrder; action: "refresh" | "mock-pay" | "payment" }) =>
      billing.action(userId, input.order.order_id, input.action),
    onSuccess: () => { void cache.invalidateQueries({ queryKey: ["entitlement-usage", userId] }); },
    onSettled: () => { void cache.invalidateQueries({ queryKey: key }); },
  });
  const zh = locale === "zh-CN";
  const data = query.data;
  const adminManaged = data?.subscription.status === "active" && data.subscription.source !== "billing";
  const error = mutation.error ?? query.error;
  const planName = (id: string | null) => data?.plans.items.find((plan) => plan.plan_id === id)?.name ?? id ?? t.none;
  const money = (amount: number, currency: string) => new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount / 100);
  const descriptions: Record<string, string> = zh
    ? { basic: "为日常阅读与轻量探索准备", pro: "让持续研究拥有更充足的空间", research: "为高频、深入的研究工作而设" }
    : { basic: "For everyday reading and exploration", pro: "More room for your ongoing research", research: "For intensive research workflows" };
  return <div className="space-y-6 text-ink">
    <header className="py-2"><p className="mb-2 text-[10px] font-semibold tracking-[0.22em] text-primary">SHENZHI / MEMBERSHIP</p><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{zh ? "让好奇，走得更远。" : "Take your curiosity further."}</h2><p className="mt-3 text-sm leading-6 text-muted">{zh ? "选择适合你的研究节奏，把时间留给发现。" : "Find the allowance that fits your research. Make more time for discovery."}</p></header>
    {error && !selected && <div role="alert" className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-sm text-danger">{error.message === "UNFINISHED_ORDER_PLAN_CONFLICT" ? t.conflict : error.message === "PAYMENT_QUERY_IDENTITY_UNVERIFIED" ? t.identity : error.message}{query.isError && <Button variant="ghost" size="sm" onClick={() => void query.refetch()}>{zh ? "重试" : "Retry"}</Button>}</div>}
    {query.isPending && <div role="status" className="h-36 animate-pulse rounded-2xl border border-line bg-card p-6 text-sm text-muted">{t.loading}</div>}
    {data && <>
      <section className="relative overflow-hidden rounded-2xl border border-primary/15 bg-card p-6 sm:p-7">
        <div aria-hidden="true" className="pointer-events-none absolute -right-14 -top-24 size-64 rounded-full border border-primary/10 bg-primary/5" />
        <div className="relative flex flex-wrap items-center justify-between gap-5"><div><p className="text-xs text-muted">{t.title}</p><div className="mt-2 flex flex-wrap items-center gap-3"><h3 className="text-xl font-semibold">{planName(data.subscription.plan_id)}</h3><span className={cn("rounded-full px-2.5 py-1 text-[11px]", data.subscription.status === "active" ? "bg-agent-soft text-agent" : "bg-chip text-muted")}>{t[data.subscription.status]}</span></div><p className="mt-3 text-xs text-muted">{data.subscription.expires_at ? `${t.expires} ${new Date(data.subscription.expires_at).toLocaleDateString(locale, { year: "numeric", month: "long", day: "numeric" })}` : data.subscription.plan_id ? t.permanent : (zh ? "可在下方选择你的研究套餐" : "Choose your research plan below")}</p></div><Link href="/settings?tab=usage" className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-4 py-2.5 text-xs font-medium hover:bg-chip">{zh ? "查看我的用量" : "View my usage"}<ArrowRight className="size-3.5" aria-hidden="true" /></Link></div>
      </section>
      <section aria-labelledby="plans-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2"><h2 id="plans-heading" className="text-base font-semibold">{zh ? "为你的下一步研究" : "For your next discovery"}</h2><span className="text-xs text-muted">{zh ? "按次购买 · 手动续费" : "One-time purchase · Manual renewal"}</span></div>
        <div className="grid gap-4 md:grid-cols-3">{data.plans.items.map((plan) => {
          const current = data.subscription.status === "active" && data.subscription.plan_id === plan.plan_id;
          const blocked = !plan.purchasable || data.plans.payment_mode === "disabled" || adminManaged || data.subscription.status === "disabled" || (data.subscription.status === "active" && !current);
          const reason = !plan.purchasable ? t.unpublished : data.plans.payment_mode === "disabled" ? t.unavailable : adminManaged ? (zh ? "管理员维护" : "Admin managed") : data.subscription.status === "disabled" ? t.disabled : t.change;
          return <article key={plan.plan_id} className={cn("relative flex flex-col rounded-2xl border bg-card p-5 transition-shadow hover:shadow-card sm:p-6", current ? "border-primary ring-1 ring-primary/10" : "border-line")}>
            <div className="mb-5 flex min-h-6 items-center justify-between gap-2"><span className="text-sm font-semibold">{locale === "en" ? plan.plan_id : plan.name}</span>{current && <span className="rounded-full bg-primary-soft px-2 py-1 text-[10px] font-medium text-primary">{zh ? "当前套餐" : "Your plan"}</span>}</div>
            <p className="min-h-10 text-xs leading-5 text-muted">{descriptions[plan.plan_id] ?? (zh ? "探索适合你的科研额度" : "Explore your research allowance")}</p>
            <p className="mt-4 flex flex-wrap items-baseline gap-1"><span className="text-3xl font-semibold tracking-tight">{money(plan.amount, plan.currency)}</span><span className="text-xs text-muted">/ {plan.duration_days} {t.days}</span></p>
            <p className="mt-2 min-h-4 text-[10px] text-muted">{plan.test_price ? t.test : (zh ? "单次购买价格" : "Per purchase")}</p>
            <Button className="mt-6 w-full" variant={current ? "default" : "outline"} disabled={blocked || mutation.isPending} aria-describedby={blocked ? `plan-reason-${plan.plan_id}` : undefined} onClick={() => { mutation.reset(); setSelected(plan); }}>{blocked ? (zh ? "暂不可选" : "Unavailable") : current ? (zh ? "续费套餐" : "Renew plan") : (zh ? "选择套餐" : "Select plan")}{!blocked && <ArrowRight aria-hidden="true" />}</Button>
            <div className="mt-6 border-t border-line pt-5"><p className="text-[10px] tracking-wide text-muted">{zh ? "每日研究额度" : "DAILY ALLOWANCE"}</p><p className="mt-2 text-xl font-semibold tabular-nums">{plan.daily_tokens.toLocaleString(locale)}<span className="ml-1.5 text-xs font-normal text-muted">Token</span></p><p className="mt-3 flex items-center gap-2 text-xs text-ink-2"><Check className="size-3.5 text-agent" aria-hidden="true" />{zh ? "每日额度，按实际用量结算" : "Daily allowance, settled by actual usage"}</p><p className="mt-3 min-h-8 text-[11px] leading-4 text-muted" id={`plan-reason-${plan.plan_id}`}>{blocked ? reason : (zh ? "购买前可确认金额与支付方式" : "Review price and payment method before purchase")}</p></div>
          </article>;
        })}</div>
        <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-muted"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{adminManaged ? t.managed : zh ? "有效期内支持同套餐续费，暂不支持切换套餐。续费会延长有效期，不会重置当日额度。" : "Renew your current plan during its active term. Plan changes are unavailable. Renewal extends validity without resetting today's allowance."}</p>
      </section>
      {selected && <CheckoutDialog plan={selected} locale={locale} userId={userId} paymentMode={data.plans.payment_mode}
        pendingOrder={data.orders.items.find((order) => order.plan_id === selected.plan_id && order.payment_status === "pending")}
        onClose={() => setSelected(null)}
        onUpdated={() => { void cache.invalidateQueries({ queryKey: key }); void cache.invalidateQueries({ queryKey: ["entitlement-usage", userId] }); }}
        onViewOrders={() => {
          setSelected(null);
          requestAnimationFrame(() => { ordersSection.current?.scrollIntoView({ behavior: "smooth", block: "start" }); ordersSection.current?.focus({ preventScroll: true }); });
        }} />}
      <UsagePanel locale={locale} userId={userId} compact />
      <section ref={ordersSection} tabIndex={-1} aria-label={t.recent} className="scroll-mt-6 overflow-hidden rounded-2xl border border-line bg-card outline-none focus-visible:ring-2 focus-visible:ring-primary"><div className="flex items-center justify-between border-b border-line p-5 sm:px-6"><h2 className="flex items-center gap-2 text-sm font-semibold"><CreditCard className="size-4 text-muted" aria-hidden="true" />{t.recent}</h2><span className="text-xs text-muted">{data.orders.items.length} {zh ? "笔记录" : "orders"}</span></div>
        {data.orders.items.length === 0 ? <p className="p-6 text-sm text-muted">{zh ? "还没有订单，选择套餐开启你的研究之旅。" : "No orders yet. Choose a plan to get started."}</p> : <div className="divide-y divide-line">{data.orders.items.map((order) => <details key={order.order_id} open={order.fulfillment_status !== "completed" && order.payment_status !== "closed"} className="group p-5 sm:px-6">
          <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-primary"><div className="min-w-0 flex-1"><p className="text-sm font-medium">{planName(order.plan_id)}<span className="ml-3 font-normal text-muted">{money(order.amount, order.currency)}</span></p><p className="mt-1 text-xs text-muted">{new Date(order.created_at).toLocaleDateString(locale)} · {t[order.channel]}</p></div><span className={cn("text-xs", order.fulfillment_status === "completed" ? "text-agent" : "text-muted")}>{order.fulfillment_status === "completed" ? (zh ? "已完成" : "Completed") : t[order.payment_status]}</span><ChevronDown className="size-4 text-muted transition-transform group-open:rotate-180" aria-hidden="true" /></summary>
          <div className="mt-4 space-y-3 border-t border-line pt-4"><p className="break-all text-[11px] text-muted">{zh ? "订单号：" : "Order: "}{order.order_id}</p><p role="status" className="text-xs">{order.fulfillment_status === "completed" ? t.completed : t[order.payment_status]}</p>
            {order.fulfillment_error && <p className="text-sm text-muted">{order.fulfillment_error === "ACTIVE_GRANTS_REQUIRE_DRAIN" ? t.drain : t.blocked}</p>}
            {order.payment_status === "pending" && <>
              {order.payment.code_url && <div className="w-fit rounded-xl border border-line bg-white p-3"><PaymentCode key={order.payment.code_url} value={order.payment.code_url} label={t.scan} /><p className="mt-2 text-center text-xs text-gray-600">{t.scan}</p></div>}
              {order.payment.redirect_url && <a className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary-deep" href={order.payment.redirect_url} target="_blank" rel="noopener noreferrer">{t.pay}<ArrowRight className="size-3.5" aria-hidden="true" /></a>}
              {!order.payment.kind && <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "payment" })}>{t.prepare}</Button>}
              {order.mode === "mock" && data.plans.payment_mode === "mock" && <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "mock-pay" })}>{t.confirm}</Button>}
            </>}
            {order.payment_status !== "closed" && order.fulfillment_status !== "completed" && <div><Button variant="outline" size="sm" disabled={mutation.isPending} onClick={() => mutation.mutate({ order, action: "refresh" })}>{t.refresh}</Button></div>}
          </div>
        </details>)}</div>}
      </section>
      <details className="rounded-xl px-1 text-xs text-muted"><summary className="cursor-pointer py-1">{zh ? "订阅与续费说明" : "About subscriptions and renewals"}</summary><p className="py-3 leading-6">{t.renew}</p></details>
    </>}
  </div>;
}
