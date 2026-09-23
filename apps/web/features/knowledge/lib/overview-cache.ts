import type {
  KnowledgeClient,
  KnowledgeOverviewResponse,
  KnowledgePersonalOverviewResponse,
} from "@/clients/knowledge";

type CachedRequest<T> = {
  promise: Promise<T>;
  value?: T;
};

let publicOverview: CachedRequest<KnowledgeOverviewResponse> | null = null;
let personalOverview: CachedRequest<KnowledgePersonalOverviewResponse> | null = null;

function cacheRequest<T>(
  current: CachedRequest<T> | null,
  request: () => Promise<T>,
  onSettled: (next: CachedRequest<T> | null) => void,
) {
  if (current) return current;

  const next = {} as CachedRequest<T>;
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

export function loadKnowledgeOverview(client: KnowledgeClient) {
  const publicRequest = cacheRequest(publicOverview, () => client.overview(), (next) => {
    publicOverview = next;
  });
  const personalRequest = cacheRequest(personalOverview, () => client.personalOverview(), (next) => {
    personalOverview = next;
  });

  return Promise.allSettled([publicRequest.promise, personalRequest.promise]);
}

/** Call after a mutation that changes overview or personal-library data. */
export function invalidateKnowledgeOverviewCache() {
  publicOverview = null;
  personalOverview = null;
}
