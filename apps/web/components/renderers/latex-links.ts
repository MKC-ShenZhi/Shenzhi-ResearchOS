type LatexSegment =
  | { type: "text"; text: string }
  | { type: "link"; text: string; href: string };

// 全角标点不会出现在论文网址中，视为网址边界。
const URL_PATTERN = /https?:\/\/[^\s<>"'`{}|\\^，。；：！？、（）【】「」《》“”‘’]+/gi;
const URL_COMMAND_PREFIX = "\\url{";
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

export function splitLatexLinks(text: string): LatexSegment[] {
  const segments: LatexSegment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const raw = match[0];
    const urlStart = match.index ?? 0;
    const urlEnd = urlStart + raw.length;
    const commandStart = urlStart - URL_COMMAND_PREFIX.length;
    // The braces give an explicit URL boundary, including any final punctuation.
    const wrapped = commandStart >= cursor
      && text[commandStart - 1] !== "\\"
      && text.startsWith(URL_COMMAND_PREFIX, commandStart)
      && text[urlEnd] === "}";
    const url = wrapped ? raw : trimUrl(raw);
    if (url.length <= "https://".length) continue;

    let href: string;
    try {
      href = new URL(url).href;
    } catch {
      continue;
    }

    const start = wrapped ? commandStart : urlStart;
    if (start > cursor) segments.push({ type: "text", text: text.slice(cursor, start) });
    segments.push({ type: "link", text: url, href });
    cursor = wrapped ? urlEnd + 1 : urlStart + url.length;
  }
  if (cursor < text.length) segments.push({ type: "text", text: text.slice(cursor) });
  return segments;
}

/** LaTeX 渲染前用占位符替换网址：网址中的 `_`、`%`、`~` 会破坏解析，连字也会改写网址文本。 */
export const LATEX_LINK_PLACEHOLDER = /SZLINK(\d+)TOKEN/;

export function replaceLatexLinks(text: string): {
  source: string;
  links: Extract<LatexSegment, { type: "link" }>[];
} {
  const links: Extract<LatexSegment, { type: "link" }>[] = [];
  const source = splitLatexLinks(text)
    .map((segment) => {
      if (segment.type === "text") return segment.text;
      links.push(segment);
      return `SZLINK${links.length - 1}TOKEN`;
    })
    .join("");
  return { source, links };
}
