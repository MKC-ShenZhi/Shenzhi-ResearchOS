"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { streamAgentRun } from "@/clients/backend/agent";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { isAbortError, requestIdForApiError } from "@/clients/backend/http";
import {
  initialPaperAgentState,
  paperAgentReducer,
  paperAgentRunRequest,
  pendingPaperAgentRetry,
  type PendingPaperAgentRun,
} from "./paper-agent";

export function usePaperAgent(paper: Pick<KnowledgePaperDetail, "id" | "title">) {
  const [state, dispatch] = useReducer(paperAgentReducer, paper.id, initialPaperAgentState);
  const abortRef = useRef<AbortController | null>(null);
  const sendLockedRef = useRef(false);
  const sequenceRef = useRef(0);
  const pendingRunsRef = useRef(new Map<string, PendingPaperAgentRun>());

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    sendLockedRef.current = false;
    pendingRunsRef.current.clear();
    dispatch({ type: "reset", paperId: paper.id });
    return () => abortRef.current?.abort();
  }, [paper.id]);

  const send = useCallback(async (rawQuestion: string) => {
    const question = rawQuestion.trim();
    if (!question || state.running || sendLockedRef.current) return;

    sendLockedRef.current = true;
    const sequence = ++sequenceRef.current;
    const userId = `paper-user-${sequence}`;
    const assistantId = `paper-assistant-${sequence}`;
    const controller = new AbortController();
    const readingCalls = new Set<string>();
    let receivedResult = false;
    const retry = pendingPaperAgentRetry(pendingRunsRef.current, question);
    const operation = retry ?? {
      question,
      request: paperAgentRunRequest(paper, question, state.turns),
      idempotencyKey: crypto.randomUUID(),
    };
    pendingRunsRef.current.set(question, operation);
    abortRef.current = controller;
    dispatch({ type: "start", question, userId, assistantId });

    try {
      await streamAgentRun(operation.request, {
        onDelta: (text, _reasoning, turn) => {
          dispatch({ type: "delta", assistantId, text, turn });
        },
        onMeta: ({ warnings = [] }) => {
          if (warnings.length) dispatch({ type: "meta", assistantId, warnings });
        },
        onToolCall: (activity) => {
          if (activity.name !== "read_paper") return;
          readingCalls.add(activity.toolCallId);
          dispatch({ type: "read_paper_start" });
        },
        onToolEnd: (toolCallId, failed) => {
          if (!readingCalls.delete(toolCallId)) return;
          dispatch({
            type: "read_paper_end",
            assistantId,
            failed,
            stillReading: readingCalls.size > 0,
          });
        },
        onResult: (result) => {
          receivedResult = true;
          if (pendingRunsRef.current.get(question) === operation) pendingRunsRef.current.delete(question);
          dispatch({ type: "result", assistantId, result });
        },
      }, controller.signal, operation.idempotencyKey);
      if (!receivedResult) {
        dispatch({ type: "failure", assistantId, message: "Agent 未返回运行结果，请重试", aborted: false });
      }
    } catch (error) {
      dispatch({
        type: "failure",
        assistantId,
        message: error instanceof Error ? error.message : undefined,
        requestId: requestIdForApiError(error),
        aborted: isAbortError(error),
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      sendLockedRef.current = false;
    }
  }, [paper, state.running, state.turns]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { ...state, send, stop };
}
