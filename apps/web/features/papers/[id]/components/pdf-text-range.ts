export type HighlightColor = "yellow" | "red" | "blue" | "green";

export type PdfHighlightRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PdfTextRange = {
  pageNumber: number;
  start: number;
  end: number;
};

export type PdfSelection = PdfTextRange & {
  id: string;
};

export type PdfHighlight = PdfTextRange & {
  id: string;
  color: HighlightColor;
};

export function pdfTextRangeId({ pageNumber, start, end }: PdfTextRange) {
  return `${pageNumber}:${start}:${end}`;
}

function elementForNode(node: Node): Element | null {
  return node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
}

function textLayerForNode(node: Node): { page: HTMLElement; textLayer: HTMLElement } | null {
  const element = elementForNode(node);
  const page = element?.closest(".react-pdf__Page") as HTMLElement | null;
  if (!page) return null;

  const textLayer = page.querySelector(".react-pdf__Page__textContent.textLayer") as HTMLElement | null;
  if (!textLayer || !textLayer.contains(element)) return null;

  return { page, textLayer };
}

function textNodesIn(textLayer: HTMLElement) {
  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    nodes.push(node as Text);
    node = walker.nextNode();
  }
  return nodes;
}

function textOffsetAt(textLayer: HTMLElement, container: Node, offset: number) {
  if (container !== textLayer && !textLayer.contains(container)) return null;

  const boundary = document.createRange();
  boundary.selectNodeContents(textLayer);
  boundary.setEnd(container, offset);
  return boundary.toString().length;
}

function textPositionAt(textNodes: Text[], offset: number) {
  let consumed = 0;
  for (const node of textNodes) {
    const length = node.data.length;
    if (offset <= consumed + length) {
      return { node, offset: offset - consumed };
    }
    consumed += length;
  }

  const lastNode = textNodes.at(-1);
  return lastNode ? { node: lastNode, offset: lastNode.data.length } : null;
}

export function readPdfTextSelection(selection: Selection | null): PdfSelection | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;

  const selectionRange = selection.getRangeAt(0);
  const startContext = textLayerForNode(selectionRange.startContainer);
  const endContext = textLayerForNode(selectionRange.endContainer);
  if (!startContext || startContext.page !== endContext?.page) return null;

  const { page, textLayer } = startContext;
  if (!textLayer.contains(selectionRange.startContainer) || !textLayer.contains(selectionRange.endContainer)) {
    return null;
  }

  const startOffset = textOffsetAt(textLayer, selectionRange.startContainer, selectionRange.startOffset);
  const endOffset = textOffsetAt(textLayer, selectionRange.endContainer, selectionRange.endOffset);
  if (startOffset === null || endOffset === null) return null;

  const start = Math.min(startOffset, endOffset);
  const end = Math.max(startOffset, endOffset);
  const pageNumber = Number(page.dataset.pageNumber);
  if (!Number.isInteger(pageNumber) || start >= end) return null;

  return {
    id: pdfTextRangeId({ pageNumber, start, end }),
    pageNumber,
    start,
    end,
  };
}

export function pdfTextRangeToRects(page: HTMLElement, textRange: PdfTextRange): PdfHighlightRect[] {
  const textLayer = page.querySelector(".react-pdf__Page__textContent.textLayer") as HTMLElement | null;
  if (!textLayer) return [];

  const textNodes = textNodesIn(textLayer);
  const startPosition = textPositionAt(textNodes, textRange.start);
  const endPosition = textPositionAt(textNodes, textRange.end);
  if (!startPosition || !endPosition) return [];

  const range = document.createRange();
  range.setStart(startPosition.node, startPosition.offset);
  range.setEnd(endPosition.node, endPosition.offset);

  const pageRect = page.getBoundingClientRect();
  if (!pageRect.width || !pageRect.height) return [];

  return Array.from(range.getClientRects())
    .filter((rect) => rect.width > 0 && rect.height > 0)
    .map((rect) => ({
      x: (rect.left - pageRect.left) / pageRect.width,
      y: (rect.top - pageRect.top) / pageRect.height,
      width: rect.width / pageRect.width,
      height: rect.height / pageRect.height,
    }));
}
