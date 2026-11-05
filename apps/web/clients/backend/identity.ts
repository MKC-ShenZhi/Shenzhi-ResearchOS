type AuthSession = {
  user?: {
    id?: string | null;
    email?: string | null;
  } | null;
} | null;

export type SessionResolver = (headers: Headers) => Promise<AuthSession>;
export type BackendIdentity =
  | { kind: "authenticated"; userId: string }
  | { kind: "anonymous" };

async function getBetterAuthSession(headers: Headers): Promise<AuthSession> {
  // Keep this lazy so the transport helper does not initialize Better Auth at module load.
  const { auth } = await import("../../lib/auth/server");
  return auth.api.getSession({ headers });
}

/** A missing session is anonymous; resolver failures must remain authentication failures. */
export async function resolveBackendIdentity(
  requestHeaders: Headers,
  resolveSession: SessionResolver = getBetterAuthSession,
): Promise<BackendIdentity> {
  const session = await resolveSession(requestHeaders);
  const user = session?.user;
  if (!user?.id) return { kind: "anonymous" };
  return { kind: "authenticated", userId: user.id };
}

/** Writes the one trusted identity accepted by the FastAPI business boundary. */
export function attachIdentity(
  backendHeaders: Headers,
  identity: BackendIdentity,
  anonymousId: string,
) {
  backendHeaders.delete("x-shenzhi-user-id");
  backendHeaders.delete("x-shenzhi-user-email");
  backendHeaders.delete("x-shenzhi-anonymous-id");
  if (identity.kind === "authenticated") {
    backendHeaders.set("X-ShenZhi-User-Id", identity.userId);
    return;
  }
  backendHeaders.set("X-ShenZhi-Anonymous-Id", anonymousId);
}

/** Writes the dedicated dual identity used only by the anonymous claim. */
export function attachMigrationIdentity(
  backendHeaders: Headers,
  userId: string,
  anonymousId: string,
) {
  backendHeaders.delete("x-shenzhi-user-id");
  backendHeaders.delete("x-shenzhi-user-email");
  backendHeaders.delete("x-shenzhi-anonymous-id");
  backendHeaders.delete("x-shenzhi-source-anonymous-id");
  backendHeaders.set("X-ShenZhi-User-Id", userId);
  backendHeaders.set("X-ShenZhi-Source-Anonymous-Id", anonymousId);
}
