"use client";

// ShenzhiAi 持久化对话页（ChatGPT 式排版）：
// 左：全局 AppSidebar 中的 Backend Agent 会话历史
// 中：用户右气泡 / 回答左通栏（头像 + 思考折叠 + 过程卡）/ 运行中插话右气泡
// 空状态：轻量提示并引导回发现页开始新对话
// 下：居中悬浮 Composer；运行中发送 = 插话（steer，不打断当前工具批）
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText, MessageCircleQuestion, Quote, Sparkles, Zap } from "lucide-react";

import {
  createWorkspace, exportAgentSession, fetchAgentConfig, getAgentSession, steerAgentRun,
  stopAgentRun, streamAgentSessionRun, uploadWorkspaceFile,
  type AgentConfig, type AgentQuestion, type AgentQuestionOption, type AgentRunInput,
  type AgentRunResult, type AgentStoredTurn,
} from "@/clients/backend/agent";
import { ReportDialog } from "./report-dialog";
import { Timeline } from "./timeline-view";
import {
  applyDelta, applyToolCall, applyToolEnd, initialStreamState, isMeaningful, restoreEntries,
  type Entry, type StreamState,
} from "./timeline";
import { ComposerShell, type ComposerSkill } from "@/components/common/composer/composer";
import type { WorkspaceFile } from "@/components/common/composer/attachment-menu";
import { AppShell } from "@/components/common/layout/app-shell";
import type { ChatAttachment, ChatConfig } from "@/types/ai-search";
import { takeAgentLaunch } from "./launch-store";
import { notifyAgentSessionsChanged } from "./session-events";

// 类型别名而非 interface：报告渲染器（ReportView）要的是带索引签名的 AgentSource，
// interface 不满足索引签名（TS2322），别名可以直接赋给它。
type Source = { title?: string; url?: string };

/** 问题轮次回传历史时的文本形态：模型需要在下一轮看到"自己问过什么"。 */
function askedText(question?: AgentQuestion): string {
  return question?.question ?? "";
}

// 过程流（思考 → 工具 → 思考）的全部状态机在 ./timeline.ts，渲染在 ./timeline-view.tsx。
// 这两块曾经内联在本文件里，无法被测试，导致同一个显示 bug 反复出现——所以彻底搬了出去。

