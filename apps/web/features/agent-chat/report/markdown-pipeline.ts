/**
 * Markdown preprocessing for the report renderer.
 *
 * Pipeline (in this order, from ReportCard / ReportView):
 *   sanitize → splitTableBlocks → extractHeadings → injectChips
 *
 * `splitTableBlocks` MUST run before `injectChips`: the comparison table's
 * first column contains `[n] Title` labels that must stay intact for
 * ComparisonTable to render its own citation chip.
 *
 * All steps must respect fenced code blocks: a table, heading or citation
 * token inside ``` fences is model-generated example content, not markup to
 * transform. `fenceMask` computes which lines are inside a fence and the
 * three transforms skip those lines.
 *
 * Marker forms differ by context (both consumed by rehype-raw/parse5):
 *   - ComparisonTable — open tag and close tag on SEPARATE lines. A lone open
 *     tag line qualifies as a CommonMark HTML block (type 7) so the marker
 *     stays at BLOCK level, and the block fragment contains a balanced pair
 *     (a one-line open+close pair is NOT type 7 and lands inside a <p>; a
 *     self-closing tag is parsed by parse5 as an opening tag that swallows
 *     the content that follows).
 *   - `<Paper ns="1,3"></Paper>` — paired on one line because it is INLINE
 *     inside a paragraph; the pair keeps parse5 from swallowing the rest of
 *     the paragraph.
 */

/** A pipe-table parsed into header + rows (first column = paper label). */
export interface ParsedTable {
  header: string[];
  rows: string[][];
}

/** A ToC entry derived from `#` / `##` / `###` headings. */
export interface Heading {
  level: number;
  text: string;
  id: string;
}

const BLOCKED_TAGS = "script|iframe|object|embed|form|link|meta|style";

const ALLOWED_TAGS = new Set([
  "br",
  "b",
  "i",
  "em",
  "strong",
  "a",
  "ul",
  "ol",
  "li",
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "code",
  "pre",
  "span",
  "blockquote",
  "hr",
]);

/**
 * Strip XSS vectors from model-generated markdown before rendering:
 * dangerous tags (script/iframe/object/embed/form/link/meta/style), `on*=`
 * event handlers, `javascript:`/`vbscript:` URLs (both raw `<a href>` and
 * markdown `[text](url)` form). Unknown raw tags are dropped so the renderer
 * only sees the safe subset.
 */
export function sanitize(markdown: string): string {
  let out = markdown
    // Paired dangerous blocks, content included.
    .replace(new RegExp(`<(${BLOCKED_TAGS})\\b[^>]*>[\\s\\S]*?<\\/\\1\\s*>`, "gi"), "")
    // Leftover unpaired dangerous tags.
    .replace(new RegExp(`<\\/?(${BLOCKED_TAGS})\\b[^>]*>`, "gi"), "");
  // Clean handlers and dangerous URL schemes inside any remaining tag.
  out = out.replace(/<\s*\/?[a-zA-Z][^<>]*>/g, (tag) =>
    tag
      .replace(/\s+on\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
      .replace(/\b(href|src)\s*=\s*["']?(?:javascript|vbscript):[^"'>\s]*["']?/gi, ""),
  );
  // Drop raw tags outside the allowlist (model artifacts, XML-ish tokens).
  out = out.replace(/<\s*\/?\s*([a-zA-Z][a-zA-Z0-9-]*)\b[^<>]*>/g, (tag, name) =>
    ALLOWED_TAGS.has(String(name).toLowerCase()) ? tag : "",
  );
  // Neutralize markdown-style links with dangerous schemes: `[text](javascript:...)`.
  out = out.replace(/\[([^\]\n]*)\]\(\s*(?:javascript|vbscript):[^)]*\)/gi, "[$1]");
  return out;
}

/**
 * Sentinel emitted by the chart pass before the 图表来源清单 appendix table.
 * The region from this sentinel to the next blank line is kept verbatim:
 * not converted to a `<ComparisonTable>`, and not chipified.
 */
const APPENDIX_SENTINEL = "<!-- sources-table -->";

/**
 * Mark the 图表来源清单 appendix region inert. From the sentinel line through
 * the end of the contiguous table block (next blank line), every line is marked;
 * blank line closes the region. Aligned with `lines`.
 */
function appendixMask(lines: string[]): boolean[] {
  const mask = new Array(lines.length).fill(false);
  let inside = false;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!inside && t === APPENDIX_SENTINEL) {
      inside = true;
      mask[i] = true;
      continue;
    }
    if (inside) {
      if (t === "") {
        inside = false;
        continue;
      }
      mask[i] = true;
    }
  }
  return mask;
}

/**
 * Mark which lines are inside a fenced code block (``` or ~~~).
 * Returns a boolean array aligned with `lines`; boundary fence lines
 * themselves are not marked. A fence closes only on the same marker.
 */
