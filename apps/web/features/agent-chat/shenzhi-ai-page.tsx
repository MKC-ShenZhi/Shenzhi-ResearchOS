"use client";

// ShenzhiAi 持久化对话页（ChatGPT 式排版）：
// 左：全局 AppSidebar 中的 Backend Agent 会话历史
// 中：用户右气泡 / 回答左通栏（头像 + 思考折叠 + 过程卡）/ 运行中插话右气泡
// 空状态：轻量提示并引导回深知 AI 新对话页（/agents）
// 下：居中悬浮 Composer；运行中发送 = 插话（steer，不打断当前工具批）
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, FileText, MessageCircleQuestion, Quote, Sparkles, Zap } from "lucide-react";

import {
  attachAgentSessionRun, createWorkspace, exportAgentSession, fetchAgentConfig, getAgentSession, steerAgentRun,
  stopAgentRun, streamAgentSessionRun, uploadWorkspaceFile,
  type AgentConfig, type AgentQuestionOption, type AgentRunInput,
  type AgentRunResult,
} from "@/clients/backend/agent";
import { ApiError } from "@/clients/backend/http";
import { ReportDialog } from "./report-dialog";
import { Timeline } from "./timeline-view";
import {
  applyDelta, applyToolCall, applyToolEnd, initialStreamState, isMeaningful, visibleNotes, startRunStream,
} from "./timeline";
import { ComposerShell, type ComposerSkill } from "@/components/common/composer/composer";
import type { WorkspaceFile } from "@/components/common/composer/attachment-menu";
import { AppShell } from "@/components/common/layout/app-shell";
import { useAuth } from "@/components/auth/auth-provider";
import { MarkdownRenderer } from "@/components/renderers/markdown-renderer";
import { StreamdownRenderer } from "./components/streamdown-renderer";
import { MessageRenderer } from "./components/message-renderer";
import { MessageActions } from "./components/message-actions";
import { MessageCopyButton } from "./components/message-copy-button";
import type { ComposerAttachment, ComposerConfig } from "@/types/ai-search";
import { takeAgentLaunch } from "./launch-store";
import { notifyAgentSessionsChanged } from "./session-events";
import { sessionExportMessages } from "./session-export";
import { storedTurns, type AgentChatTurn as Turn } from "./session-state";
import { applyMessageEvent, initialMessageState, reconcileMessage, startMessageRun } from "./message-state";

// 类型别名而非 interface：报告渲染器（ReportView）要的是带索引签名的 AgentSource，
// interface 不满足索引签名（TS2322），别名可以直接赋给它。
type Source = { title?: string; url?: string };

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

interface RunContext {
  sessionId: string;
  generation: number;
  assistantId: string;
}

