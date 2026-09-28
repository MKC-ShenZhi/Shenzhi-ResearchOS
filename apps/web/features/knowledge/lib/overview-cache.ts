import type {
  KnowledgeClient,
  KnowledgeOverviewResponse,
  KnowledgePersonalOverviewResponse,
} from "@/clients/knowledge";

type CachedRequest<T> = {
  identityKey: string | null;
  promise: Promise<T>;
  value?: T;
};

let publicOverview: CachedRequest<KnowledgeOverviewResponse> | null = null;
let personalOverview: CachedRequest<KnowledgePersonalOverviewResponse> | null = null;

function cacheRequest<T>(
  current: CachedRequest<T> | null,
  identityKey: string | null,
  request: () => Promise<T>,
  onSettled: (next: CachedRequest<T> | null) => void,
) {
  if (current?.identityKey === identityKey) return current;

  const next = { identityKey } as CachedRequest<T>;
  next.promise = request()
    .then((value) => {
      next.value = value;
      return value;
    })
    .catch((error: unknown) => {
      // Failed requests must remain retryable. A transient upstream failure
      // should not make the overview cache permanently unusable.
      onSettled(null);
      throw error;
    });
  onSettled(next);
  return next;
}

export function loadKnowledgeOverview(client: KnowledgeClient, identityKey: string | null = null) {
  const previousPublic = publicOverview;
  let currentPublic: CachedRequest<KnowledgeOverviewResponse> | null = null;
  const publicRequest = cacheRequest(publicOverview, identityKey, () => client.overview(), (next) => {
    if (next === null) {
      if (publicOverview === currentPublic) publicOverview = null;
      return;
    }
    if (publicOverview === previousPublic || publicOverview === next) publicOverview = next;
  });
  const previousPersonal = personalOverview;
  let currentPersonal: CachedRequest<KnowledgePersonalOverviewResponse> | null = null;
  const personalRequest = cacheRequest(personalOverview, identityKey, () => client.personalOverview(), (next) => {
    if (next === null) {
      if (personalOverview === currentPersonal) personalOverview = null;
      return;
    }
    if (personalOverview === previousPersonal || personalOverview === next) personalOverview = next;
  });
  currentPublic = publicRequest;
  currentPersonal = personalRequest;

  return Promise.allSettled([publicRequest.promise, personalRequest.promise]);
}

export async function loadKnowledgeOverviewForGeneration(
  client: KnowledgeClient,
  identityKey: string | null,
  generation: number,
  currentGeneration: () => number,
) {
  const result = await loadKnowledgeOverview(client, identityKey);
  return generation === currentGeneration() ? result : null;
}

/** Call after a mutation that changes overview or personal-library data. */
export function invalidateKnowledgeOverviewCache() {
  publicOverview = null;
  personalOverview = null;
}
