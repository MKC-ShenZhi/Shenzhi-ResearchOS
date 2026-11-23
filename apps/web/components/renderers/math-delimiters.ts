function getFence(source: string, lineStart: number) {
  let index = lineStart;
  while (index < source.length && index - lineStart < 3 && source[index] === " ") {
    index += 1;
  }

  const marker = source[index];
  if (marker !== "`" && marker !== "~") return null;

  let end = index;
  while (source[end] === marker) end += 1;
  if (end - index < 3) return null;

  return { marker, length: end - index };
}

function getClosingFence(source: string, lineStart: number, fence: { marker: string; length: number }) {
  let index = lineStart;
  while (index < source.length && index - lineStart < 3 && source[index] === " ") {
    index += 1;
  }

  if (source[index] !== fence.marker) return false;
  let end = index;
  while (source[end] === fence.marker) end += 1;
  if (end - index < fence.length) return false;

  while (end < source.length && source[end] !== "\n") {
    if (source[end] !== " " && source[end] !== "\t" && source[end] !== "\r") return false;
    end += 1;
  }
  return true;
}

function countRun(source: string, index: number, character: string) {
  let end = index;
  while (source[end] === character) end += 1;
  return end - index;
}

function findCodeSpanEnd(source: string, start: number, delimiterLength: number) {
  for (let index = start; index < source.length;) {
    if (source[index] !== "`") {
      index += 1;
      continue;
    }

    const runLength = countRun(source, index, "`");
    if (runLength === delimiterLength) return index + runLength;
    index += runLength;
  }
  return -1;
}

function isEscaped(source: string, index: number) {
  let backslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && source[cursor] === "\\"; cursor -= 1) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
}

function findMathEnd(source: string, start: number, closing: string) {
  for (let index = start; index < source.length;) {
    if (source[index] === "`" && !isEscaped(source, index)) {
      const runLength = countRun(source, index, "`");
      const end = findCodeSpanEnd(source, index + runLength, runLength);
      if (end !== -1) {
        index = end;
        continue;
      }
    }

    if (source.startsWith(closing, index) && !isEscaped(source, index)) return index;
    index += 1;
  }
  return -1;
}

function isStandaloneMath(source: string, start: number, end: number) {
  const lineStart = source.lastIndexOf("\n", start - 1) + 1;
  const lineEndIndex = source.indexOf("\n", end);
  const lineEnd = lineEndIndex === -1 ? source.length : lineEndIndex;

  return source.slice(lineStart, start).trim() === ""
    && source.slice(end, lineEnd).trim() === "";
}

export function normalizeMathDelimiters(markdown: string) {
  let output = "";
  let index = 0;
  let fence: { marker: string; length: number } | null = null;

  while (index < markdown.length) {
    const atLineStart = index === 0 || markdown[index - 1] === "\n";
    const lineEnd = markdown.indexOf("\n", index);
    const afterLine = lineEnd === -1 ? markdown.length : lineEnd + 1;

    if (atLineStart) {
      if (fence && getClosingFence(markdown, index, fence)) {
        output += markdown.slice(index, afterLine);
        index = afterLine;
        fence = null;
        continue;
      }

      if (!fence) {
        fence = getFence(markdown, index);
        if (fence) {
          output += markdown.slice(index, afterLine);
          index = afterLine;
          continue;
        }
      }
    }

    if (fence) {
      output += markdown[index];
      index += 1;
      continue;
    }

    if (markdown[index] === "`" && !isEscaped(markdown, index)) {
      const runLength = countRun(markdown, index, "`");
      const codeEnd = findCodeSpanEnd(markdown, index + runLength, runLength);
      if (codeEnd !== -1) {
        output += markdown.slice(index, codeEnd);
        index = codeEnd;
        continue;
      }
    }

    const isDisplayDelimiter = markdown.startsWith("\\[", index);
    const isInlineDelimiter = markdown.startsWith("\\(", index);
    if ((isDisplayDelimiter || isInlineDelimiter) && !isEscaped(markdown, index)) {
      const closing = isDisplayDelimiter ? "\\]" : "\\)";
      const contentStart = index + 2;
      const closingIndex = findMathEnd(markdown, contentStart, closing);
      if (closingIndex !== -1) {
        const content = markdown.slice(contentStart, closingIndex).trim();
        const closingEnd = closingIndex + 2;
        const standalone = isDisplayDelimiter
          && isStandaloneMath(markdown, index, closingEnd);

        output += standalone ? `$$\n${content}\n$$` : `$${content}$`;
        index = closingEnd;
        continue;
      }
    }

    output += markdown[index];
    index += 1;
  }

  return output;
}
