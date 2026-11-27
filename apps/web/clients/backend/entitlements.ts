import { ApiError, agentApiPath, expectedUserHeaders } from "./http";

export type UsageWindow = {
  rule_id: string; metric: string; unit: string;
  limit_units: number; held_units: number; used_units: number; remaining_units: number;
  window_ref: { window_id: string; window_type: "fixed" | "natural" | "rolling"; end: string | null; timezone: string | null };
};

export type EntitlementUsage = {
  schema_version: number; plan_id: string; token_scope: string; windows: UsageWindow[];
};

/** Agent control's public read endpoint returns the v2 wire payload, not an API envelope. */
export async function fetchEntitlementUsage(userId: string): Promise<EntitlementUsage> {
  const response = await fetch(agentApiPath("/agent/entitlements"), {
    headers: expectedUserHeaders(userId), cache: "no-store", signal: AbortSignal.timeout(30000),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(payload.error?.reason_code ?? payload.code ?? "USAGE_UNAVAILABLE",
      payload.error?.message ?? payload.message ?? "USAGE_UNAVAILABLE", response.status);
  }
  return payload as EntitlementUsage;
}
