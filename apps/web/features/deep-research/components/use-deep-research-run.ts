"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DR_RUN_TOTAL_MS,
  drEvents,
  drPlan,
  drReport,
} from "@/features/deep-research/data";
import type { DRStepEvent } from "@/types";

/** 计划节/报告节三态:待生成 → 生成中 → 已生成 */
export type DRSectionState = "todo" | "running" | "done";

export interface DeepResearchRun {
  phase: "running" | "done";
  elapsedMs: number;
  /** 已出现的步骤事件 */
  visibleEvents: DRStepEvent[];
  /** 各节状态(计划卡与报告节共用) */
  sectionState: Record<string, DRSectionState>;
  /** 来源墙可见条数 */
  visibleSources: number;
}

/**
 * 节状态派生:某节 write 事件出现 → 生成中;
 * 更靠后的节已开始、或运行结束 → 已生成;否则待生成。
 */
function deriveSectionState(
  visible: DRStepEvent[],
  done: boolean,
): Record<string, DRSectionState> {
  const started = new Set(
    visible
      .filter(
        (e): e is DRStepEvent & { sectionId: string } =>
          e.kind === "write" && !!e.sectionId,
      )
      .map((e) => e.sectionId),
  );
  const state: Record<string, DRSectionState> = {};
  drPlan.forEach((sec, i) => {
    if (!started.has(sec.id)) {
      state[sec.id] = "todo";
      return;
    }
    const laterStarted = drPlan.slice(i + 1).some((l) => started.has(l.id));
    state[sec.id] = laterStarted || done ? "done" : "running";
  });
  return state;
}

/**
 * Deep Research 运行播放器 —— 确定性预录事件流(无随机)
 * instant=true 直接落在完成态(历史记录 / headless 截图用),
 * 否则以 100ms tick 推进;组件卸载自动清理 interval。
 * 配合 key 重挂载实现「返回后再次开始 → 从头播放」。
 */
export function useDeepResearchRun(instant: boolean): DeepResearchRun {
  const [elapsedMs, setElapsedMs] = useState(() =>
    instant ? DR_RUN_TOTAL_MS : 0,
  );

  useEffect(() => {
    if (instant) return;
    const t0 = performance.now();
    const iv = window.setInterval(() => {
      setElapsedMs(Math.min(performance.now() - t0, DR_RUN_TOTAL_MS));
    }, 100);
    return () => window.clearInterval(iv);
  }, [instant]);

  const done = elapsedMs >= DR_RUN_TOTAL_MS;
  const visibleEvents = useMemo(
    () => drEvents.filter((e) => e.offsetMs <= elapsedMs),
    [elapsedMs],
  );
  const sectionState = useMemo(
    () => deriveSectionState(visibleEvents, done),
    [visibleEvents, done],
  );
  /** 来源墙:read 事件后全量;此前任一 search 事件后先出 8 条 */
  const visibleSources = useMemo(() => {
    if (visibleEvents.some((e) => e.kind === "read")) {
      return drReport.references.length;
    }
    return visibleEvents.some((e) => e.kind === "search") ? 8 : 0;
  }, [visibleEvents]);

  return {
    phase: done ? "done" : "running",
    elapsedMs,
    visibleEvents,
    sectionState,
    visibleSources,
  };
}
