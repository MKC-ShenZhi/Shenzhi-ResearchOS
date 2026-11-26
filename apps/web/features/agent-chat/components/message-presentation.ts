import { isMarkdownBlock, type AgentMessage, type Reference } from "../../../clients/backend/agent-message";
import { paperHref } from "../../../lib/navigation/paper";
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

/** Navigation is a Web concern; keep the original source URL in the protocol. */
export function referenceLink(reference: Reference): { href: string; external: boolean } | null {
  if (reference.type === "paper" && reference.entity_id?.trim()) {
    return { href: paperHref(reference.entity_id), external: false };
  }
  const href = safeReferenceUrl(reference.url) ?? doiUrl(reference.doi);
  return href ? { href, external: true } : null;
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

/** Read citation positions without counting literal code/math/link examples. */
export function citedReferenceIds(blocks: AgentMessage["blocks"]): string[] {
  const ids = new Set<string>();
  for (const block of blocks) {
    if (!isMarkdownBlock(block)) continue;
    let fence: string | null = null;
    let inList = false;
    const lines: string[] = [];
    for (const line of block.content.split("\n")) {
      const match = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
      if (match) {
        if (!fence) fence = match[1];
        else if (match[1][0] === fence[0] && match[1].length >= fence.length && !match[2].trim()) fence = null;
        continue;
      }
      if (/^ {0,3}(?:[-+*]|\d+[.)])\s/.test(line)) inList = true;
      else if (/^\S/.test(line)) inList = false;
      if (!fence && (inList || !/^(?: {4}|\t)/.test(line))) lines.push(line);
    }
    const text = lines.join("\n")
      .replace(/(`+)[\s\S]*?\1/g, "")
      .replace(/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]*\$/g, "")
      .replace(/!?\[(?:[^\[\]]|\[\[cite:[^\]]*\]\])*\]\([^)]*\)/g, "");
    for (const match of text.matchAll(/\[\[cite:([^\[\]\r\n]+)\]\]/g)) ids.add(match[1]);
  }
  return [...ids];
}

export function citationTargets(references: readonly Reference[], prefix: string,
  ids: readonly string[] = references.map((reference) => reference.id), allowPending = false): CitationTarget[] {
  const sources = new Map(references.map((reference) => [reference.id, reference]));
  return ids.flatMap((id, index) => {
    const source = sources.get(id);
    if (!source && !allowPending) return [];
    return [{ id, number: index + 1, href: `#${referenceAnchor(prefix, index + 1)}`,
      title: source?.title ?? "正在整理参考来源", pending: !source }];
  });
}
