import { getKnowledgeBaseConfig } from "../../../../config/knowledge";
import { isPaperImagePath } from "../../../../lib/paper-thumbnail";

export const runtime = "nodejs";

const CONTENT_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

function failure(status: number) {
  return new Response(null, { status, headers: { "Cache-Control": "no-store" } });
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  if (!isPaperImagePath(path)) return failure(404);

  let config: ReturnType<typeof getKnowledgeBaseConfig>;
  try { config = getKnowledgeBaseConfig(); }
  catch { return failure(503); }
  if (!config) return failure(503);

  const contentType = CONTENT_TYPES[path[path.length - 1].split(".").pop()!.toLowerCase()];
  const headers = new Headers({ Accept: contentType });
  // No cookies, credentials, arbitrary URLs, query strings or client headers.
  for (const name of ["If-None-Match", "If-Modified-Since"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const timeout = AbortSignal.timeout(config.timeoutMs);
  try {
    const upstream = await fetch(new URL(`images/${path.join("/")}`, config.baseUrl), {
      headers,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.any([request.signal, timeout]),
    });
    const responseHeaders = new Headers({
      "Cache-Control": upstream.headers.get("Cache-Control") ?? "public, max-age=3600, must-revalidate",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of ["ETag", "Last-Modified"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (upstream.status === 304 && (headers.has("If-None-Match") || headers.has("If-Modified-Since"))) {
      return new Response(null, { status: 304, headers: responseHeaders });
    }

    const actualType = upstream.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase();
    if (upstream.status !== 200 || actualType !== contentType) {
      await upstream.body?.cancel();
      return failure([404, 410].includes(upstream.status) ? 404 : 502);
    }
    // Buffer before responding so timeout/body-read errors also become safe errors.
    const image = await upstream.arrayBuffer();
    responseHeaders.set("Content-Type", contentType);
    return new Response(image, { headers: responseHeaders });
  } catch (error) {
    return failure(timeout.aborted || (error instanceof Error && error.name === "TimeoutError") ? 504 : 502);
  }
}
