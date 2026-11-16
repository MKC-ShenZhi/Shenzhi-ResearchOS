import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

function load(path: string, dependencies: Record<string, unknown>, globals = {}) {
  const exports: Record<string, unknown> = {};
  const source = ts.transpileModule(readFileSync(path, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  runInNewContext(source, {
    ...globals,
    exports,
    require: (id: string) => {
      assert.ok(id in dependencies, `Unexpected import: ${id}`);
      return dependencies[id];
    },
  });
  return exports;
}

test("freshness errors preserve authenticated state; real 401 refreshes the provider to signed out", async () => {
  type ErrorContext = { request: { url: string }; response: { status: number } };
  type View = { props: { value: { session: unknown }; children: [unknown, { props: { open: boolean; notice: string } }] } };
  const win = Object.assign(new EventTarget(), { setTimeout: () => 1, clearTimeout: () => {} });
  let onError!: (context: ErrorContext) => void;
  let refreshes = 0;
  let session: unknown = { user: { id: "user-a" }, session: {} };
  const refetch = async () => { refreshes++; session = null; };
  const auth = load("components/auth/auth-client.ts", {
    "better-auth/react": {
      createAuthClient: (options: { fetchOptions: { onError: typeof onError } }) => {
        onError = options.fetchOptions.onError;
        return { useSession: () => ({ data: session, isPending: false, refetch }) };
      },
    },
    "better-auth/client/plugins": { emailOTPClient: () => ({}) },
  }, { window: win, Event });

  const cells: unknown[] = [];
  const effects = new Map<number, { deps: unknown[]; cleanup?: () => void }>();
  let cursor = 0;
  let afterRender: (() => void)[] = [];
  const react = {
    createContext: () => ({ Provider: "provider" }),
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = initial;
      return [cells[index], (value: unknown) => { cells[index] = value; }];
    },
    useRef: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = { current: initial };
      return cells[index];
    },
    useCallback: (callback: unknown) => callback,
    useMemo: (factory: () => unknown) => factory(),
    useEffect: (effect: () => (() => void) | void, deps: unknown[]) => {
      const index = cursor++;
      const previous = effects.get(index);
      if (previous && deps.every((dep, i) => Object.is(dep, previous.deps[i]))) return;
      afterRender.push(() => {
        previous?.cleanup?.();
        effects.set(index, { deps, cleanup: effect() || undefined });
      });
    },
  };
  const jsx = (type: unknown, props: unknown) => ({ type, props });
  const identities: unknown[] = [];
  const syncIdentity = (id: unknown) => identities.push(id);
  const provider = load("components/auth/auth-provider.tsx", {
    react,
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "@/components/auth/auth-client": auth,
    "@/components/auth/login-modal": { LoginModal: "login-modal" },
    "@/stores/collections": { useCollections: (selector: (state: { syncIdentity: typeof syncIdentity }) => unknown) => selector({ syncIdentity }) },
  }, { window: win });
  const render = () => {
    cursor = 0;
    afterRender = [];
    const view = (provider.AuthProvider as (props: { children: string }) => View)({ children: "settings" });
    afterRender.forEach((effect) => effect());
    return view;
  };
  const authenticated = render();
  assert.ok(authenticated.props.value.session);
  assert.equal(authenticated.props.children[1].props.open, false);
  onError({ request: { url: "/api/auth/list-sessions" }, response: { status: 403 } });
  assert.equal(refreshes, 0);
  assert.ok(render().props.value.session);
  assert.equal(render().props.children[1].props.open, false);

  onError({ request: { url: "/api/auth/list-sessions" }, response: { status: 401 } });
  await Promise.resolve();
  assert.equal(refreshes, 1);
  assert.equal(render().props.value.session, null);
  const signedOut = render();
  assert.equal(signedOut.props.children[1].props.open, true);
  assert.equal(signedOut.props.children[1].props.notice, "登录状态已失效，请重新登录");
  assert.equal(identities.at(-1), null, "user-scoped collections clear with the authentication identity");
  effects.forEach(({ cleanup }) => cleanup?.());
});