/** agent 反问：单问题制品（{question, options, allow_other, header}）。 */
function QuestionCard({ question, onAnswer, busy }: {
  question: { question: string; options?: AgentQuestionOption[]; allow_other?: boolean; header?: string | null };
  onAnswer: (text: string) => void;
  busy: boolean;
}) {
  const options = question.options ?? [];
  return (
    <div className="mt-3 rounded-2xl border border-primary/25 bg-primary-soft/40 p-3.5">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-primary">
        <MessageCircleQuestion className="h-3.5 w-3.5" />
        {question.header || "需要你确认"}
      </div>
      <div className="text-[14px] leading-6 text-ink">{question.question}</div>
      {options.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={busy}
              onClick={() => onAnswer(option.value)}
              title={option.description ?? undefined}
              className="cursor-pointer rounded-full border border-primary/30 bg-card px-3 py-1.5 text-[13px] text-ink transition-colors hover:border-primary hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {option.label ?? option.value}
            </button>
          ))}
        </div>
      )}
      {options.some((option) => option.description) && (
        <ul className="mt-2 space-y-0.5">
          {options.filter((option) => option.description).map((option) => (
            <li key={`${option.value}-desc`} className="text-[11px] leading-5 text-muted">
              <span className="text-ink/70">{option.label ?? option.value}</span>：{option.description}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 text-[11px] text-muted">
        点选项即作为你的回答发送{question.allow_other === false ? "" : "；也可以直接在下方输入你自己的答案"}
      </div>
    </div>
  );
}

/** 引用回复：选中历史回答片段 → 新消息自动附原文锚点（ChatGPT reply-to-message 同类交互）。 */
interface QuoteDraft { text: string }

interface SteerNote { text: string; kind: "steer" | "follow_up" | "system" }

interface Turn {
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  /** 过程流的全部状态（思考 / 正文 / 工具按到达顺序交错）；渲染与持久化都从它派生。 */
  stream: StreamState;
  steers: SteerNote[];
  report?: string;
  sources?: Source[];
  /** agent 反问的问题（status=awaiting_input）：界面据此渲染候选项。一次一个。 */
  question?: AgentQuestion;
  warnings?: string[];
  error?: string;
  stopped?: boolean;
  /** 终态原因（timeout / cancelled / max_turns…）：同一句"已停止"说不清是到点了还是你停的。 */
  stopReason?: string;
}

/** 终态原因 → 人话（stop_reason 是后端枚举：StopReason）。 */
function stopLabel(reason?: string): string {
  switch (reason) {
    case "timeout": return "（到达本轮时间上限，已完成的内容如上）";
    case "cancelled": return "（已手动停止）";
    case "max_turns": return "（达到最大轮数限制）";
    case "length": return "（输出达到长度上限，内容可能不完整）";
    case "error": return "（运行出错，见上方提示）";
    default: return "（本轮已停止）";
  }
}

/** 持久化形状 → 过程流（旧会话只有 activity 时按工具顺序恢复）。 */
function fromStoredTurn(turn: AgentStoredTurn): StreamState {
  const segments = turn.process;
  const entries: Entry[] = segments?.length
    ? segments.map((segment) => segment.kind === "tool"
        ? { kind: "tool" as const, tool: segment.tool }
        : { kind: segment.kind === "text" ? "text" as const : "thinking" as const, text: segment.text })
    : restoreEntries(undefined, undefined);
  return { turn: 0, entries, thinkingIndex: -1, textIndex: -1 };
}

const FALLBACK_CONFIG: AgentConfig = {
  models: [], default_model: "default", skills: [],
  upload: { max_size_mb: 0, max_files: 0, accept: [] },
};

function Md({ text }: { text: string }) {
  return <div className="min-w-0 break-words text-[15px] leading-7">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      p: ({ children }) => <p className="my-2">{children}</p>,
      ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
      h1: ({ children }) => <h2 className="mb-2 mt-5 text-lg font-semibold">{children}</h2>,
      h2: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold">{children}</h3>,
      h3: ({ children }) => <h4 className="mb-1 mt-3 font-semibold">{children}</h4>,
      code: ({ children }) => <code className="rounded bg-chip px-1 font-mono text-[13px]">{children}</code>,
      pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-xl bg-panel p-3 leading-6">{children}</pre>,
      a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a>,
      table: ({ children }) => <div className="my-3 overflow-x-auto"><table className="w-full border-collapse">{children}</table></div>,
      th: ({ children }) => <th className="border border-line bg-sidebar px-3 py-2 text-left">{children}</th>,
      td: ({ children }) => <td className="border border-line px-3 py-2">{children}</td>,
      blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-primary/40 pl-3 text-muted">{children}</blockquote>,
    }}>{text}</ReactMarkdown>
  </div>;
}

function Sources({ sources }: { sources: Source[] }) {
  return <div className="mt-3 border-t border-line pt-2">
    <div className="mb-1 text-xs font-medium text-muted">参考来源（{sources.length}）</div>
    <ol className="list-decimal space-y-1 pl-5 text-xs text-muted">
      {sources.map((source, index) => {
        const title = source.title || source.url || "(未命名)";
        return <li key={index}>
          {source.url
            ? <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{title}</a>
            : title}
        </li>;
      })}
    </ol>
  </div>;
}

function AssistantAvatar() {
  return <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-agent text-white shadow-card" aria-hidden>
    <Sparkles className="size-4" strokeWidth={2} />
  </div>;
}

// 运行中的实时观感由 Timeline 承接（对应条目带 spinner），不再单独渲染活动卡。

/** 报告摘要卡：对话里只给标题与开头几行，全文在弹层里看（避免几十页 markdown 铺满对话）。 */
function ReportSummary({ text, sources, onOpen }: {
  text: string;
  sources?: Source[];
  onOpen: () => void;
}) {
  const firstHeading = text.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? "研究报告";
  const plain = text.replace(/^#+\s+.*$/gm, "").replace(/[*_`>|[\]()]/g, "").replace(/\s+/g, " ").trim();
  return <div className="mt-3 rounded-2xl border border-line bg-card p-4 shadow-card">
    <div className="flex items-start gap-2">
      <FileText className="mt-0.5 size-4 shrink-0 text-agent" strokeWidth={2} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold text-ink">{firstHeading}</div>
        <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-muted">{plain.slice(0, 200)}…</p>
        <div className="mt-1 text-[11px] text-faint">
          {text.length.toLocaleString()} 字{sources?.length ? ` · ${sources.length} 条来源` : ""}
        </div>
      </div>
      <button type="button" onClick={onOpen}
        className="shrink-0 cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-primary/90">
        查看报告
      </button>
    </div>
  </div>;
}

export function ShenzhiAiPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const launchId = searchParams.get("launch");
  const [agentConfig, setAgentConfig] = useState<AgentConfig>(FALLBACK_CONFIG);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionTitle, setSessionTitle] = useState("Agent 会话");
  const [hydratedSessionId, setHydratedSessionId] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [steerError, setSteerError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [workspace, setWorkspace] = useState<{ id: string; name: string; files: number } | null>(null);
  const [model, setModel] = useState("default");
  // 默认 fast。预算对齐 SZDR 的实测形态（15 分钟 / 120 次工具调用，见后端 policies.py）：
  // deadline 是上限不是目标，快问题照样快回；mode 只是资源倾向，不是方法论档位。
  const [mode, setMode] = useState<"fast" | "deep" | "idea" | "doubt">("fast");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<ComposerSkill[]>([]);
  const [quote, setQuote] = useState<QuoteDraft | null>(null);   // 引用回复草稿
  /** 正在弹层里查看的报告（null = 关闭）。 */
  const [openReport, setOpenReport] = useState<{ text: string; sources?: Source[] } | null>(null);
  const [exporting, setExporting] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);
  const loadedSessionRef = useRef<string | null>(null);

  useEffect(() => {
    fetchAgentConfig().then((config) => {
      setAgentConfig(config);
      setModel((current) => current === "default" ? config.default_model || "default" : current);
      setSelectedSkills((current) => current.map((selected) =>
        config.skills.find((skill) => skill.name === selected.name) ?? selected));
    }).catch(() => { /* 后端不可用时保持 fallback，发送时给出可读错误 */ });
  }, []);

  useEffect(() => {
    if (!sessionId) {
      router.replace("/");
      return;
    }
    if (loadedSessionRef.current && loadedSessionRef.current !== sessionId) {
      if (runIdRef.current) void stopAgentRun(runIdRef.current).catch(() => {});
      abortRef.current?.abort();
    }
    loadedSessionRef.current = sessionId;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setRunning(false);
      setLoadingSession(true);
      setHydratedSessionId(null);
      setRunError(null);
      void getAgentSession(sessionId).then((session) => {
        if (!active) return;
        setSessionTitle(session.title);
        setTurns(session.turns.flatMap((turn) => [
          { role: "user" as const, content: turn.user_content, reasoning: "",
            stream: initialStreamState(), steers: [] },
          { role: "assistant" as const, content: turn.assistant_content,
            reasoning: turn.reasoning ?? "", stream: fromStoredTurn(turn),
            steers: turn.steers ?? [], report: turn.report ?? undefined,
            sources: turn.sources, question: turn.question ?? undefined,
            warnings: turn.warnings, error: turn.error ?? undefined,
            stopped: turn.stopped, stopReason: turn.stop_reason ?? undefined },
        ]));
        const settings = session.settings ?? {};
        setModel(settings.model || "default");
        if (settings.mode) setMode(settings.mode);
        setAttachments((settings.attachments ?? []) as ChatAttachment[]);
        setSelectedSkills((settings.skills ?? []).map((name) => ({ name, description: "" })));
        setWorkspace(settings.workspace_id
          ? { id: settings.workspace_id, name: "会话工作区", files: 0 } : null);
        setHydratedSessionId(session.id);
      }).catch((cause) => {
        if (!active) return;
        setRunError(cause instanceof Error ? cause.message : "会话不存在或无权访问");
      }).finally(() => {
        if (active) setLoadingSession(false);
      });
    });
    return () => { active = false; };
  }, [sessionId, router]);

  useEffect(() => {
    if (stickRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [turns]);

  const patchAssistant = useCallback((patch: (turn: Turn) => Turn) => {
    setTurns((previous) => {
      const index = previous.map((turn) => turn.role).lastIndexOf("assistant");
      if (index === -1) return previous;
      const next = [...previous];
      next[index] = patch(previous[index]);
      return next;
    });
  }, []);

  const handleWorkspaceFolder = useCallback(async (files: WorkspaceFile[]) => {
    setRunError(null);
    setUploading(true);
    try {
      const createdId = workspace?.id ?? (await createWorkspace()).workspace_id;
      const name = files[0]?.relativePath.split("/")[0] ?? "workspace";
      let uploaded = 0;
      const errors: string[] = [];
      for (const item of files.slice(0, 200)) {
        if (item.file.size > 5 * 1024 * 1024) { errors.push(`${item.relativePath} 超过 5MB`); continue; }
        try {
          await uploadWorkspaceFile(createdId, item.file, item.relativePath);
          uploaded += 1;
        } catch (error) { errors.push(error instanceof Error ? error.message : `${item.relativePath} 上传失败`); }
      }
      setWorkspace({ id: createdId, name, files: uploaded });
      if (errors.length) setRunError(errors.join("；"));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "工作区创建失败");
    } finally {
      setUploading(false);
    }
  }, [workspace]);

  const toggleSkill = useCallback((name: string) => {
    setSelectedSkills((previous) => previous.some((skill) => skill.name === name)
      ? previous.filter((skill) => skill.name !== name)
      : [...previous, ...agentConfig.skills.filter((skill) => skill.name === name)]);
  }, [agentConfig]);

  /** All normal sends and the home-page launch use this exact persisted run path. */
  const runPrompt = useCallback(async (runInput: AgentRunInput) => {
    const prompt = runInput.prompt.trim();
    if (!prompt || running || !sessionId) return;
    setTurns((previous) => [...previous,
      { role: "user", content: prompt, reasoning: "", stream: initialStreamState(), steers: [] },
      { role: "assistant", content: "", reasoning: "", stream: initialStreamState(), steers: [] }]);
    setInput("");
    setRunError(null);
    setSteerError(null);
    setRunning(true);
    runIdRef.current = null;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamAgentSessionRun(sessionId, runInput, {
        onRunStart: (runId) => { runIdRef.current = runId; },
        onDelta: (text, reasoning, turn) => patchAssistant((current) => {
          // 状态机全在 timeline.ts（可测）。这里只负责把它与页面的 Turn 接起来。
          return {
            ...current,
            stream: applyDelta(current.stream, text, reasoning, turn),
            content: turn !== current.stream.turn ? text : current.content + text,
            reasoning: turn !== current.stream.turn ? reasoning : current.reasoning + reasoning,
          };
        }),
        onMeta: (data) => {
          if (data.warnings?.length) patchAssistant((turn) => ({ ...turn, warnings: data.warnings }));
        },
        onMessage: (text, kind) => patchAssistant((turn) => ({
          ...turn, steers: [...turn.steers, { text, kind }],
        })),
        onCompaction: ({ before_chars, after_chars }) => patchAssistant((turn) => ({
          ...turn, steers: [...turn.steers, {
            kind: "system", text: `上下文已压缩（${before_chars} → ${after_chars} 字符）`,
          }],
        })),
        onToolCall: (activity) => patchAssistant((turn) => ({
          ...turn,
          stream: applyToolCall(turn.stream, activity),
        })),
        onToolEnd: (toolCallId, isError, durationMs, summary) => patchAssistant((turn) => ({
          ...turn,
          // 回填到同一个工具对象：工具行据此从"转圈"变"完成"
          stream: applyToolEnd(turn.stream, toolCallId, { done: true, isError, durationMs, summary }),
        })),
        onResult: (result: AgentRunResult) => {
          patchAssistant((turn) => {
          const sources = result.output?.sources;
          return {
            ...turn,
            // 问题由 QuestionCard 渲染（避免正文与卡片重复同一段文字），content 只放报告/正文
            report: result.output?.report,
            sources: sources?.length ? sources : undefined,
            question: result.question ?? undefined,
            error: result.status === "failed" ? result.error?.message ?? "运行失败" : undefined,
            stopped: result.status === "stopped" || result.status === "timeout",
            stopReason: result.stop_reason,
            // 超时/停止时，模型在被打断前写出的正文此前被整段丢掉（界面只剩"已停止"）：
            // content 为空就补上 final_text（有流式正文时不重复）。
            content: result.question ? "" : turn.content || result.final_text || "",
          };
          });
          notifyAgentSessionsChanged();
        },
      }, controller.signal);
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        patchAssistant((turn) => ({ ...turn, stopped: true }));
      } else {
        setRunError((error as Error).message || "连接失败，请稍后重试");
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
      runIdRef.current = null;
    }
  }, [running, sessionId, patchAssistant]);

  const send = useCallback(async (answer?: string) => {
    let prompt = (answer ?? input).trim();
    if (!prompt || running) return;
    const skillsForRun = selectedSkills.map((skill) => skill.name);
    if (quote) {
      const quoted = quote.text.slice(0, 2_000);
      prompt = `针对之前回答中的这段内容：\n\n${quoted}\n\n我的问题/意见是：${prompt}`;
      setQuote(null);
    }
    if (prompt.startsWith("/research ")) {
      const skill = agentConfig.skills.find((item) => item.name === "deep-research");
      if (!skill) {
        setRunError("深度研究技能尚未安装，请直接提问或使用基础检索工具");
        return;
      }
      const topic = prompt.slice("/research ".length).trim();
      prompt = `对「${topic}」执行 deep-research 技能的深度研究流程，交付带引用的研究报告。`;
      if (!skillsForRun.includes(skill.name)) {
        setSelectedSkills((previous) => [...previous, skill]);
        skillsForRun.push(skill.name);
      }
    }
    await runPrompt({
      prompt, model: model === "default" ? undefined : model, mode,
      attachments, workspace_id: workspace?.id, skills: skillsForRun,
    });
  }, [input, running, selectedSkills, quote, agentConfig, runPrompt, model, mode, attachments, workspace]);

  useEffect(() => {
    if (!launchId || hydratedSessionId !== sessionId || running) return;
    const launch = takeAgentLaunch(launchId, sessionId);
    if (!launch) return;
    queueMicrotask(() => {
      void runPrompt(launch);
      router.replace(`/agents?session=${encodeURIComponent(sessionId)}`, { scroll: false });
    });
  }, [launchId, hydratedSessionId, sessionId, running, runPrompt, router]);

  /** 运行中发送 = 插话（steer）：不打断当前工具批，下一个模型请求前注入。 */
  const steer = useCallback(async () => {
    const text = input.trim();
    if (!text || !running || !runIdRef.current) return;
    setInput("");
    setSteerError(null);
    try {
      await steerAgentRun(runIdRef.current, text);
    } catch (error) {
      setInput(text);
      setSteerError(error instanceof Error ? error.message : "插话失败，请重试");
    }
  }, [input, running]);

  const stop = useCallback(async () => {
    const runId = runIdRef.current;
    if (!runId) {
      abortRef.current?.abort();
      return;
    }
    try {
      await stopAgentRun(runId);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "停止失败，请重试");
    }
  }, []);

  /** 引用回复：mouseup 后若在回答区（data-quote-source）内有选区，展示引用条。 */
  const captureQuote = useCallback(() => {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? '';
    if (text.length >= 2 && text.length <= 2_000 && selection?.anchorNode) {
      const el = (selection.anchorNode.nodeType === 1
        ? selection.anchorNode : selection.anchorNode.parentElement) as HTMLElement | null;
      if (el?.closest('[data-quote-source]')) {
        setQuote({ text });
        return;
      }
    }
  }, []);

  /** 导出当前会话：POST 本地轮次 → 下载 HTML/JSONL（pi session-export 同构）。 */
  const exportSession = useCallback(async (format: "html" | "jsonl") => {
    if (turns.length === 0 || exporting) return;
    setExporting(true);
    try {
      const messages = turns
        .filter((turn) => turn.role === "user"
          || (turn.role === "assistant" && (turn.content || turn.report || turn.question)))
        .map((turn) => turn.role === "user"
          ? { kind: "user", text: turn.content }
          : { kind: "assistant", content: turn.report ?? turn.content ?? askedText(turn.question),
              reasoning: turn.reasoning || "",
              tool_calls: turn.stream.entries
                .filter((entry): entry is Extract<Entry, { kind: "tool" }> => entry.kind === "tool")
                .map((entry) => ({ id: entry.tool.toolCallId, name: entry.tool.name, arguments: entry.tool.arguments })),
              stop_reason: "stop" });
      const { blob, filename } = await exportAgentSession({ title: sessionTitle, messages, format });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "导出失败，请重试");
    } finally {
      setExporting(false);
    }
  }, [turns, exporting, sessionTitle]);

  /**
   * 回答 agent 的提问：点选项即发（填入输入框并立刻发送，下一帧触发一次 send）。
   * 没有"部分确认"的中间状态——一次只有一个问题，所以点选即答案。
   */
  const answerQuestion = useCallback((text: string) => {
    if (running || !text.trim()) return;
    void send(text);
  }, [running, send]);

  const chatConfig = {
    models: agentConfig.models,
    default_model: agentConfig.default_model,
    modes: ["fast", "deep", "idea", "doubt"],
    quota: { used: 0, limit: 0, deep_used: 0, deep_limit: 0 },
    quota_enforced: false,
    upload: agentConfig.upload,
  } as ChatConfig;


  return <AppShell>
    <div className="flex h-[calc(100vh-3.5rem)] lg:h-screen">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line px-6 py-3">
          <h1 className="max-w-[45%] truncate text-base font-semibold">{sessionTitle}</h1>
          <div className="flex items-center gap-2">
            <span className="mr-1 hidden text-[11px] text-faint sm:inline">选中回答文本可引用追问</span>
            <button type="button" disabled={turns.length === 0 || exporting} onClick={() => void exportSession("html")}
              className="flex cursor-pointer items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary disabled:cursor-default disabled:opacity-40">
              <Download className="size-3.5" strokeWidth={2} aria-hidden />
              {exporting ? "导出中…" : "导出 HTML"}
            </button>
            <button type="button" disabled={turns.length === 0 || exporting} onClick={() => void exportSession("jsonl")}
              className="cursor-pointer rounded-lg border border-line px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary disabled:cursor-default disabled:opacity-40">
              JSONL
            </button>
          </div>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto"
          onMouseUp={captureQuote}
          onScroll={(event) => {
            const el = event.currentTarget;
            stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}>
          {/* 宽度按可用空间走，不再死卡 768px 居中：宽屏下左右两侧会留下大片死空白
              （用户反馈"死空白太多"）。上限放宽到 1100px 只防止超宽屏上单行过长难以阅读。 */}
          <div className="mx-auto w-full max-w-[1100px] px-6 pt-8">
            {turns.length === 0 && !running && (
              <div className="mt-24 mb-16 text-center">
                <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary" aria-hidden>
                  <Sparkles className="size-6" strokeWidth={2} />
                </div>
                <p className="text-sm text-muted">
                  {loadingSession ? "正在加载会话…" : runError ? "无法打开这个会话" : "这个会话还没有消息"}
                </p>
                {!loadingSession && (
                  <button type="button" onClick={() => router.push("/")}
                    className="mt-4 cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-deep">
                    返回发现页开始新对话
                  </button>
                )}
              </div>
            )}
            {turns.map((turn, index) => turn.role === "user"
              ? <div key={index} className="mb-6 flex justify-end">
                  <div className="max-w-[75%] whitespace-pre-wrap rounded-3xl bg-chip px-4 py-2.5 text-[15px] leading-7 text-ink">
                    {turn.content}
                  </div>
                </div>
              : <div key={index} className="mb-8">
                  {/* 过程流：思考 / 正文 / 工具按到达顺序交错（pi 的结构）。空时不渲染任何盒子。 */}
                  <Timeline state={turn.stream} live={running && index === turns.length - 1} />
                  {turn.steers.map((note, noteIndex) => (
                    <div key={noteIndex} className="mb-3 flex items-center justify-end gap-1.5">
                      <span className="rounded-full bg-agent-soft px-2 py-0.5 text-[10px] font-medium text-agent">
                        {note.kind === "steer" ? "⚡ 插话"
                        : note.kind === "system" ? "⚙ 系统提示" : "→ 追问"}
                      </span>
                      <div className="max-w-[70%] rounded-2xl rounded-br-md border border-agent/30 bg-agent-soft px-3.5 py-2 text-[14px] leading-6 text-ink">
                        {note.text}
                      </div>
                    </div>
                  ))}
                  {turn.warnings?.length ? (
                    <div className="mb-2 text-xs text-amber-600 dark:text-amber-400">⚠ {turn.warnings.join("；")}</div>
                  ) : null}
                  {(isMeaningful(turn.reasoning) || isMeaningful(turn.content)
                    || turn.report || turn.question || turn.error || turn.stopped) && (
                  <div className="flex gap-3">
                    <AssistantAvatar />
                    <div className="min-w-0 flex-1" data-quote-source>
                      {/* 只有标点的正文不渲染：模型常在工具轮之间吐孤立的 "."。 */}
                      {turn.content && isMeaningful(turn.content) && <Md text={turn.content} />}
                      {turn.report && (
                        // 报告只在按钮里看全文：正文内联渲染会把几十页 markdown 铺满对话。
                        <ReportSummary
                          text={turn.report}
                          sources={turn.sources}
                          onOpen={() => setOpenReport({ text: turn.report!, sources: turn.sources })}
                        />
                      )}
                      {turn.question ? (
                        // 只有"正在跑"时才禁用：此前写成 `running || index !== turns.length - 1`，
                        // 而问题到达时 run 已结束、它那一轮又不是最后一轮，于是按钮被永久锁死
                        // （能看到问题但点不动）。
                        <QuestionCard
                          question={turn.question}
                          busy={running}
                          onAnswer={(text) => answerQuestion(text)}
                        />
                      ) : null}
                      {turn.sources && !turn.report && <Sources sources={turn.sources} />}
                      {turn.error && <div className="mt-1 text-sm text-red-600 dark:text-red-400">{turn.error}</div>}
                      {turn.stopped && (
                        <div className="mt-1 text-xs text-muted">{stopLabel(turn.stopReason)}</div>
                      )}
                    </div>
                  </div>)}
                </div>)}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="px-6 pb-4">
          <div className="mx-auto w-full max-w-[1100px]">
            {workspace && (
              <div className="mb-1.5 flex items-center gap-2">
                <span className="rounded-full bg-chip px-2.5 py-1 text-[11px] text-ink-2">
                  📁 工作区 {workspace.name}（{workspace.files} 个文件）
                </span>
                <button onClick={() => setWorkspace(null)} className="text-[11px] text-muted hover:text-ink">移除</button>
              </div>
            )}
            {quote && (
              <div className="mb-1.5 flex items-start gap-2 rounded-xl border border-primary/30 bg-primary-soft/60 px-3 py-2">
                <Quote className="mt-0.5 size-3.5 shrink-0 text-primary" strokeWidth={2} aria-hidden />
                <div className="min-w-0 flex-1">
                  <span className="text-[11px] font-medium text-primary">引用追问</span>
                  <p className="mt-0.5 line-clamp-2 text-[12px] leading-4 text-ink-2">{quote.text}</p>
                </div>
                <button type="button" onClick={() => setQuote(null)}
                  className="shrink-0 cursor-pointer rounded p-0.5 text-faint hover:text-ink"
                  aria-label="取消引用">✕</button>
              </div>
            )}
            {running && (
              <div className="mb-1.5 flex items-center gap-2 rounded-xl border border-agent/25 bg-agent-soft/60 px-3 py-1.5">
                <Zap className="size-3.5 shrink-0 text-agent" strokeWidth={2.2} aria-hidden />
                <span className="text-[11px] leading-4 text-agent">运行中 · 现在发送的内容将作为插话注入，不打断当前任务</span>
                <button type="button"
                  onClick={() => void stop()}
                  className="ml-auto shrink-0 cursor-pointer rounded-full border border-agent/40 px-2.5 py-0.5 text-[11px] font-medium text-agent transition-colors hover:bg-agent hover:text-white">
                  停止
                </button>
              </div>
            )}
            <ComposerShell
              value={input}
              onChange={setInput}
              onSend={() => { if (running) { void steer(); } else { void send(); } }}
              placeholder={running ? "运行中插话 · 回车注入下一轮…" : "询问任何问题"}
              modeSwitch={false}
              model={model}
              onModelChange={setModel}
              replyMode={mode}
              onReplyModeChange={(value) => {
                if (value === "fast" || value === "deep" || value === "idea" || value === "doubt") setMode(value);
              }}
              webSearchSwitch={false}
              attachments={attachments}
              onAttachmentsChange={setAttachments}
              onWorkspaceFolder={(files) => void handleWorkspaceFolder(files)}
              selectedSkills={selectedSkills}
              onRemoveSkill={(name) => toggleSkill(name)}
              onSelectSkill={(name) => toggleSkill(name)}
              config={chatConfig}
              busy={uploading}
              disabled={loadingSession || !hydratedSessionId}
              hideStyleRow
              onStop={() => void stop()}
              skills={agentConfig.skills}
            />
            {steerError && <div className="mt-2 text-xs text-red-600 dark:text-red-400">{steerError}</div>}
            {runError && <div className="mt-2 text-xs text-red-600 dark:text-red-400">{runError}</div>}
          </div>
        </div>
      </div>
    </div>
    <ReportDialog
      open={openReport !== null}
      onClose={() => setOpenReport(null)}
      text={openReport?.text ?? ""}
      sources={openReport?.sources}
    />
  </AppShell>;
}
