import { z } from "zod";
import { parseScholarContract, scholarProfileSchema } from "@/clients/knowledge/scholar-profiles";
import type { ScholarProvider } from "./types";

let catalog: Promise<z.infer<typeof scholarProfileSchema>[]> | undefined;

function loadCatalog() {
  catalog ??= fetch("/images/scholar-preview/profiles.json")
    .then(async (response) => {
      if (!response.ok) throw new Error("Scholar preview data is unavailable.");
      return parseScholarContract(z.array(scholarProfileSchema), await response.json());
    })
    .catch((error) => {
      catalog = undefined;
      throw error;
    });
  return catalog;
}

const normalize = (value: string) => value.normalize("NFKC").trim().toLowerCase();

export const previewScholarProvider: ScholarProvider = {
  cacheKey: "local-scholar-preview",
  isDemo: false,
  isPreview: true,
  supportsBrowse: true,
  async search(query, signal, { limit, offset } = { limit: 20, offset: 0 }) {
    const profiles = await loadCatalog();
    signal?.throwIfAborted();
    const term = normalize(query);
    const exact = [];
    const partial = [];
    for (const profile of profiles) {
      const names = [profile.name_en ?? "", ...(profile.aliases ?? [])].map(normalize);
      if (term && names.includes(term)) exact.push(profile);
      else if (names.some((name) => name.includes(term)) ||
        profile.affiliations?.some(({ institution }) => normalize(institution ?? "").includes(term))) {
        partial.push(profile);
      }
    }
    const matches = [...exact, ...partial];
    return { items: matches.slice(offset, offset + limit), limit, offset, total: matches.length, has_more: offset + limit < matches.length };
  },
  async detail(id, signal) {
    const profiles = await loadCatalog();
    signal?.throwIfAborted();
    const scholar = profiles.find((profile) => profile.scholar_id === id);
    return scholar ? { scholar, papers: [] } : null;
  },
  async papers(_id, limit, offset) {
    return { items: [], limit, offset, total: 0 };
  },
};
