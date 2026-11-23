import { mockPaperDetail } from "../../../clients/knowledge/mock-data";
import { DEMO_SCHOLARS, DEMO_SCHOLAR_PAPER_IDS } from "./mock-data";
import type { ScholarProvider } from "./types";

/** 局部数据源，与 NEXT_PUBLIC_KNOWLEDGE_SOURCE 及真实 Scholar API 无关。 */
export function createMockScholarProvider(latencyMs = 180): ScholarProvider {
  async function wait(signal?: AbortSignal) {
    signal?.throwIfAborted();
    if (!latencyMs) return;
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        clearTimeout(timer);
        reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, latencyMs);
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }
  return {
    cacheKey: "mock-demo-v2",
    isDemo: true,
    supportsBrowse: true,
    async search(query, signal, page = { limit: 20, offset: 0 }) {
      await wait(signal);
      const term = query.trim().toLocaleLowerCase();
      const items = structuredClone(
        DEMO_SCHOLARS.filter((scholar) =>
          [scholar.name_zh, scholar.name_en].some((name) =>
            name?.toLocaleLowerCase().includes(term),
          ),
        ),
      );
      return { items: items.slice(page.offset, page.offset + page.limit),
        ...page, total: items.length, has_more: page.offset + page.limit < items.length };
    },
    async papers(id, limit, offset, signal) {
      await wait(signal);
      const papers = [...new Set(DEMO_SCHOLAR_PAPER_IDS[id] ?? [])].flatMap((paperId) => {
        const paper = mockPaperDetail(paperId);
        return paper ? [{ ...paper, platform_detail: false }] : [];
      });
      return structuredClone({ items: papers.slice(offset, offset + limit), total: papers.length, limit, offset });
    },
    async detail(id, signal) {
      await wait(signal);
      const scholar = DEMO_SCHOLARS.find((item) => item.scholar_id === id);
      if (!scholar) return null;
      const paperIds = [...new Set(DEMO_SCHOLAR_PAPER_IDS[id] ?? [])];
      return structuredClone({
        scholar,
        papers: paperIds.flatMap((paperId) => {
          const paper = mockPaperDetail(paperId);
          return paper ? [paper] : [];
        }),
      });
    },
  };
}
