/**
 * 过程流（"思考 → 工具 → 思考"）的纯逻辑，零 React 依赖，可直接用真实到达序列测试。
 *
 * 条目模型对齐 pi 的 assistant 消息内容块
 * （packages/coding-agent/src/modes/interactive/components/assistant-message.ts:108-134）：
 * 一轮里 thinking 与 text 是**各自独立的块**，按到达顺序排列，各自渲染；
 * 工具执行是**与这些块并列的条目**，流式过程中按到达顺序追加
 * （interactive-mode.ts:3252-3265）。
 *
 * 两条来自实测的硬规则：
 * - 内容为空的块不渲染（pi 用 `text.trim()` / `thinking.trim()`）；
 * - 工具轮之间的过渡正文不进最终答案——它留在自己那一轮的 text 块里，答案只取最后一轮。
 */
/** 一次工具调用（页面侧 Activity 的同一形状，steps 与之共享引用）。 */
export interface Activity {
  toolCallId: string; name: string; arguments: string;
  done: boolean; isError: boolean; durationMs: number; summary?: string;
}

/** 思考条目：一段思考（不含正文）。 */
export interface ThinkingEntry { kind: "thinking"; text: string }
/** 正文条目：一轮的正文（不含思考）。 */
export interface TextEntry { kind: "text"; text: string }
/** 工具条目：一次工具执行。 */
export interface ToolEntry { kind: "tool"; tool: Activity }

export type Entry = ThinkingEntry | TextEntry | ToolEntry;

/** 折叠态单行预览：空白压平、单行截断。 */
export function previewLine(text: string, max = 80): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/**
 * 内容是否值得显示：只有标点/符号的片段不算（含字母、数字或中日韩文字才算）。
 *
 * 模型偶尔在两轮工具之间吐孤立的 `"."`，照显示就是对话框里孤零零一个句点。
 * pi 对应的是 `text.trim()`（只挡空白）；这里更严一档，因为实测出现过纯标点轮次。
 */
export function isMeaningful(text: string): boolean {
  return /[\p{L}\p{N}]/u.test(text);
}

/**
 * 过程流的可变状态。
 *
 * `entries` 是唯一真相：思考、正文、工具按到达顺序排在一起。`turn` 用于判断新一轮。
 *
 * 后端语义（runtime.py:531-539，已核对实现而非猜测）：
 * - `TextDelta` 按 ≥24 字批量发，`reasoning` 每片即发；
 * - **两者发给前端的都是增量片**（后端自己用 `assistant.content += ...` /
 *   `assistant.reasoning += ...` 累计），所以前端对两者都要**拼接**。
 */
export interface StreamState {
  turn: number;
  entries: Entry[];
  /** 本轮思考/正文条目在 entries 中的下标；-1 表示本轮还没这类条目。 */
  thinkingIndex: number;
  textIndex: number;
}

export function initialStreamState(): StreamState {
  return { turn: 0, entries: [], thinkingIndex: -1, textIndex: -1 };
}

/**
 * 把增量片拼进**本轮**对应条目，不跨轮找。
 *
 * 早先的实现从数组末尾向后扫描找同类型条目，于是第 3 轮的正文拼到了第 2 轮那个 `"."`
 * 条目上（实测输出 `"..Answer here."`）。按轮次记账才是正确的边界。
 */
function appendAt(entries: Entry[], index: number, kind: "thinking" | "text", chunk: string): Entry[] {
  const existing = index >= 0 ? entries[index] : undefined;
  if (existing && existing.kind === kind) {
    const next = [...entries];
    next[index] = { kind, text: existing.text + chunk } as Entry;
    return next;
  }
  return [...entries, { kind, text: chunk } as Entry];
}

/**
 * 收到一个 delta：把增量片拼进本轮对应的条目；turn 变化则开新条目。
 *
 * 语义依据 runtime.py:531-539（核对实现，不靠猜）：text 与 reasoning 发给前端的**都是增量片**，
 * 累计在客户端完成。曾经把 reasoning 当成"每轮累计全量"而整体替换，由此引出一连串假问题。
 */
export function applyDelta(state: StreamState, text: string, reasoning: string, turn: number): StreamState {
  if (turn !== state.turn) {
    const entries = [...state.entries];
    let thinkingIndex = -1;
    let textIndex = -1;
    if (reasoning) { thinkingIndex = entries.length; entries.push({ kind: "thinking", text: reasoning }); }
    if (text) { textIndex = entries.length; entries.push({ kind: "text", text }); }
    return { turn, entries, thinkingIndex, textIndex };
  }
  let { entries, thinkingIndex, textIndex } = state;
  if (reasoning) {
    if (thinkingIndex < 0) thinkingIndex = entries.length;
    entries = appendAt(entries, thinkingIndex, "thinking", reasoning);
  }
  if (text) {
    if (textIndex < 0) textIndex = entries.length;
    entries = appendAt(entries, textIndex, "text", text);
  }
  return { turn, entries, thinkingIndex, textIndex };
}

/** 工具调用到达：追加一个并列的工具条目。 */
export function applyToolCall(state: StreamState, tool: Activity): StreamState {
  return { ...state, entries: [...state.entries, { kind: "tool", tool }] };
}

/** 工具结束：把结果回填到**同一个**工具对象（页面侧的 steps 与本状态共享引用，故两处同步）。 */
export function applyToolEnd(state: StreamState, toolCallId: string, patch: Partial<Activity>): StreamState {
  return {
    ...state,
    entries: state.entries.map((entry) =>
      entry.kind === "tool" && entry.tool.toolCallId === toolCallId
        ? { kind: "tool", tool: { ...entry.tool, ...patch } }
        : entry),
  };
}

/**
 * 渲染序列：按到达顺序取条目，丢弃无内容者（pi 的空块判定）。
 * 不相邻同类型条目也不做特殊合并——每个条目的文本已经是该轮的完整内容。
 */
export function renderEntries(state: StreamState): Entry[] {
  return state.entries.filter((entry) => {
    if (entry.kind === "tool") return true;
    return isMeaningful(entry.text);
  });
}

/**
 * 旧会话恢复：早期持久化的是 `{steps, segments, narrations}` 三件套，这里折算成新条目。
 * 没有可显示内容时返回空数组，调用方据此不渲染过程区。
 */
export function restoreEntries(
  segments: Array<{ kind: "reasoning"; text: string } | { kind: "tool"; tool: Activity }> | undefined,
  activity: Activity[] | undefined,
): Entry[] {
  if (segments?.length) {
    return segments.map((segment) => segment.kind === "tool"
      ? { kind: "tool" as const, tool: segment.tool }
      : { kind: "thinking" as const, text: segment.text });
  }
  return (activity ?? []).map((tool) => ({ kind: "tool" as const, tool }));
}
