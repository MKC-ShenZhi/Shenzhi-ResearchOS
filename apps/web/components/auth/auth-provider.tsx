"use client";

import * as React from "react";
import {
  AUTH_SESSION_INVALID_EVENT,
  authClient,
} from "@/components/auth/auth-client";
import { LoginModal } from "@/components/auth/login-modal";

const SESSION_INVALID_NOTICE = "登录状态已失效，请重新登录";
const MAX_TIMEOUT_MS = 2_147_483_647;

export type AuthSuccessCallback = () => void | Promise<void>;

export interface LoginRequestOptions {
  notice?: string | null;
  onSuccess?: AuthSuccessCallback;
}

type AuthSession = typeof authClient.$Infer.Session;
type SignOutResult = Awaited<ReturnType<typeof authClient.signOut>>;
type DeleteAccountOptions = Parameters<typeof authClient.deleteUser>[0];
type DeleteAccountResult = Awaited<ReturnType<typeof authClient.deleteUser>>;

interface AuthContextValue {
  session: AuthSession | null;
  isPending: boolean;
  refetchSession: () => Promise<void>;
  openLogin: (options?: LoginRequestOptions) => void;
  closeLogin: () => void;
  requireAuth: (options?: LoginRequestOptions) => boolean;
  signOut: () => Promise<SignOutResult>;
  deleteAccount: (
    options: DeleteAccountOptions,
  ) => Promise<DeleteAccountResult>;
  completeExternalAccountDeletion: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const {
    data: session,
    isPending,
    refetch: refetchSession,
  } = authClient.useSession();
  const [loginOpen, setLoginOpen] = React.useState(false);
  const [loginNotice, setLoginNotice] = React.useState<string | null>(null);
  const loginSuccessRef = React.useRef<AuthSuccessCallback | null>(null);
  const previousSessionRef = React.useRef<AuthSession | null>(null);
  const sessionInitializedRef = React.useRef(false);
  const expectedSessionEndRef = React.useRef(false);

  const closeLogin = React.useCallback(() => {
    loginSuccessRef.current = null;
    setLoginOpen(false);
    setLoginNotice(null);
  }, []);

  const openLogin = React.useCallback((options?: LoginRequestOptions) => {
    loginSuccessRef.current = options?.onSuccess ?? null;
    setLoginNotice(options?.notice ?? null);
    setLoginOpen(true);
  }, []);

  const runSuccessCallback = React.useCallback(
    async (callback: AuthSuccessCallback) => {
      try {
        await callback();
      } catch (error) {
        console.error("登录成功后的操作执行失败", error);
      }
    },
    [],
  );

  const handleLoginSuccess = React.useCallback(async () => {
    const callback = loginSuccessRef.current;
    loginSuccessRef.current = null;
    if (callback) await runSuccessCallback(callback);
  }, [runSuccessCallback]);

  const requireAuth = React.useCallback(
    (options?: LoginRequestOptions) => {
      if (!session) {
        openLogin({
          notice: options?.notice ?? "请先登录后继续",
          onSuccess: options?.onSuccess,
        });
        return false;
      }

      if (options?.onSuccess) {
        void runSuccessCallback(options.onSuccess);
      }
      return true;
    },
    [openLogin, runSuccessCallback, session],
  );

  const signOut = React.useCallback(async () => {
    expectedSessionEndRef.current = true;
    try {
      const result = await authClient.signOut();
      if (result.error) {
        expectedSessionEndRef.current = false;
      } else {
        await refetchSession();
      }
      return result;
    } catch (error) {
      expectedSessionEndRef.current = false;
      throw error;
    }
  }, [refetchSession]);

  const deleteAccount = React.useCallback(
    async (options: DeleteAccountOptions) => {
      expectedSessionEndRef.current = true;
      try {
        const result = await authClient.deleteUser(options);
        if (result.error) {
          expectedSessionEndRef.current = false;
        } else {
          await refetchSession();
        }
        return result;
      } catch (error) {
        expectedSessionEndRef.current = false;
        throw error;
      }
    },
    [refetchSession],
  );

  const completeExternalAccountDeletion = React.useCallback(async () => {
    expectedSessionEndRef.current = true;
    try {
      await refetchSession();
    } catch (error) {
      expectedSessionEndRef.current = false;
      throw error;
    }
  }, [refetchSession]);

  React.useEffect(() => {
    if (isPending) return;

    if (!sessionInitializedRef.current) {
      sessionInitializedRef.current = true;
      previousSessionRef.current = session;
      return;
    }

    if (previousSessionRef.current && !session) {
      const expectedSessionEnd = expectedSessionEndRef.current;
      expectedSessionEndRef.current = false;
      if (!expectedSessionEnd) {
        openLogin({
          notice: SESSION_INVALID_NOTICE,
          onSuccess: loginSuccessRef.current ?? undefined,
        });
      }
    }

    previousSessionRef.current = session;
  }, [isPending, openLogin, session]);

  React.useEffect(() => {
    const handleInvalidSession = () => {
      if (previousSessionRef.current) void refetchSession();
    };

    window.addEventListener(AUTH_SESSION_INVALID_EVENT, handleInvalidSession);
    return () =>
      window.removeEventListener(
        AUTH_SESSION_INVALID_EVENT,
        handleInvalidSession,
      );
  }, [refetchSession]);

  React.useEffect(() => {
    const expiresAt = session?.session.expiresAt;
    if (!expiresAt) return;

    const expiresAtMs = new Date(expiresAt).getTime();
    if (!Number.isFinite(expiresAtMs)) return;

    let timer: number;
    const scheduleRefresh = () => {
      const remaining = expiresAtMs - Date.now() + 100;
      timer = window.setTimeout(
        () => {
          if (remaining > MAX_TIMEOUT_MS) scheduleRefresh();
          else void refetchSession();
        },
        Math.min(Math.max(remaining, 0), MAX_TIMEOUT_MS),
      );
    };
    scheduleRefresh();

    return () => window.clearTimeout(timer);
  }, [refetchSession, session?.session.expiresAt]);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      session,
      isPending,
      refetchSession,
      openLogin,
      closeLogin,
      requireAuth,
      signOut,
      deleteAccount,
      completeExternalAccountDeletion,
    }),
    [
      closeLogin,
      completeExternalAccountDeletion,
      deleteAccount,
      isPending,
      openLogin,
      refetchSession,
      requireAuth,
      session,
      signOut,
    ],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <LoginModal
        open={loginOpen}
        notice={loginNotice}
        onClose={closeLogin}
        onSuccess={handleLoginSuccess}
      />
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth 必须在 AuthProvider 内使用");
  }
  return context;
}
