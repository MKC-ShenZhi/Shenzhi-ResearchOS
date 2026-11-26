import type { AgentMessage, Reference } from "../../../clients/backend/agent-message";
import type { CitationTarget } from "./citation-markers";

export const MESSAGE_STATUS: Record<AgentMessage["status"], string> = {
  running: "生成中…", done: "已完成", failed: "执行失败", stopped: "已停止",
  timeout: "执行超时", awaiting_input: "等待你的回答",
};
export const REFERENCE_TYPE: Record<Reference["type"], string> = {
  paper: "论文", author: "学者", institution: "机构", webpage: "网页", dataset: "数据集", funding: "基金",
};
const messageDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Shanghai",
});

export function messageTime(seconds: number): { dateTime: string; label: string } | null {
  const date = new Date(seconds * 1000);
  if (!Number.isFinite(date.getTime())) return null;
  return { dateTime: date.toISOString(), label: messageDateFormatter.format(date) };
}

export function safeReferenceUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function doiUrl(doi?: string | null): string | null {
  const value = doi?.trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, "");
  return value ? `https://doi.org/${encodeURIComponent(value)}` : null;
}

export function referenceDetails(reference: Reference): string {
  const authors = reference.authors?.filter((author) => author.trim());
  const authorText = authors?.length ? authors.length > 2 ? `${authors[0]} et al.` : authors.join("、") : "";
  const publication = [reference.venue, reference.year].filter((value) => value !== null && value !== undefined && value !== "").join(" ");
  const url = safeReferenceUrl(reference.url);
  const hostname = url ? new URL(url).hostname.replace(/^www\./, "") : "";
  return [authorText || hostname, publication].filter(Boolean).join(" · ");
}

export function referenceAnchor(prefix: string, number: number): string {
  return `${prefix}-reference-${number}`;
}

export function citationTargets(references: readonly Reference[], prefix: string): CitationTarget[] {
  return references.map((reference, index) => ({
    id: reference.id, number: index + 1, href: `#${referenceAnchor(prefix, index + 1)}`, title: reference.title,
  }));
}
