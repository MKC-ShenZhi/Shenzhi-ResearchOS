import { api } from '../../api';

export type Target = { kind: 'provider' | 'model' | 'tool' | 'skill'; target_id: string };
export type HealthSummary = Target & {
  state: string; reason: string; audit_id: string | null;
  check: { profile: string; observed_at: string; expires_at: string; coverage?: string } | null;
};

export function healthSummaries(targets: Target[], signal: AbortSignal) {
  return api<{ items: HealthSummary[]; truncated: boolean }>('/agent/checks/summary', {
    method: 'POST', body: JSON.stringify({ targets }), signal,
  });
}
