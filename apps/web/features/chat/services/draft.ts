import type {
  ChatAttachment,
  ChatModelId,
  ChatReplyMode,
  ComposerSubmitPayload,
} from "../../../types/ai-search";
import { DEFAULT_CHAT_MODEL } from "./model-catalog";

const KEY = "shenzhi.chat.draft";

export interface AskDraft {
  question: string;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  attachments: ChatAttachment[];
}

const DEFAULTS: Omit<AskDraft, "question"> = {
  mode: "fast",
  model: DEFAULT_CHAT_MODEL,
  web_search: false,
  attachments: [],
};

export function saveAskDraft(payload: ComposerSubmitPayload) {
  if (typeof window === "undefined") return;
  const draft: AskDraft = {
    question: payload.question,
    mode: payload.mode,
    model: payload.model,
    web_search: payload.web_search,
    attachments: payload.attachments,
  };
  try { sessionStorage.setItem(KEY, JSON.stringify(draft)); } catch { /* Storage may be disabled. */ }
}

export function readAskDraft(question: string): AskDraft {
  const fallback: AskDraft = { question, ...DEFAULTS };
  if (typeof window === "undefined") return fallback;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<AskDraft>;
    const sameQuestion =
      !parsed.question || parsed.question === question || !question;
    return {
      question: question || parsed.question || "",
      mode: sameQuestion && parsed.mode ? parsed.mode : DEFAULTS.mode,
      model: sameQuestion && parsed.model ? parsed.model : DEFAULTS.model,
      web_search:
        sameQuestion && typeof parsed.web_search === "boolean"
          ? parsed.web_search
          : DEFAULTS.web_search,
      attachments:
        sameQuestion && Array.isArray(parsed.attachments)
          ? parsed.attachments
          : [],
    };
  } catch {
    return fallback;
  }
}

export function clearAskDraft() {
  if (typeof window === "undefined") return;
  try { sessionStorage.removeItem(KEY); } catch { /* Storage may be disabled. */ }
}

export function askQueryString(payload: ComposerSubmitPayload) {
  const params = new URLSearchParams({
    q: payload.question,
    mode: payload.mode,
    model: payload.model,
    web_search: payload.web_search ? "1" : "0",
  });
  return params.toString();
}
