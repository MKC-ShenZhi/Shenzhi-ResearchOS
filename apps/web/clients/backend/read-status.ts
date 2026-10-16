import { apiJson } from "./http";

const MAX_BATCH_SIZE = 100;
export const PAPER_READ_CHANNEL = "shenzhi-paper-read";

interface ReadStatusResponse {
  user_id: string;
  read_paper_ids: string[];
  reading_paper_ids: string[];
}

export type PaperReadStatus = "read" | "reading" | null;
type Pending = { resolve: (status: PaperReadStatus) => void; reject: (error: unknown) => void };
let pendingByUser = new Map<string, Map<string, Pending[]>>();
let scheduled = false;
let publishChannel: BroadcastChannel | undefined;

export const paperReadStatusQueryKey = (userId: string, paperId: string) =>
  ["paper-read-status", userId, paperId] as const;

async function requestBatch(userId: string, entries: [string, Pending[]][]) {
  const paperIds = entries.map(([paperId]) => paperId);
  try {
    const response = await apiJson<ReadStatusResponse>("/papers/read-status", {
      method: "POST",
      body: JSON.stringify({ paper_ids: paperIds }),
    });
    if (response.user_id !== userId) throw new Error("阅读状态所属账户已变化");
    const readIds = new Set(response.read_paper_ids);
    const readingIds = new Set(response.reading_paper_ids);
    for (const [paperId, waiters] of entries) {
      const status = readIds.has(paperId) ? "read" : readingIds.has(paperId) ? "reading" : null;
      for (const waiter of waiters) waiter.resolve(status);
    }
  } catch (error) {
    for (const [, waiters] of entries) {
      for (const waiter of waiters) waiter.reject(error);
    }
  }
}

function flushPending() {
  scheduled = false;
  const batches = pendingByUser;
  pendingByUser = new Map();
  for (const [userId, papers] of batches) {
    const entries = [...papers.entries()];
    for (let index = 0; index < entries.length; index += MAX_BATCH_SIZE) {
      void requestBatch(userId, entries.slice(index, index + MAX_BATCH_SIZE));
    }
  }
}

/** Collect card queries from the current render into bounded backend requests. */
export function fetchPaperReadStatus(userId: string, paperId: string): Promise<PaperReadStatus> {
  return new Promise((resolve, reject) => {
    const papers = pendingByUser.get(userId) ?? new Map<string, Pending[]>();
    const waiters = papers.get(paperId) ?? [];
    waiters.push({ resolve, reject });
    papers.set(paperId, waiters);
    pendingByUser.set(userId, papers);
    if (!scheduled) {
      scheduled = true;
      setTimeout(flushPending, 0);
    }
  });
}

export function publishPaperRead(userId: string, paperId: string, status: Exclude<PaperReadStatus, null>) {
  if (typeof BroadcastChannel === "undefined") return;
  publishChannel ??= new BroadcastChannel(PAPER_READ_CHANNEL);
  publishChannel.postMessage({ userId, paperId, status });
}
