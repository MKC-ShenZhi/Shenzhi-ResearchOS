import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import * as identityResponse from "../../clients/backend/identity-response";

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

const userSession = { user: { id: "user-a" }, session: {} };

function setup(initialSession: typeof userSession | null = userSession, beforeRefresh = Promise.resolve()) {
  type ErrorContext = { request: { url: string }; response: { status: number } };
  type View = { props: { value: { session: unknown }; children: [unknown, { props: { open: boolean; notice: string } }] } };
  const win = Object.assign(new EventTarget(), { setTimeout: () => 1, clearTimeout: () => {} });
  let onError!: (context: ErrorContext) => void;
  let refreshes = 0;
  let session = initialSession;
  let currentSession: typeof userSession | null = null;
  const refetch = async () => {
    refreshes++;
    await beforeRefresh;
    session = currentSession;
  };
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
    "@/clients/backend/identity-response": identityResponse,
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
  function backend(status: number, kind?: string) {
    const http = load("clients/backend/http.ts", { "./identity-response": identityResponse }, {
      window: win, CustomEvent, Headers, Response, FormData, AbortSignal,
      fetch: async (url: string) => url.endsWith("/identity/bootstrap")
        ? new Response(null, { status: 204 })
        : Response.json(status === 200 ? { code: 0, data: "ok" } : { code: 10001, message: "请登录" }, {
          status,
          headers: kind ? { [identityResponse.BACKEND_IDENTITY_HEADER]: kind } : {},
        }),
    }) as typeof import("../../clients/backend/http");
    const sse = load("clients/backend/sse.ts", { "./http": http }) as typeof import("../../clients/backend/sse");
    return { ...http, ...sse };
  }
  return {
    onError, render, identities, backend,
    get refreshes() { return refreshes; },
    setCurrentSession: (value: typeof userSession | null) => { currentSession = value; },
    cleanup: () => effects.forEach(({ cleanup }) => cleanup?.()),
  };
}

test("freshness errors preserve authenticated state; real 401 refreshes the provider to signed out", async (t) => {
  const state = setup();
  const { onError, render, identities } = state;
  t.after(state.cleanup);
  const authenticated = render();
  assert.ok(authenticated.props.value.session);
  assert.equal(authenticated.props.children[1].props.open, false);
  onError({ request: { url: "/api/auth/list-sessions" }, response: { status: 403 } });
  assert.equal(state.refreshes, 0);
  assert.ok(render().props.value.session);
  assert.equal(render().props.children[1].props.open, false);

  onError({ request: { url: "/api/auth/list-sessions" }, response: { status: 401 } });
  await Promise.resolve();
  assert.equal(state.refreshes, 1);
  assert.equal(render().props.value.session, null);
  const signedOut = render();
  assert.equal(signedOut.props.children[1].props.open, true);
  assert.equal(signedOut.props.children[1].props.notice, "登录状态已失效，请重新登录");
  assert.equal(identities.at(-1), null, "user-scoped collections clear with the authentication identity");
});

test("concurrent anonymous business 401s share one session refresh and open the global login", async (t) => {
  let completeRefresh!: () => void;
  const beforeRefresh = new Promise<void>((resolve) => { completeRefresh = resolve; });
  const state = setup(userSession, beforeRefresh);
  t.after(state.cleanup);
  state.render();
  const http = state.backend(401, "anonymous");
  const results = await Promise.allSettled([
    http.apiJson("/collections/folders"),
    http.apiJson("/history"),
    http.readSseStream("/api/v1/agent/run", { onEvent: () => {} }),
  ]);
  for (const result of results) {
    assert.ok(result.status === "rejected");
    assert.ok(http.isSessionMismatchError(result.reason));
  }
  assert.equal(state.refreshes, 1);
  completeRefresh();
  await beforeRefresh;
  assert.equal(state.render().props.value.session, null);
  assert.equal(state.render().props.children[1].props.notice, "登录状态已失效，请重新登录");
  assert.equal(state.identities.at(-1), null);
});

test("ordinary 401s stay local when identities agree or the BFF reports no identity", async (t) => {
  const signedIn = setup();
  const signedOut = setup(null);
  t.after(signedIn.cleanup);
  t.after(signedOut.cleanup);
  for (const [state, kind] of [[signedIn, "authenticated"], [signedOut, "anonymous"], [signedIn, undefined]] as const) {
    state.render();
    const http = state.backend(401, kind);
    await assert.rejects(http.apiJson("/collections/folders"), (error) =>
      error instanceof http.ApiError && error.status === 401 && !http.isSessionMismatchError(error));
    assert.equal(state.refreshes, 0);
    assert.equal(state.render().props.children[1].props.open, false);
  }
});

test("successful business responses also reconcile mismatches using the current Better Auth session", async (t) => {
  const signedIn = setup();
  const signedOut = setup(null);
  const revoked = setup();
  t.after(signedIn.cleanup);
  t.after(signedOut.cleanup);
  t.after(revoked.cleanup);
  signedIn.setCurrentSession(userSession);
  signedOut.setCurrentSession(userSession);
  for (const [state, kind] of [[signedIn, "anonymous"], [signedOut, "authenticated"]] as const) {
    state.render();
    assert.equal(await state.backend(200, kind).apiJson("/agent/config"), "ok");
    assert.equal(state.refreshes, 1);
    assert.equal(state.render().props.value.session, userSession);
    assert.equal(state.render().props.children[1].props.open, false);
  }

  revoked.render();
  assert.equal(await revoked.backend(200, "anonymous").apiJson("/agent/config"), "ok");
  assert.equal(revoked.refreshes, 1);
  assert.equal(revoked.render().props.value.session, null);
  assert.equal(revoked.render().props.children[1].props.open, true);
});
