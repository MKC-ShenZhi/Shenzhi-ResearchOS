"use client";

import {
  getKnowledgeClient,
  type KnowledgeClient,
  type KnowledgePaperHit,
} from "../../../clients/knowledge";
import type { FeedPaper } from "../../../types";

/**
 * TODO(MVP-RANDOM-DISCOVERY-FEED):
 * Temporary MVP fallback for the discovery feed.
 *
 * This is NOT the final personalized recommendation implementation.
 * Replace/remove this module when the real recommendation/discovery
 * service is available.
 */

export type DiscoveryFeedTab = "recommend" | "frontier" | "follow" | "research";

export const MVP_RANDOM_DISCOVERY_SEEDS = [
  "machine learning",
  "deep learning",
  "large language model",
  "computer vision",
  "natural language processing",
  "multimodal learning",
  "reinforcement learning",
  "graph neural network",
  "AI agent",
] as const;

const SEARCH_TOP_K = 20;
const FEED_SIZE = 8;
const VENUE_TONES: FeedPaper["venueTone"][] = ["violet", "amber", "green"];

interface MvpRandomDiscoveryFeedOptions {
  client?: Pick<KnowledgeClient, "search">;
  random?: () => number;
  currentYear?: number;
}

function randomIndex(length: number, random: () => number): number {
  return Math.floor(random() * length);
}

function shuffle<T>(items: readonly T[], random: () => number): T[] {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = randomIndex(index + 1, random);
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

function stableVenueTone(id: string): FeedPaper["venueTone"] {
  let hash = 0;
  for (const character of id) hash = (hash + character.charCodeAt(0)) % VENUE_TONES.length;
  return VENUE_TONES[hash];
}

function discoveryTags(hit: KnowledgePaperHit): string[] {
  const source = hit.keywords.length > 0 ? hit.keywords : hit.subjects;
  return [...new Set(source.map((tag) => tag.trim()).filter(Boolean))].slice(0, 3);
}

/** Maps only fields available on a Knowledge search hit; no metrics are invented. */
export function mapKnowledgePaperHitToFeedPaper(hit: KnowledgePaperHit): FeedPaper {
  const tags = discoveryTags(hit);

  return {
    id: hit.id,
    date: hit.year === null ? "年份未知" : String(hit.year),
    venue: hit.venue?.trim() || "来源未知",
    venueTone: stableVenueTone(hit.id),
    authors: hit.authors.length > 0 ? hit.authors.join(" · ") : "作者未知",
    title: hit.title,
    abstract: hit.abstract?.trim() || "暂无摘要",
    aiLink: "AI 深度解读",
    tags,
    thumb: tags[0] ?? "论文摘要",
  };
}

/** Executes exactly one broad Knowledge search and returns only real search hits. */
export async function fetchMvpRandomDiscoveryFeed(
  tab: DiscoveryFeedTab,
  options: MvpRandomDiscoveryFeedOptions = {},
): Promise<FeedPaper[]> {
  const random = options.random ?? Math.random;
  const client = options.client ?? getKnowledgeClient();
  const currentYear = options.currentYear ?? new Date().getFullYear();
  const seed = MVP_RANDOM_DISCOVERY_SEEDS[
    randomIndex(MVP_RANDOM_DISCOVERY_SEEDS.length, random)
  ];

  const response = await client.search({
    query: seed,
    topK: SEARCH_TOP_K,
    yearFrom: tab === "frontier" ? currentYear - 1 : null,
    yearTo: null,
    venue: [],
    author: [],
    keyword: [],
    subject: [],
  });

  return shuffle(response.results, random)
    .slice(0, FEED_SIZE)
    .map(mapKnowledgePaperHitToFeedPaper);
}
