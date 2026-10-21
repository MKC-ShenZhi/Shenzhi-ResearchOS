import { BffKnowledgeClient } from "../../../clients/knowledge/bff";
import { KnowledgeClientError } from "../../../clients/knowledge/client";
import type { ScholarProvider } from "./types";

export function createRealScholarProvider(client = new BffKnowledgeClient()): ScholarProvider {
  return {
    cacheKey: "product-scholars-v2-bff",
    isDemo: false,
    supportsBrowse: false,
    search(query, signal, page = { limit: 20, offset: 0 }) {
      return client.searchScholarProfiles(query.trim(), page.limit, page.offset, signal);
    },
    async detail(id, signal) {
      try {
        return { scholar: await client.scholarProfile(id, signal), papers: [] };
      } catch (error) {
        if (error instanceof KnowledgeClientError && error.code === "NOT_FOUND") return null;
        throw error;
      }
    },
    papers(id, limit, offset, signal) {
      return client.scholarPapers(id, limit, offset, signal);
    },
  };
}
