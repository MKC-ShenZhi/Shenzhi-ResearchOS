const PREFIX = "针对之前回答中的这段内容：\n\n";
const QUESTION = "\n\n我的问题/意见是：";

/** The existing wire/storage format stays intact; only its presentation is split. */
export function quotedPromptParts(prompt: string): { question: string; quote?: string } {
  if (!prompt.startsWith(PREFIX)) return { question: prompt };
  const boundary = prompt.lastIndexOf(QUESTION);
  if (boundary < PREFIX.length) return { question: prompt };
  const quote = prompt.slice(PREFIX.length, boundary);
  const question = prompt.slice(boundary + QUESTION.length);
  return quote.trim() && question.trim() ? { question, quote } : { question: prompt };
}

export function withQuote(prompt: string, quote: { text: string } | null) {
  return quote ? `${PREFIX}${quote.text}${QUESTION}${prompt}` : prompt;
}
