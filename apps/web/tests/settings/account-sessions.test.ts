import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import * as authErrors from "../../components/auth/auth-errors";
import { accountMessages } from "../../features/settings/i18n";

type Item = { id: string; token: string; createdAt: string };
type Result<T> = { data?: T; error?: { code: string; status: number } };
type Props = { currentUserId: string; currentToken: string; locale: "en" | "zh-CN" };
type Element = { type: string; props: { children?: unknown; disabled?: boolean; onClick?: () => void; role?: string } };
const stale = { error: { code: "SESSION_NOT_FRESH", status: 403 } };
const item = (token: string): Item => ({ id: token, token, createdAt: "2026-01-01T00:00:00Z" });
const flush = () => new Promise<void>((resolve) => setImmediate(resolve));

// Follow the existing VM-based component tests without adding a DOM dependency.
// Drive hook state/effect cleanup explicitly to exercise async event handlers.
function panel() {
  const cells: unknown[] = [];
  const effects = new Map<number, { deps: unknown[]; cleanup?: () => void }>();
  let cursor = 0;
  let mounted = true;
  let lateUpdates = 0;
  let props: Props = { currentUserId: "user-a", currentToken: "old", locale: "en" };
  const logins: { notice: string; onSuccess: () => Promise<void> }[] = [];
  const calls = { list: 0, revoke: 0, session: 0 };
  const client = {
    listSessions: async (): Promise<Result<Item[]>> => {
      calls.list++;
      return { data: [item(props.currentToken), item("other")] };
    },
    revokeOtherSessions: async (): Promise<Result<unknown>> => {
      calls.revoke++;
      return { data: {} };
    },
    getSession: async (): Promise<Result<{ user: { id: string }; session: { token: string } }>> => {
      calls.session++;
      return { data: { user: { id: props.currentUserId }, session: { token: props.currentToken } } };
    },
  };
  const react = {
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = initial;
      return [cells[index], (value: unknown) => {
        if (!mounted) lateUpdates++;
        cells[index] = value;
      }];
    },
    useRef: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = { current: initial };
      return cells[index];
    },
    useEffect: (effect: () => () => void, deps: unknown[]) => {
      const index = cursor++;
      const previous = effects.get(index);
      if (previous && deps.every((dep, i) => dep === previous.deps[i])) return;
      previous?.cleanup?.();
      effects.set(index, { deps, cleanup: effect() });
    },
  };
  const jsx = (type: string, props: Element["props"]) => ({ type, props });
  const dependencies: Record<string, unknown> = {
    react,
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "@/components/auth/auth-client": { authClient: client },
    "@/components/auth/auth-provider": { useAuth: () => ({ openLogin: (options: typeof logins[number]) => logins.push(options) }) },
    "@/components/auth/auth-errors": authErrors,
    "@/components/ui/button": { Button: "button" },
    "../i18n": { accountMessages },
  };
  const exports: { AccountSessions?: (props: Props) => Element } = {};
  const source = ts.transpileModule(readFileSync("features/settings/components/account-sessions.tsx", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  runInNewContext(source, {
    exports,
    require: (id: string) => {
      assert.ok(id in dependencies, `Unexpected import: ${id}`);
      return dependencies[id];
    },
  });
  function elements(node: unknown): Element[] {
    if (Array.isArray(node)) return node.flatMap(elements);
    if (!node || typeof node !== "object" || !("props" in node)) return [];
    const element = node as Element;
    return [element, ...elements(element.props.children)];
  }
  function render(next: Partial<Props> = {}) {
    props = { ...props, ...next };
    cursor = 0;
    return elements(exports.AccountSessions!(props));
  }
  render();
  return {
    client, calls, logins, render,
    buttons: () => render().filter((element) => element.type === "button"),
    rows: () => render().filter((element) => element.type === "li"),
    errors: () => render().filter((element) => element.props.role === "alert"),
    lateUpdates: () => lateUpdates,
    unmount: () => {
      mounted = false;
      effects.forEach(({ cleanup }) => cleanup?.());
    },
  };
}

test("entering settings, rerendering and changing locale do not list sessions or open login", async () => {
  const p = panel();
  p.client.listSessions = async () => { p.calls.list++; return stale; };
  p.render({ locale: "zh-CN" });
  await flush();
  assert.equal(p.calls.list, 0);
  assert.equal(p.logins.length, 0);
  assert.equal(p.buttons()[0].props.children, accountMessages["zh-CN"].viewSessions);
  assert.equal(p.buttons()[1].props.disabled, true);
});

test("explicit view lists sessions, labels the current session and revokes others", async () => {
  const p = panel();
  p.buttons()[0].props.onClick!();
  await flush();
  assert.equal(p.calls.list, 1);
  assert.equal(p.rows().length, 2);
  assert.equal(Array.isArray(p.rows()[0].props.children), true);
  const children = p.rows()[0].props.children as Element[];
  assert.equal(children[0].props.children, accountMessages.en.sessionCurrent);
  assert.equal(p.buttons()[1].props.disabled, false);
  p.client.listSessions = async () => { p.calls.list++; return { data: [item("old")] }; };
  p.buttons()[1].props.onClick!();
  await flush();
  assert.equal(p.calls.revoke, 1);
  assert.equal(p.calls.list, 2);
  assert.equal(p.rows().length, 1);
  assert.equal(p.buttons()[1].props.disabled, true);
});

test("explicit stale view reauthenticates once and reloads across token rotation", async () => {
  const p = panel();
  p.client.listSessions = async () => { p.calls.list++; return stale; };
  p.buttons()[0].props.onClick!();
  await flush();
  assert.equal(p.logins.length, 1);
  assert.equal(p.logins[0].notice, accountMessages.en.sessionsReauthNotice);
  assert.equal(p.errors()[0].props.children, accountMessages.en.sessionsReauthRequired);
  p.render({ currentToken: "fresh" });
  p.client.listSessions = async () => { p.calls.list++; return { data: [item("fresh"), item("old")] }; };
  await p.logins[0].onSuccess();
  assert.equal(p.calls.session, 1);
  assert.equal(p.calls.list, 2);
  assert.equal(p.rows().length, 2);
  assert.equal(p.errors().length, 0);
  assert.equal(p.logins.length, 1);
  p.render({ currentToken: "another" });
  assert.equal(p.rows().length, 0, "cached sessions belong to the token used to fetch them");
  assert.equal(p.calls.list, 2, "token rotation alone does not fetch");
});

test("stale retry stays inline without a repeated login prompt", async () => {
  const p = panel();
  p.client.listSessions = async () => { p.calls.list++; return stale; };
  p.buttons()[0].props.onClick!();
  await flush();
  await p.logins[0].onSuccess();
  assert.equal(p.calls.list, 2);
  assert.equal(p.logins.length, 1);
  assert.equal(p.errors().length, 1);
});

test("revoke retains reauthentication and refreshes the session list after success", async () => {
  const p = panel();
  p.buttons()[0].props.onClick!();
  await flush();
  p.client.revokeOtherSessions = async () => { p.calls.revoke++; return stale; };
  p.buttons()[1].props.onClick!();
  await flush();
  assert.equal(p.calls.list, 1, "failed revoke does not fetch the list");
  assert.equal(p.logins.length, 1);
  p.render({ currentToken: "fresh" });
  p.client.revokeOtherSessions = async () => { p.calls.revoke++; return { data: {} }; };
  p.client.listSessions = async () => { p.calls.list++; return { data: [item("fresh")] }; };
  await p.logins[0].onSuccess();
  assert.equal(p.calls.revoke, 2);
  assert.equal(p.rows().length, 1);
  assert.equal(p.errors().length, 0);
});

test("a stale refresh after successful revocation retries only the list", async () => {
  const p = panel();
  p.buttons()[0].props.onClick!();
  await flush();
  p.client.listSessions = async () => { p.calls.list++; return stale; };
  p.buttons()[1].props.onClick!();
  await flush();
  assert.equal(p.calls.revoke, 1);
  p.render({ currentToken: "fresh" });
  p.client.listSessions = async () => { p.calls.list++; return { data: [item("fresh")] }; };
  await p.logins[0].onSuccess();
  assert.equal(p.calls.revoke, 1, "completed mutations are not replayed");
  assert.equal(p.rows().length, 1);
});

test("reauthentication as another user cannot query or revoke for the previous user", async () => {
  for (const action of ["load", "revoke"]) {
    const p = panel();
    if (action === "revoke") {
      p.buttons()[0].props.onClick!();
      await flush();
      p.client.revokeOtherSessions = async () => { p.calls.revoke++; return stale; };
    } else {
      p.client.listSessions = async () => { p.calls.list++; return stale; };
    }
    p.buttons()[action === "load" ? 0 : 1].props.onClick!();
    await flush();
    p.client.getSession = async () => ({ data: { user: { id: "user-b" }, session: { token: "b" } } });
    const before = { ...p.calls };
    await p.logins[0].onSuccess();
    assert.deepEqual(p.calls, before);
    assert.equal(p.rows().length, 0);
    assert.equal(p.errors()[0].props.children, accountMessages.en.reauthAccountMismatch);
  }
});

test("unmount cancels deferred login callbacks and ignores in-flight results and errors", async () => {
  const p = panel();
  p.client.listSessions = async () => stale;
  p.buttons()[0].props.onClick!();
  await flush();
  p.unmount();
  await p.logins[0].onSuccess();
  assert.equal(p.calls.session, 0);
  assert.equal(p.lateUpdates(), 0);

  for (const reject of [false, true]) {
    const pending = panel();
    let complete!: () => void;
    pending.client.listSessions = () => new Promise((resolve, fail) => {
      complete = () => reject ? fail(new Error("offline")) : resolve(stale);
    });
    pending.buttons()[0].props.onClick!();
    pending.unmount();
    complete();
    await flush();
    assert.equal(pending.logins.length, 0);
    assert.equal(pending.lateUpdates(), 0);
  }
});

test("switching accounts remounts an empty panel and invalidates the previous callback", async () => {
  const a = panel();
  a.client.listSessions = async () => stale;
  a.buttons()[0].props.onClick!();
  await flush();
  a.unmount();
  const b = panel();
  b.render({ currentUserId: "user-b", currentToken: "b" });
  await a.logins[0].onSuccess();
  assert.equal(a.calls.session, 0);
  assert.equal(a.lateUpdates(), 0);
  assert.equal(b.calls.list, 0);
  assert.equal(b.rows().length, 0);
  assert.equal(b.errors().length, 0);
});

test("duplicate clicks share one request; real authorization errors clear old data", async () => {
  const p = panel();
  p.buttons()[0].props.onClick!();
  await flush();
  let complete!: () => void;
  p.client.listSessions = () => {
    p.calls.list++;
    return new Promise((resolve) => { complete = () => resolve({ error: { code: "UNAUTHORIZED", status: 401 } }); });
  };
  const click = p.buttons()[0].props.onClick!;
  click();
  click();
  assert.equal(p.calls.list, 2);
  assert.equal(p.buttons()[0].props.disabled, true);
  complete();
  await flush();
  assert.equal(p.rows().length, 0);
  assert.equal(p.errors()[0].props.children, accountMessages.en.sessionsLoadFailed);
  assert.equal(p.logins.length, 0, "401 handling belongs to the global auth client/provider");
  assert.equal(p.buttons()[0].props.disabled, false);
});
