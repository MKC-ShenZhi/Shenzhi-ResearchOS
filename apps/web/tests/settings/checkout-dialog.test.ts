import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";

type Element = { type: unknown; props: Record<string, unknown> };
const jsx = (type: unknown, props: Element["props"]) => ({ type, props });
function elements(node: unknown): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== "object" || !("props" in node)) return [];
  const element = node as Element;
  return [element, ...elements(element.props.children)];
}

function setup(pendingOrder?: Record<string, unknown>, busy = false, upgrade = false, quoteData?: Record<string, unknown>) {
  let options: { mutationFn: () => Promise<unknown>; onSuccess: (order: unknown) => void; onError: () => void };
  let effect: () => () => void;
  const calls: unknown[][] = [];
  let closeCount = 0;
  let updates = 0;
  let restored = 0;
  let modalOpened = 0;
  let modalClosed = 0;
  let quoteEnabled = false;
  class FocusTarget { isConnected = true; focus() { restored++; } }
  const document = { body: { style: { overflow: "auto" } }, activeElement: new FocusTarget() };
  const dialog = { showModal() { modalOpened++; }, close() { modalClosed++; } };
  const exports: Record<string, unknown> = {};
  const mutation = { isPending: busy, data: undefined, error: null, mutate() { calls.push(["mutate"]); }, reset() { calls.push(["reset"]); } };
  const deps: Record<string, unknown> = {
    react: { useEffect: (callback: typeof effect) => { effect = callback; }, useId: () => "checkout-title", useRef: () => ({ current: dialog }) },
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "@tanstack/react-query": {
      useMutation: (input: typeof options) => { options = input; return mutation; },
      useQuery: (input: { enabled: boolean }) => {
        quoteEnabled = input.enabled;
        return { data: quoteData, isFetching: false, isPending: !quoteData, error: null,
          refetch: () => { calls.push(["quote-refetch"]); } };
      },
    },
    "lucide-react": {},
    "./billing-state": { billingMessage: (code: string) => code },
    "@/clients/backend/billing": { billing: {
      create: async (...args: unknown[]) => { calls.push(["create", ...args]); return {}; },
      action: async (...args: unknown[]) => { calls.push(["action", ...args]); return {}; },
    } },
    "@/components/ui/button": { Button: "button" },
  };
  runInNewContext(ts.transpileModule(readFileSync("features/settings/components/subscription/checkout-dialog.tsx", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports, document, HTMLElement: FocusTarget, window: { location: { assign: (url: string) => calls.push(["redirect", url]) } },
    require: (id: string) => { assert.ok(id in deps, `Unexpected import: ${id}`); return deps[id]; },
  });
  const render = exports.CheckoutDialog as (props: unknown) => unknown;
  const tree = elements(render({ plan: { plan_id: upgrade ? "research" : "pro", name: upgrade ? "Research 研究版" : "Pro 专业版", amount: upgrade ? 4990 : 1990, currency: "CNY", daily_tokens: 1000000, duration_months: 1, test_price: true },
    pendingOrder, upgrade, paymentMode: "live", userId: "user-a", locale: "zh-CN", onClose: () => closeCount++, onUpdated: () => updates++, onViewOrders: () => calls.push(["view-orders"]),
  }));
  return { tree, calls, mutation, document, dialog, quoteEnabled, options: () => options!, effect: () => effect!(), counts: () => ({ closeCount, updates, restored, modalOpened, modalClosed }) };
}

test("opening checkout is read-only; confirmation creates only an Alipay order", async () => {
  const h = setup();
  assert.deepEqual(h.calls, []);
  assert.equal(h.quoteEnabled, false);
  const radios = h.tree.filter((node) => node.type === "input");
  assert.equal(radios[0].props.checked, true);
  assert.equal(radios[1].props.disabled, true);
  await h.options().mutationFn();
  assert.deepEqual(h.calls, [["create", "user-a", "pro", "alipay"]]);
});

test("upgrade sends the reviewed backend quote and can refresh an expired quote", async () => {
  const quote = { amount: 1500, currency: "CNY", quoted_at: new Date().toISOString(),
    quote_token: "backend-quote", quote_expires_at: new Date(Date.now() + 300000).toISOString() };
  const h = setup(undefined, false, true, quote);
  assert.equal(h.quoteEnabled, true);
  await h.options().mutationFn();
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [["create", "user-a", "research", "alipay", { quoted_at: quote.quoted_at, quote_token: quote.quote_token }]]);
  const expired = setup(undefined, false, true, { ...quote, quote_expires_at: "2020-01-01T00:00:00Z" });
  assert.throws(() => expired.options().mutationFn(), /QUOTE_EXPIRED/);
  assert.deepEqual(expired.calls, []);
  const refresh = expired.tree.find((node) => node.type === "button" && node.props.children === "重新获取报价")!;
  (refresh.props.onClick as () => void)();
  assert.deepEqual(expired.calls, [["reset"], ["quote-refetch"]]);
});

