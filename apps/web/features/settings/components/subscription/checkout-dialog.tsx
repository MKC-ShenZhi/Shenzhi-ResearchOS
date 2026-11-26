"use client";

import { useEffect, useId, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowUpRight, Check, CreditCard, LoaderCircle, X } from "lucide-react";
import { billing, type BillingOrder, type BillingPlan } from "@/clients/backend/billing";
import type { SettingsLocale } from "@/clients/settings";
import { Button } from "@/components/ui/button";

export function CheckoutDialog({ plan, pendingOrder, paymentMode, userId, locale, onClose, onUpdated, onViewOrders }: {
  plan: BillingPlan;
  pendingOrder?: BillingOrder;
  paymentMode: string;
  userId: string;
  locale: SettingsLocale;
  onClose: () => void;
  onUpdated: () => void;
  onViewOrders: () => void;
}) {
  const zh = locale === "zh-CN";
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const mutation = useMutation({
    mutationFn: () => pendingOrder
      ? billing.action(userId, pendingOrder.order_id, "payment")
      : billing.create(userId, plan.plan_id, "alipay"),
    onSuccess: (order) => {
      onUpdated();
      if (order.mode === "live" && order.payment_status === "pending" && order.channel === "alipay" && order.payment.redirect_url) {
        // Same-tab navigation also works after an async request without a popup permission.
        window.location.assign(order.payment.redirect_url);
      }
    },
    onError: () => {
      // A provider error can leave a persisted order. Refresh the recovery list.
      onUpdated();
    },
  });
  const order = mutation.data ?? pendingOrder;
  const legacyWechat = order?.channel === "wechat";
  const amount = new Intl.NumberFormat(locale, { style: "currency", currency: order?.currency ?? plan.currency }).format((order?.amount ?? plan.amount) / 100);
  const busy = mutation.isPending;

  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    const overflow = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = overflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);

  return <dialog ref={dialog} aria-labelledby={titleId} aria-describedby={descriptionId}
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}
    onKeyDown={(event) => {
      if (event.key !== "Tab") return;
      const controls = event.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), a[href]");
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }}
    className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none border-0 bg-transparent p-4 text-ink backdrop:bg-black/45 backdrop:backdrop-blur-[3px] open:flex open:items-center open:justify-center sm:p-6">
    <div className="max-h-full w-full max-w-[460px] overflow-y-auto rounded-2xl border border-line bg-card shadow-pop" aria-busy={busy}>
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <div><h2 id={titleId} className="text-lg font-semibold tracking-tight">{zh ? "确认订阅" : "Confirm subscription"}</h2><p id={descriptionId} className="mt-2 text-xs leading-5 text-muted">{zh ? "核对套餐与金额，再继续完成付款。" : "Review your plan and amount before continuing to payment."}</p></div>
        <Button autoFocus size="icon" variant="ghost" className="-mr-2 -mt-2 shrink-0" disabled={busy} aria-label={zh ? "关闭确认" : "Close review"} onClick={onClose}><X aria-hidden="true" /></Button>
      </div>

      <div className="px-6 pb-6">
        <div className="mt-5 rounded-xl border border-primary/10 bg-primary-soft/50 p-4">
          <div className="flex items-center gap-2"><span className="flex size-7 items-center justify-center rounded-lg bg-card text-primary"><CreditCard className="size-4" aria-hidden="true" /></span><h3 className="text-sm font-semibold">{locale === "en" ? plan.plan_id : plan.name}</h3></div>
          <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2"><span className="text-xs text-muted">{plan.duration_days} {zh ? "天使用权益" : "days of access"}</span><span className="text-2xl font-semibold tabular-nums tracking-tight">{amount}</span></div>
          <p className="mt-3 border-t border-primary/10 pt-3 text-xs text-ink-2">{plan.daily_tokens.toLocaleString(locale)} Token / {zh ? "天" : "day"}</p>
        </div>

        <fieldset className="mt-5"><legend className="mb-2.5 text-xs font-medium text-ink-2">{zh ? "支付方式" : "Payment method"}</legend>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center justify-between gap-2 rounded-lg border border-primary bg-primary-soft/40 px-3 py-3 text-sm text-primary"><span className="flex items-center gap-2"><input type="radio" name="checkout-channel" checked={!legacyWechat} disabled={legacyWechat} readOnly aria-label={zh ? "支付宝" : "Alipay"} className="accent-primary" /><span>{zh ? "支付宝" : "Alipay"}</span></span><Check className="size-3.5" aria-hidden="true" /></label>
            <label className="flex items-center gap-2 rounded-lg border border-line bg-chip/40 px-3 py-3 text-xs text-muted"><input type="radio" name="checkout-channel" checked={legacyWechat} readOnly disabled aria-label={zh ? "微信支付，暂未接入" : "WeChat Pay, unavailable"} /><span>{zh ? "微信支付" : "WeChat Pay"}<span className="mt-0.5 block text-[10px]">{zh ? "暂未接入" : "Unavailable"}</span></span></label>
          </div>
        </fieldset>

        <div className="mt-4 space-y-2 text-[11px] leading-5 text-muted">
          <p>{paymentMode === "mock" ? (zh ? "开发测试模式，不会真实扣款。" : "Development mode. No real charge.") : plan.test_price ? (zh ? "当前为测试价格，不代表正式售价。" : "Test price, not final pricing.") : (zh ? "单次购买，不会自动续费。" : "One-time purchase. No automatic renewal.")}</p>
          <p>{legacyWechat ? (zh ? "已有微信待支付订单，需在近期订单中继续处理，无法改为支付宝。" : "An existing WeChat order must be continued in your order history; its channel cannot be changed.") : order ? (zh ? "将继续已有待支付订单，无需重复下单。" : "Continue your pending order without creating another.") : (zh ? "续费从当前到期时间延长；已到期则从购买时间起算。" : "Renewals extend your current expiry, or start at purchase if expired.")}</p>
        </div>

        {mutation.error && <p role="alert" className="mt-3 rounded-lg bg-danger-soft p-3 text-xs leading-5 text-danger">{mutation.error.message === "UNFINISHED_ORDER_PLAN_CONFLICT" ? (zh ? "已有其他套餐的未完成订单，请先到近期订单处理。" : "Resolve the unfinished order for another plan in your order history first.") : (zh ? "暂时无法获取支付入口，请重试或在近期订单中继续。" : "Payment is unavailable. Retry or continue from your order history.")}</p>}
        {mutation.data && !legacyWechat && !mutation.data.payment.redirect_url && <p role="status" className="mt-3 text-xs leading-5 text-muted">{zh ? "订单已保存，请在近期订单中查看支付或权益到账状态。" : "Order saved. Check payment and entitlement status in your orders."}</p>}

        <div className="mt-5 flex items-center justify-between border-t border-line pt-4"><span className="text-xs text-muted">{zh ? "本次应付" : "Amount due"}</span><strong className="text-lg tabular-nums">{amount}</strong></div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" disabled={busy} onClick={onClose}>{zh ? "取消" : "Cancel"}</Button>
          {legacyWechat || (mutation.data && (mutation.data.payment_status !== "pending" || !mutation.data.payment.redirect_url)) ? <Button onClick={onViewOrders}>{zh ? "查看订单" : "View orders"}</Button> : mutation.data?.payment.redirect_url ? <a href={mutation.data.payment.redirect_url} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground outline-none hover:bg-primary-deep focus-visible:ring-2 focus-visible:ring-primary">{zh ? "继续前往支付宝" : "Continue to Alipay"}<ArrowUpRight className="size-4" aria-hidden="true" /></a> : <Button disabled={busy || paymentMode === "disabled"} onClick={() => mutation.mutate()}>{busy ? <><LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" />{zh ? "正在获取支付入口…" : "Preparing payment…"}</> : <>{paymentMode === "mock" ? (zh ? "创建测试订单" : "Create test order") : (zh ? "前往支付宝支付" : "Continue to Alipay")}<ArrowUpRight aria-hidden="true" /></>}</Button>}
        </div>
      </div>
    </div>
  </dialog>;
}
