import { optionalEnv, parseBooleanEnv, parsePositiveIntegerEnv } from "./env";

export const ANONYMOUS_CHAT_TTL_SECONDS = parsePositiveIntegerEnv(
  "CHAT_ANONYMOUS_TTL_SECONDS",
  604800,
);

/**
 * FastAPI 业务后端根地址（仅服务端）。
 * 浏览器不得读取；兼容旧名 API_URL。不要使用 NEXT_PUBLIC_ 前缀。
 */
export const backendConfig = {
  allowInsecureLocal: parseBooleanEnv("BACKEND_ALLOW_INSECURE_LOCAL_BFF"),
  secret: optionalEnv("BACKEND_BFF_SECRET"),
  url: optionalEnv("BUSINESS_BACKEND_URL") ?? optionalEnv("API_URL"),
};

export function backendConnectionIsAllowed(config: typeof backendConfig): boolean {
  if (config.secret) return true;
  if (!config.allowInsecureLocal || !config.url) return false;
  try {
    const hostname = new URL(config.url).hostname.toLowerCase();
    return hostname === "localhost" || hostname.endsWith(".localhost") ||
      hostname === "::1" || hostname === "[::1]" || /^127(?:\.\d{1,3}){3}$/.test(hostname);
  } catch {
    return false;
  }
}
