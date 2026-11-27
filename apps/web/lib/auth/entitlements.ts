import { backendConfig, backendConnectionIsAllowed } from "@/config/backend";

/** Best-effort registration notification; Backend initializes published Basic idempotently. */
export async function initializeUserEntitlement(userId: string): Promise<void> {
  if (!backendConfig.url || !backendConnectionIsAllowed(backendConfig)) {
    throw new Error("Entitlement backend unavailable");
  }
  const response = await fetch(`${backendConfig.url.replace(/\/$/, "")}/api/v1/identity/entitlements/initialize`, {
    method: "POST",
    headers: {
      "X-ShenZhi-User-Id": userId,
      ...(backendConfig.secret ? { "X-ShenZhi-Bff-Secret": backendConfig.secret } : {}),
    },
    signal: AbortSignal.timeout(5000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Entitlement initialization unconfirmed");
  const result = await response.json();
  if (result.data?.initialized === 0) {
    console.info("auth.entitlement_initialization_no_change");
  }
}