function newTurnId(prefix: string) {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`;
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

const FALLBACK_CONFIG: AgentConfig = {
  models: [], default_model: "default", skills: [],
  upload: { max_size_mb: 0, max_files: 0, accept: [] },
};

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
  const { session, isPending } = useAuth();
  const identityKey = isPending ? null : (session?.user?.id ?? null);
  const sessionId = searchParams.get("session") ?? "";
  const launchId = searchParams.get("launch");
  const [agentConfig, setAgentConfig] = useState<AgentConfig>(FALLBACK_CONFIG);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionTitle, setSessionTitle] = useState("Agent 会话");
  const [hydratedSessionId, setHydratedSessionId] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [steerError, setSteerError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [workspace, setWorkspace] = useState<{ id: string; name: string; files: number } | null>(null);
  const [model, setModel] = useState("default");
  // 默认 fast。预算对齐 SZDR 的实测形态（15 分钟 / 120 次工具调用，见后端 policies.py）：
  // deadline 是上限不是目标，快问题照样快回；mode 只是资源倾向，不是方法论档位。
  const [mode, setMode] = useState<"fast" | "deep" | "idea" | "doubt">("fast");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
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
  const sessionGenerationRef = useRef(0);
  const pendingOperationRef = useRef<{
    sessionId: string; body: AgentRunInput; key: string; userId: string; assistantId: string;
  } | null>(null);
  // Render-visible mirror of the ref: the retry action must appear and disappear
  // with the pending operation, not only when another state change re-renders.
  const [pendingOperationSessionId, setPendingOperationSessionId] = useState<string | null>(null);
  const runContextRef = useRef<{
    sessionId: string;
    generation: number;
    assistantId: string;
    controller: AbortController;
  } | null>(null);

  useEffect(() => {
    fetchAgentConfig().then((config) => {
      setAgentConfig(config);
      setModel((current) => current === "default" ? config.default_model || "default" : current);
      setSelectedSkills((current) => current.map((selected) =>
        config.skills.find((skill) => skill.name === selected.name) ?? selected));
    }).catch(() => { /* 后端不可用时保持 fallback，发送时给出可读错误 */ });
  }, []);

  const patchAssistant = useCallback((context: {
    sessionId: string;
    generation: number;
    assistantId: string;
  }, patch: (turn: Turn) => Turn) => {
    const current = runContextRef.current;
    if (!current || current.sessionId !== context.sessionId
      || current.generation !== context.generation
      || context.generation !== sessionGenerationRef.current
      || current.assistantId !== context.assistantId) return;
    setTurns((previous) => {
      if (context.generation !== sessionGenerationRef.current) return previous;
      const index = previous.findIndex((turn) => turn.id === context.assistantId);
      if (index === -1) return previous;
      const next = [...previous];
      next[index] = patch(previous[index]);
      return next;
    });
  }, []);

  const isCurrentRun = useCallback((context: RunContext, controller: AbortController) => {
    const current = runContextRef.current;
    return current?.controller === controller
      && current.sessionId === context.sessionId
      && current.generation === context.generation
      && current.assistantId === context.assistantId
      && context.generation === sessionGenerationRef.current;
  }, []);

  const finishRun = useCallback((context: RunContext, controller: AbortController) => {
    if (!isCurrentRun(context, controller)) return;
    setRunning(false);
    setStopping(false);
    abortRef.current = null;
    runIdRef.current = null;
    runContextRef.current = null;
    notifyAgentSessionsChanged();
  }, [isCurrentRun]);

  const buildRunHandlers = useCallback((
    context: RunContext, controller: AbortController,
    onAccepted?: () => void, onCompleted?: () => void,
  ): Parameters<typeof streamAgentSessionRun>[2] => {
    const isCurrent = () => isCurrentRun(context, controller);
    return {
      onRunStart: (runId) => {
        onAccepted?.();
        if (isCurrent()) runIdRef.current = runId;
        patchAssistant(context, (turn) => ({ ...turn, content: "", reasoning: "",
          stream: startRunStream(turn.stream), structured: startMessageRun(turn.structured, runId) }));
      },
      onMessageEvent: (event) => patchAssistant(context, (turn) => ({
        ...turn, structured: applyMessageEvent(turn.structured, event),
      })),
      onDelta: (text, reasoning, turn) => patchAssistant(context, (current) => {
        // 状态机全在 timeline.ts（可测）。这里只负责把它与页面的 Turn 接起来。
        return {
          ...current,
          stream: applyDelta(current.stream, text, reasoning, turn),
          content: turn !== current.stream.turn ? text : current.content + text,
          reasoning: turn !== current.stream.turn ? reasoning : current.reasoning + reasoning,
        };
      }),
      onMeta: (data) => {
        if (data.warnings?.length) patchAssistant(context, (turn) => ({ ...turn, warnings: data.warnings }));
      },
      onMessage: (text, kind) => patchAssistant(context, (turn) => ({
        ...turn, steers: [...turn.steers, { text, kind }],
      })),
      onToolCall: (activity) => patchAssistant(context, (turn) => ({
        ...turn,
        stream: applyToolCall(turn.stream, activity),
      })),
      onToolEnd: (toolCallId, isError, durationMs, summary, cancelled) => patchAssistant(context, (turn) => ({
        ...turn,
        // 回填到同一个工具对象：工具行据此从"转圈"变"完成"
        stream: applyToolEnd(turn.stream, toolCallId, { done: true, isError, durationMs, summary, cancelled }),
      })),
      onResult: (result: AgentRunResult) => {
        if (!isCurrent()) return;
        setStopping(false);
        onCompleted?.();
        patchAssistant(context, (turn) => {
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
            status: result.status,
            structured: reconcileMessage(turn.structured, result.message, true),
            // The persisted final_text is authoritative, including failure/timeout partials.
            content: result.question ? "" : result.final_text || "",
          };
        });
      },
    };
  }, [isCurrentRun, patchAssistant]);

  useEffect(() => {
    if (isPending) return;
    if (!sessionId) {
      router.replace("/agents");
      return;
    }
    const generation = sessionGenerationRef.current + 1;
    sessionGenerationRef.current = generation;
    const previousRun = runContextRef.current;
    if (previousRun) {
      previousRun.controller.abort();
      runContextRef.current = null;
    }
    if (loadedSessionRef.current && loadedSessionRef.current !== sessionId) {
      abortRef.current?.abort();
    }
    runIdRef.current = null;
    abortRef.current = null;
    loadedSessionRef.current = sessionId;
    let active = true;
    queueMicrotask(() => {
      if (!active || generation !== sessionGenerationRef.current) return;
      setRunning(false);
      setLoadingSession(true);
      setHydratedSessionId(null);
      setRunError(null);
      setStopping(false);
      setNeedsRefresh(false);
      setOpenReport(null);
      setQuote(null);
      setTurns([]);
      setWorkspace(null);
      setAttachments([]);
      setSelectedSkills([]);
      void getAgentSession(sessionId).then((session) => {
        if (!active || generation !== sessionGenerationRef.current) return;
        setSessionTitle(session.title);
        const restored = storedTurns(session.turns);
        const lastTurn = session.turns.at(-1);
        if (lastTurn?.status !== "running") {
          pendingOperationRef.current = null;
          setPendingOperationSessionId(null);
        }
        if (lastTurn?.status === "running") {
          const assistant = restored.at(-1)!;
          Object.assign(assistant, {
            stream: initialStreamState(), content: "", reasoning: "", steers: [], structured: initialMessageState(),
          });
        }
        setTurns(restored);
        const settings = session.settings ?? {};
        setModel(settings.model || "default");
        if (settings.mode) setMode(settings.mode);
        // Session settings describe past turns; sent files must not reappear in the composer.
        setAttachments([]);
        setSelectedSkills((settings.skills ?? []).map((name) => ({ name, description: "" })));
        setWorkspace(settings.workspace_id
          ? { id: settings.workspace_id, name: "会话工作区", files: 0 } : null);
        setHydratedSessionId(session.id);
        if (lastTurn?.status === "running") {
          const controller = new AbortController();
          const context = { sessionId, generation, assistantId: `${lastTurn.id}:assistant` };
          setRunning(true);
          abortRef.current = controller;
          runIdRef.current = null;
          runContextRef.current = { ...context, controller };
          void attachAgentSessionRun(sessionId, buildRunHandlers(context, controller), controller.signal)
            .catch(async (cause: unknown) => {
              if (!active || !isCurrentRun(context, controller) || controller.signal.aborted) return;
              setNeedsRefresh(true);
              if (cause instanceof ApiError && cause.status === 404) {
                // One refresh only; the service reconciles orphan turns before returning.
                const refreshed = await getAgentSession(sessionId);
                if (active && isCurrentRun(context, controller) && !controller.signal.aborted) {
                  setTurns(storedTurns(refreshed.turns));
                  if (refreshed.turns.at(-1)?.status === "running") {
                    setRunError("任务仍在其他工作进程运行，当前连接无法接续；稍后重新打开会话查看结果。");
                  } else {
                    setNeedsRefresh(false);
                  }
                }
              } else if (!(cause instanceof Error && cause.name === "AbortError")) {
                setRunError(cause instanceof Error ? cause.message : "续接失败，请稍后重试");
              }
            })
            .catch((cause: unknown) => {
              if (active && isCurrentRun(context, controller) && !controller.signal.aborted) {
                setRunError(cause instanceof Error ? cause.message : "会话刷新失败，请稍后重试");
              }
            })
            .finally(() => finishRun(context, controller));
        }
      }).catch((cause) => {
        if (!active || generation !== sessionGenerationRef.current) return;
        setRunError(cause instanceof Error ? cause.message : "会话不存在或无权访问");
      }).finally(() => {
        if (active && generation === sessionGenerationRef.current) setLoadingSession(false);
      });
    });
    return () => {
      active = false;
      abortRef.current?.abort();
      runContextRef.current = null;
      abortRef.current = null;
      runIdRef.current = null;
    };
  }, [identityKey, isPending, sessionId, router, buildRunHandlers, finishRun, isCurrentRun, refreshVersion]);

  useEffect(() => {
    if (stickRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [turns]);

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
  const runPrompt = useCallback(async (runInput: AgentRunInput, retryOperationKey?: string) => {
    const prompt = runInput.prompt.trim();
    if (!prompt || running || !sessionId || (needsRefresh && !retryOperationKey)) return;
    const requestBody = { ...runInput, prompt };
    const idempotencyKey = retryOperationKey ?? newTurnId("operation");
    const retry = retryOperationKey && pendingOperationRef.current?.key === retryOperationKey
      ? pendingOperationRef.current
      : null;
    const generation = sessionGenerationRef.current;
    const userId = retry?.userId ?? newTurnId("user");
    const assistantId = retry?.assistantId ?? newTurnId("assistant");
    pendingOperationRef.current = { sessionId, body: requestBody, key: idempotencyKey, userId, assistantId };
    setPendingOperationSessionId(sessionId);
    const context = { sessionId, generation, assistantId };
    const userTurn: Turn = {
      id: userId, role: "user", content: prompt, attachments: runInput.attachments as ComposerAttachment[],
      reasoning: "", stream: initialStreamState(), structured: initialMessageState(), steers: [],
    };
    const assistantTurn: Turn = {
      id: assistantId, role: "assistant", content: "", reasoning: "", stream: initialStreamState(), structured: initialMessageState(), steers: [], status: "running",
    };
    setTurns((previous) => {
      if (retry && previous.some((turn) => turn.id === userId)
          && previous.some((turn) => turn.id === assistantId)) {
        return previous.map((turn) => turn.id === assistantId ? assistantTurn : turn);
      }
      return [...previous.filter((turn) => turn.id !== userId && turn.id !== assistantId), userTurn, assistantTurn];
    });
    setInput("");
    setAttachments([]);
    setRunError(null);
    setNeedsRefresh(false);
    setSteerError(null);
    setRunning(true);
    runIdRef.current = null;
    const controller = new AbortController();
    abortRef.current = controller;
    runContextRef.current = { ...context, controller };
    const isCurrent = () => isCurrentRun(context, controller);
    let accepted = false;
    try {
      await streamAgentSessionRun(
        sessionId, requestBody,
        buildRunHandlers(context, controller, () => {
          accepted = true;
        }, () => {
          if (pendingOperationRef.current?.key === idempotencyKey) {
            pendingOperationRef.current = null;
            setPendingOperationSessionId(null);
          }
        }),
        idempotencyKey, controller.signal,
      );
    } catch (error) {
      if (!accepted && isCurrent()) {
        setTurns((previous) => previous.filter((turn) => turn.id !== userId && turn.id !== assistantId));
        setInput(prompt);
        setAttachments(runInput.attachments as ComposerAttachment[]);
      }
      if (!controller.signal.aborted && (error as Error).name !== "AbortError" && isCurrent()) {
        // A lost response can hide an accepted Task; only a same-key retry is safe.
        setNeedsRefresh(true);
        setRunError(error instanceof ApiError && error.status === 409
          ? "该会话已有正在运行的任务，当前连接无法实时续接。稍后重新打开会话查看结果；再次重试会沿用本次操作标识。"
          : (error as Error).message || "连接失败，请稍后重试");
      }
    } finally {
      finishRun(context, controller);
    }
  }, [running, sessionId, needsRefresh, buildRunHandlers, finishRun, isCurrentRun]);

  const retryPendingOperation = useCallback(() => {
    const operation = pendingOperationRef.current;
    if (operation?.sessionId === sessionId) {
      void runPrompt(operation.body, operation.key);
    }
  }, [runPrompt, sessionId]);

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
    if (stopping) return;
    const runId = runIdRef.current;
    if (!runId) {
      setNeedsRefresh(true);
      setRunError("提交状态待确认，请重新连接或刷新结果后继续操作。");
      abortRef.current?.abort();
      return;
    }
    setStopping(true);
    try {
      await stopAgentRun(runId);
    } catch (error) {
      if (runIdRef.current !== runId) return;
      setStopping(false);
      setRunError(error instanceof Error ? error.message : "停止失败，请重试");
    }
  }, [stopping]);

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
      const messages = sessionExportMessages(turns);
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

  const composerConfig: ComposerConfig = {
    models: agentConfig.models,
    default_model: agentConfig.default_model,
    modes: ["fast", "deep", "idea", "doubt"],
    quota: { used: 0, limit: 0, deep_used: 0, deep_limit: 0 },
    quota_enforced: false,
    upload: agentConfig.upload,
  };


  return <AppShell>
    <div className="app-workspace-height flex min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3 sm:px-6">
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
        {agentConfig.models.some((item) => item.value === "demo/m1") && (
          <p role="status" className="px-4 py-2 text-sm text-amber-700 dark:text-amber-400">Mock 演示：受控模拟执行，不调用真实模型或检索服务。</p>
        )}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto"
          onMouseUp={captureQuote}
          onScroll={(event) => {
            const el = event.currentTarget;
            stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}>
          {/* 宽度按可用空间走，不再死卡 768px 居中：宽屏下左右两侧会留下大片死空白
              （用户反馈"死空白太多"）。上限放宽到 1100px 只防止超宽屏上单行过长难以阅读。 */}
          <div className="mx-auto w-full max-w-[1100px] px-4 pt-6 sm:px-6 sm:pt-8">
            {turns.length === 0 && !running && (
              <div className="mt-24 mb-16 text-center">
                <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary" aria-hidden>
                  <Sparkles className="size-6" strokeWidth={2} />
                </div>
                <p className="text-sm text-muted">
                  {loadingSession ? "正在加载会话…" : runError ? "无法打开这个会话" : "这个会话还没有消息"}
                </p>
                {!loadingSession && (
                  <button type="button" onClick={() => router.push("/agents")}
                    className="mt-4 cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-deep">
                    开始新对话
                  </button>
                )}
              </div>
            )}
            {turns.map((turn, index) => turn.role === "user"
              ? <div key={turn.id} className="mb-6 flex flex-col items-end">
                  <div className="min-w-0 max-w-[90%] break-words sm:max-w-[75%] rounded-3xl bg-chip px-4 py-2.5 text-[15px] leading-7 text-ink">
                    <MarkdownRenderer content={turn.content}
                      className="[&>:first-child]:mt-0 [&>:last-child]:mb-0 [&_p]:whitespace-pre-wrap" />
                    {!!turn.attachments?.length && <div className="mt-2 flex flex-wrap gap-1.5">
                      {turn.attachments.map((attachment, attachmentIndex) => <span key={`${turn.id}:attachment:${attachmentIndex}`} className="inline-flex max-w-full items-center gap-1 rounded-lg bg-card px-2 py-1 text-xs text-muted" title={attachment.title ?? undefined}><FileText className="size-3.5 shrink-0" /><span className="truncate">{attachment.title || "附件"}</span></span>)}
                    </div>}
                  </div>
                  {turn.content.trim() && <div className="mt-1 flex items-center gap-1">
                    <MessageCopyButton text={turn.content} label="复制提问" />
                  </div>}
                </div>
              : <div key={turn.id} className="mb-8">
                  {!turn.structured.message && <p role="status" className="mb-2 text-xs text-muted">{turn.status === "running"
                    ? running && index === turns.length - 1 ? "任务执行中…" : "执行状态待同步，请刷新结果"
                    : ({ done: "已完成", failed: "执行失败", timeout: "执行超时", stopped: "已停止", awaiting_input: "等待你的回答" }[turn.status ?? "done"])}</p>}
                  {/* 过程流：思考 / 正文 / 工具按到达顺序交错（pi 的结构）。空时不渲染任何盒子。 */}
                  <Timeline state={turn.stream} live={running && index === turns.length - 1} includeText={!turn.structured.message} />
                  {visibleNotes(turn.steers).map((note, noteIndex) => (
                    <div key={noteIndex} className="mb-3 flex items-center justify-end gap-1.5">
                      <span className="rounded-full bg-agent-soft px-2 py-0.5 text-[10px] font-medium text-agent">
                        {note.kind === "steer" ? "⚡ 插话"
                        : "→ 追问"}
                      </span>
                      <div className="max-w-[70%] rounded-2xl rounded-br-md border border-agent/30 bg-agent-soft px-3.5 py-2 text-[14px] leading-6 text-ink">
                        {note.text}
                      </div>
                    </div>
                  ))}
                  {turn.warnings?.length ? (
                    <div className="mb-2 text-xs text-amber-600 dark:text-amber-400">⚠ {turn.warnings.join("；")}</div>
                  ) : null}
                  {(turn.structured.message || isMeaningful(turn.reasoning) || isMeaningful(turn.content)
                    || turn.report || turn.question || turn.error || turn.stopped) && (
                  <div className="flex gap-3">
                    <AssistantAvatar />
                    <div className="min-w-0 flex-1" data-quote-source>
                      {/* 只有标点的正文不渲染：模型常在工具轮之间吐孤立的 "."。 */}
                      {turn.structured.message ? (
                        <MessageRenderer message={turn.structured.message}
                          activeBlockId={turn.structured.activeBlockId}
                          isStreaming={running && index === turns.length - 1} />
                      ) : turn.content && isMeaningful(turn.content) && (
                        <StreamdownRenderer content={turn.content} isStreaming={running && index === turns.length - 1} />
                      )}
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
                      {!turn.structured.message && turn.sources && !turn.report && <Sources sources={turn.sources} />}
                      {turn.error && <div className="mt-1 text-sm text-red-600 dark:text-red-400">{turn.error}</div>}
                      {turn.stopped && (
                        <div className="mt-1 text-xs text-muted">{stopLabel(turn.stopReason)}</div>
                      )}
                      <MessageActions message={turn.structured.message} content={turn.content}
                        status={turn.status} isStreaming={running && index === turns.length - 1} />
                    </div>
                  </div>)}
                </div>)}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="shrink-0 px-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6">
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
                <span className="text-[11px] leading-4 text-agent">{stopping ? "正在停止…" : "运行中 · 现在发送的内容将作为插话注入，不打断当前任务"}</span>
                <button type="button"
                  disabled={stopping}
                  onClick={() => void stop()}
                  className="ml-auto shrink-0 cursor-pointer rounded-full border border-agent/40 px-2.5 py-0.5 text-[11px] font-medium text-agent transition-colors hover:bg-agent hover:text-white">
                  {stopping ? "正在停止…" : "停止"}
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
              config={composerConfig}
              busy={uploading}
              disabled={loadingSession || !hydratedSessionId || needsRefresh}
              hideStyleRow
              onStop={() => void stop()}
              skills={agentConfig.skills}
            />
            {steerError && <div className="mt-2 text-xs text-red-600 dark:text-red-400">{steerError}</div>}
            {runError && <div role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">{runError}</div>}
            {!running && <button type="button" disabled={loadingSession} onClick={() => setRefreshVersion((value) => value + 1)}
              className="mt-2 mr-4 cursor-pointer text-xs text-primary hover:underline">重新连接 / 刷新结果</button>}
            {!running && pendingOperationSessionId === sessionId && (
              <button type="button" onClick={retryPendingOperation}
                className="mt-2 cursor-pointer text-xs text-primary hover:underline">
                重试上次提交
              </button>
            )}
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