function fenceMask(lines: string[]): boolean[] {
  const inside = new Array(lines.length).fill(false);
  let fence: string | null = null;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^\s*(```|~~~)/);
    if (m) {
      if (fence === null) {
        fence = m[1];
      } else if (m[1] === fence) {
        fence = null;
      }
      continue;
    }
    if (fence !== null) inside[i] = true;
  }
  return inside;
}

/** Split one markdown table line into cells on unescaped pipes. */
function splitCells(line: string): string[] {
  const cells: string[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  // A pipe is a real column separator unless it is escaped (`\|`). Odd runs
  // of backslashes escape the pipe; even runs are backslash-escapes that
  // leave the pipe as a separator (e.g. `\\|`).
  const re = /(?<!\\)(?:\\\\)*\|/g;
  while ((m = re.exec(line)) !== null) {
    cells.push(line.slice(last, m.index).trim());
    last = m.index + 1;
  }
  cells.push(line.slice(last).trim());
  return cells.map((c) => c.replace(/\\\|/g, "|").trim());
}

/** Parse raw pipe-table lines into a ParsedTable. */
export function parseMarkdownTable(lines: string[]): ParsedTable {
  const rows = lines
    .map((l) => l.replace(/^\s*\|/, "").replace(/\|\s*$/, ""))
    .map(splitCells);
  if (rows.length === 0) {
    return { header: [], rows: [] };
  }
  const isSep = (cells: string[]) => cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c.trim()));
  let header: string[] = rows[0];
  let body: string[][] = rows.slice(1);
  if (rows.length > 1 && isSep(rows[1])) {
    header = rows[0];
    body = rows.slice(2);
  }
  const width = Math.max(header.length, ...body.map((r) => r.length));
  const pad = (cells: string[]) => {
    const row = cells.slice(0, width);
    while (row.length < width) row.push("");
    return row;
  };
  return {
    header: pad(header),
    rows: body.filter((r) => r.length > 0).map(pad),
  };
}

/**
 * Extract contiguous pipe-table blocks from markdown, replacing each with a
 * `<ComparisonTable idx="k"></ComparisonTable>` marker and collecting the
 * parsed tables. Lines inside fenced code blocks are never treated as tables.
 */
export interface SplitResult {
  text: string;
  tables: ParsedTable[];
}

export function splitTableBlocks(markdown: string): SplitResult {
  const lines = markdown.split("\n");
  const mask = fenceMask(lines);
  const appendix = appendixMask(lines);
  const text: string[] = [];
  const tables: ParsedTable[] = [];
  let i = 0;
  while (i < lines.length) {
    const trimmed = lines[i].trim();
    // 图表来源清单区域：原样保留（含哨兵注释与 pipe 表格），不转 ComparisonTable。
    if (appendix[i]) {
      text.push(lines[i]);
      i++;
      continue;
    }
    if (!mask[i] && trimmed.startsWith("|")) {
      const block: string[] = [];
      while (i < lines.length && !mask[i] && lines[i].trim().startsWith("|")) {
        block.push(lines[i].trim());
        i++;
      }
      const parsed = parseMarkdownTable(block);
      if (parsed.rows.length > 0) {
        tables.push(parsed);
        // Open/close on separate lines = block-level HTML (type 7) with a
        // balanced pair inside one fragment; blank lines keep it from gluing
        // onto a surrounding paragraph even when the source table was a
        // paragraph continuation.
        text.push("", `<ComparisonTable idx="${tables.length - 1}">`, "</ComparisonTable>", "");
      } else {
        text.push(...block);
      }
    } else {
      text.push(lines[i]);
      i++;
    }
  }
  return { text: text.join("\n"), tables };
}

const HEADING_RE = /^(#{1,3})\s+(.+)$/;

/**
 * Extract `#` / `##` / `###` headings with stable sequential ids, skipping
 * fences. Ids are assigned in document order so ToC entries can be matched to
 * the rendered elements (ReportCard assigns the same `section-N` ids
 * post-render). Level 1–2 surface in the ToC sidebar; level 3 keeps nesting.
 */
export function extractHeadings(markdown: string): Heading[] {
  const lines = markdown.split("\n");
  const mask = fenceMask(lines);
  const headings: Heading[] = [];
  let idx = 0;
  for (let i = 0; i < lines.length; i++) {
    if (mask[i]) continue;
    const m = lines[i].match(HEADING_RE);
    if (!m) continue;
    headings.push({
      level: m[1].length,
      text: m[2].trim(),
      id: `section-${idx}`,
    });
    idx++;
  }
  return headings;
}

/** Matches citation tokens: [1], [1,3], [1, 3], [1 3], [1][2]. */
export const CITE_TOKEN_RE = /(\[\d+(?:[,\s]+\d+)*\])/g;

/**
 * Replace citation tokens in prose with `<Paper ns="..."></Paper>` tags.
 * Must run after splitTableBlocks so table labels are untouched, and must
 * skip fenced code blocks so example `[1]` tokens in code stay literal.
 */
export function injectChips(text: string): string {
  const lines = text.split("\n");
  const mask = fenceMask(lines);
  const appendix = appendixMask(lines);
  return lines
    .map((line, i) => {
      if (mask[i] || appendix[i]) return line;
      return line.replace(CITE_TOKEN_RE, (_m, token: string) => {
        const nums = token
          .replace(/[\[\]]/g, "")
          .split(/[,\s]+/)
          .map((s) => parseInt(s, 10))
          .filter((n) => Number.isFinite(n));
        if (nums.length === 0) return token;
        return `<Paper ns="${nums.join(",")}"></Paper>`;
      });
    })
    .join("\n");
}

/** Full frontend-only preprocessing pass; the renderer consumes the result. */
export function renderMarkdown(markdown: string): { text: string; tables: ParsedTable[]; headings: Heading[] } {
  const clean = sanitize(markdown);
  const split = splitTableBlocks(clean);
  const headings = extractHeadings(split.text);
  const text = injectChips(split.text);
  return { text, tables: split.tables, headings };
}
