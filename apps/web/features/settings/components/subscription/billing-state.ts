import type { BillingPlan, Subscription } from "@/clients/backend/billing";

export function purchaseBlock(subscription: Subscription, plan: BillingPlan): string | null {
  if (plan.plan_id === "basic") return "BASIC_FREE_FOREVER";
  if (subscription.transition_pending_reason) return subscription.transition_pending_reason;
  if (subscription.status === "disabled") return "ENTITLEMENT_DISABLED";
  if (["pro", "research"].includes(subscription.plan_id ?? "") && !subscription.expires_at)
    return "LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN";
  if (subscription.status === "active" && subscription.plan_id === "research" && plan.plan_id !== "research")
    return "PLAN_CHANGE_NOT_SUPPORTED";
  return !plan.purchasable ? "PLAN_NOT_PUBLISHED" : null;
}

export function billingMessage(code: string, zh: boolean): string {
  const messages: Record<string, [string, string]> = {
    BASIC_FREE_FOREVER: ["Basic 永久免费，无需购买。", "Basic is free forever. No purchase needed."],
    LEGACY_PERMANENT_ENTITLEMENT_REQUIRES_ADMIN: ["保留现有长期高级权益；如需购买，请联系管理员设置期限。", "Your permanent paid entitlement is preserved. Contact an administrator to set its expiry before purchasing."],
    ACTIVE_GRANTS_REQUIRE_DRAIN: ["请等待当前 Agent 任务及用量结算结束后重试。", "Wait for current Agent tasks and usage settlement, then retry."],
    BASIC_POLICY_UNAVAILABLE: ["Basic 策略暂不可用，等待管理员恢复后重试。", "Basic policy is unavailable. Wait for an administrator to restore it."],
    PLAN_CHANGE_NOT_SUPPORTED: ["Research 有效期内不支持主动降级。", "Active Research subscriptions cannot be downgraded."],
    QUOTE_REQUIRED: ["请先获取升级报价。", "Get an upgrade quote first."],
    QUOTE_EXPIRED: ["升级报价已过期，请重新获取报价。", "Upgrade quote expired. Get a new quote."],
    QUOTE_CHANGED: ["报价条件已变化，请重新获取报价。", "Quote conditions changed. Get a new quote."],
    QUOTE_INVALID: ["升级报价无效，请重新获取报价。", "Invalid quote. Get a new quote."],
    QUOTE_SNAPSHOT_INVALID: ["历史升级订单缺少有效快照，请联系管理员处理。", "This legacy upgrade order lacks a valid snapshot. Contact an administrator."],
    UPGRADE_NOT_AVAILABLE: ["原 Pro 权益已到期或发生变化；已支付订单请联系管理员处理。", "The original Pro term expired or changed. Contact an administrator about paid orders."],
    ENTITLEMENT_CHANGED: ["当前权益已变化，请刷新订阅并重试。", "Your entitlement changed. Refresh your subscription and retry."],
    PAID_ORDER_REQUIRES_FULFILLMENT: ["已有已支付订单等待权益到账，请在近期订单查询或重试履约，勿重复付款。", "A paid order awaits fulfillment. Check or retry it in recent orders before purchasing again."],
    UNFINISHED_ORDER_PLAN_CONFLICT: ["已有其他套餐未完成订单，请先在近期订单处理。", "Resolve the unfinished order for another plan in recent orders first."],
    ENTITLEMENT_DISABLED: ["当前权益已停用，请联系管理员。", "Your entitlement is disabled. Contact an administrator."],
    PLAN_NOT_PUBLISHED: ["套餐暂未开放购买。", "This plan is not available for purchase."],
  };
  return messages[code]?.[zh ? 0 : 1] ?? code;
}
