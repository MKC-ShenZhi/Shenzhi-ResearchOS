import { optionalEnv } from "./env";

/** Runtime server config shared in name/value with the Knowledge integration. */
export function getKnowledgeBaseConfig(): { baseUrl: URL; timeoutMs: number } | null {
  const configured = optionalEnv("KNOWLEDGE_BASE_API_URL");
  if (!configured) return null;

  const baseUrl = new URL(configured);
  if (!["http:", "https:"].includes(baseUrl.protocol) || baseUrl.username ||
      baseUrl.password || baseUrl.search || baseUrl.hash) {
    throw new Error("Invalid KNOWLEDGE_BASE_API_URL");
  }
  baseUrl.pathname = `${baseUrl.pathname.replace(/\/+$/, "")}/`;

  const seconds = Number(optionalEnv("KNOWLEDGE_BASE_TIMEOUT_SEC"));
  const milliseconds = Math.ceil(seconds * 1000);
  const timeoutMs = Number.isFinite(milliseconds) && milliseconds > 0 && milliseconds <= 2 ** 31 - 1
    ? milliseconds : 30_000;
  return { baseUrl, timeoutMs };
}
