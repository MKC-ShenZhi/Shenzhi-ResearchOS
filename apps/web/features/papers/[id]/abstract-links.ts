import { paperExternalUrl } from "../../../lib/navigation/paper";

/**
 * 摘要正文中的网址识别，仅用于展示层把纯文本网址渲染为可点击链接，
 * 不推断链接含义（代码仓库、项目主页等由后端字段承载）。
 */
export type AbstractSegment =
  | { type: "text"; text: string }
  | { type: "link"; text: string; href: string };

// 全角标点不会出现在论文网址中，视为网址边界。
const URL_PATTERN = /https?:\/\/[^\s<>"'`{}|\\^，。；：！？、（）【】「」《》“”‘’]+/gi;
const TRAILING_PUNCTUATION = new Set([".", ",", ";", ":", "!", "?", "'", "\""]);
const CLOSING_BRACKETS: Record<string, string> = { ")": "(", "]": "[", "}": "{" };

function count(text: string, char: string) {
  return text.split(char).length - 1;
}

/** 去掉句末标点；括号只有在网址内未配对时才视为外部标点。 */
function trimUrl(raw: string): string {
  let url = raw;
  while (url) {
    const last = url[url.length - 1];
    const opening = CLOSING_BRACKETS[last];
    if (TRAILING_PUNCTUATION.has(last) || (opening && count(url, opening) < count(url, last))) {
      url = url.slice(0, -1);
      continue;
    }
    break;
  }
  return url;
}

export function splitAbstractLinks(text: string): AbstractSegment[] {
  const segments: AbstractSegment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const url = trimUrl(match[0]);
    const href = paperExternalUrl(url);
    const start = match.index ?? 0;
    if (!href || url.length <= "https://".length) continue;
    if (start > cursor) segments.push({ type: "text", text: text.slice(cursor, start) });
    segments.push({ type: "link", text: url, href });
    cursor = start + url.length;
  }
  if (cursor < text.length) segments.push({ type: "text", text: text.slice(cursor) });
  return segments;
}

/** LaTeX 渲染前用占位符替换网址：网址中的 `_`、`%`、`~` 会破坏解析，连字也会改写网址文本。 */
export const ABSTRACT_LINK_PLACEHOLDER = /SZLINK(\d+)TOKEN/;

export function replaceAbstractLinks(text: string): {
  source: string;
  links: Extract<AbstractSegment, { type: "link" }>[];
} {
  const links: Extract<AbstractSegment, { type: "link" }>[] = [];
  const source = splitAbstractLinks(text)
    .map((segment) => {
      if (segment.type === "text") return segment.text;
      links.push(segment);
      return `SZLINK${links.length - 1}TOKEN`;
    })
    .join("");
  return { source, links };
}