test("pending orders reuse their ID; only pending live Alipay results navigate", async () => {
  const h = setup({ order_id: "existing", channel: "alipay", amount: 2, currency: "CNY" });
  await h.options().mutationFn();
  assert.deepEqual(h.calls, [["action", "user-a", "existing", "payment"]]);
  const order = { mode: "live", channel: "alipay", payment_status: "pending", payment: { redirect_url: "https://example.com/payment" } };
  h.options().onSuccess({ ...order, mode: "mock" });
  h.options().onSuccess({ ...order, payment_status: "paid" });
  h.options().onSuccess({ ...order, channel: "wechat" });
  assert.equal(h.calls.length, 1);
  h.options().onSuccess(order);
  assert.deepEqual(h.calls[1], ["redirect", "https://example.com/payment"]);
  assert.equal(h.counts().updates, 4);
});

test("legacy WeChat orders show their actual channel and recover from order history", () => {
  const h = setup({ order_id: "legacy", channel: "wechat", amount: 2, currency: "CNY" });
  const radios = h.tree.filter((node) => node.type === "input");
  assert.equal(radios[0].props.checked, false);
  assert.equal(radios[1].props.checked, true);
  const view = h.tree.find((node) => node.type === "button" && node.props.children === "查看订单")!;
  (view.props.onClick as () => void)();
  assert.deepEqual(h.calls, [["view-orders"]]);
});

test("native modal locks scroll and restores focus after Escape cancellation", () => {
  const h = setup();
  const cleanup = h.effect();
  assert.equal(h.counts().modalOpened, 1);
  assert.equal(h.document.body.style.overflow, "hidden");
  const root = h.tree[0];
  let prevented = false;
  (root.props.onCancel as (event: unknown) => void)({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(h.counts().closeCount, 1);
  cleanup();
  assert.equal(h.document.body.style.overflow, "auto");
  assert.equal(h.counts().modalClosed, 1);
  assert.equal(h.counts().restored, 1);
});

test("submitting disables repeat confirmation and blocks Escape or backdrop dismissal", () => {
  const h = setup(undefined, true);
  const root = h.tree[0];
  (root.props.onCancel as (event: unknown) => void)({ preventDefault() {} });
  (root.props.onClick as (event: unknown) => void)({ target: h.dialog, currentTarget: h.dialog });
  assert.equal(h.counts().closeCount, 0);
  assert.ok(h.tree.filter((node) => node.type === "button").every((node) => node.props.disabled));
});

test("Tab and Shift+Tab wrap within the modal controls", () => {
  const h = setup();
  let firstFocused = 0;
  let lastFocused = 0;
  const first = { focus() { firstFocused++; } };
  const last = { focus() { lastFocused++; } };
  const keydown = h.tree[0].props.onKeyDown as (event: unknown) => void;
  let prevented = 0;
  const event = { key: "Tab", shiftKey: false, preventDefault() { prevented++; }, currentTarget: { querySelectorAll: () => [first, last] } };
  Object.assign(h.document, { activeElement: last });
  keydown(event);
  Object.assign(h.document, { activeElement: first });
  keydown({ ...event, shiftKey: true });
  assert.equal(firstFocused, 1);
  assert.equal(lastFocused, 1);
  assert.equal(prevented, 2);
});
