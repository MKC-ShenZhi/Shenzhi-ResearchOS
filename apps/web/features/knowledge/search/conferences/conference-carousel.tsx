"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronRight, Pause, Play } from "lucide-react";
import type { KnowledgeConference } from "@/clients/knowledge";
import { buildConferenceBatches, CONFERENCE_ROTATION_MS, CONFERENCE_SELECTION_FEEDBACK_MS } from "./conference-state";

function subscribeVisibility(listener: () => void) {
  document.addEventListener("visibilitychange", listener);
  return () => document.removeEventListener("visibilitychange", listener);
}
const pageIsHidden = () => document.hidden;
const serverIsHidden = () => false;

/** Candidate rotation owns no selected conference, URL or paper query state. */
export function ConferenceCarousel({ items, onSelect }: {
  items: KnowledgeConference[];
  onSelect: (conference: KnowledgeConference) => void;
}) {
  const batches = useMemo(() => buildConferenceBatches(items), [items]);
  const [batchIndex, setBatchIndex] = useState(0);
  const [userPaused, setUserPaused] = useState(false);
  const [pointerInside, setPointerInside] = useState(false);
  const [focusInside, setFocusInside] = useState(false);
  const [feedback, setFeedback] = useState<{ key: string } | null>(null);
  const hidden = useSyncExternalStore(subscribeVisibility, pageIsHidden, serverIsHidden);
  const reducedMotion = useReducedMotion();
  const count = batches.length;
  const currentIndex = batchIndex % Math.max(1, count);
  const paused = userPaused || pointerInside || focusInside || hidden;

  useEffect(() => {
    if (paused || count < 2) return;
    const timer = window.setTimeout(() => setBatchIndex((index) => (index + 1) % count), CONFERENCE_ROTATION_MS);
    return () => window.clearTimeout(timer);
  }, [paused, count, batchIndex]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), CONFERENCE_SELECTION_FEEDBACK_MS);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  return <div role="region" aria-label="会议候选" aria-roledescription="轮播" className="min-w-0"
    onPointerEnter={(event) => { if (event.pointerType !== "touch") setPointerInside(true); }}
    onPointerLeave={() => setPointerInside(false)}
    onFocusCapture={(event) => setFocusInside(event.target.matches(":focus-visible"))}
    onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setFocusInside(false); }}>
    <div className="relative min-h-64 overflow-hidden sm:min-h-[168px]" aria-live="off">
      <AnimatePresence initial={false} mode="wait">
        <motion.div key={currentIndex} className="grid auto-rows-[80px] grid-cols-2 gap-2 sm:grid-cols-3"
          initial={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : -24 }}
          transition={{ duration: reducedMotion ? 0 : 0.3, ease: [0.22, 1, 0.36, 1] }}>
          {(batches[currentIndex] ?? []).map(({ conference, key }) => <button key={key} type="button"
            aria-label={`选择会议 ${conference.name}`} title={conference.name}
            data-selection-feedback={feedback?.key === key ? "true" : undefined}
            onClick={() => { setFeedback({ key }); onSelect(conference); }}
            className={`min-w-0 rounded-xl border px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${feedback?.key === key ? "border-primary bg-primary-soft ring-2 ring-primary/15" : "border-line bg-card hover:border-primary/50"}`}>
            <span className="block truncate text-sm font-semibold text-ink">{conference.name}</span>
            <span className="mt-1 block text-[11px] leading-relaxed text-muted">{conference.paperCount.toLocaleString()} 篇 · {conference.yearCount} 个年份</span>
          </button>)}
        </motion.div>
      </AnimatePresence>
      {count === 0 && <p className="p-4 text-xs text-muted">暂无可浏览会议</p>}
    </div>
    <div className="mt-2 flex min-h-7 flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span title={userPaused ? "已手动暂停" : paused ? "移出鼠标或结束键盘操作后，重新计时 15 秒" : "每 15 秒自动轮换一批，不改变当前会议"}>{count > 1 ? `第 ${currentIndex + 1} / ${count} 批 · ${paused ? "已暂停" : "15 秒换一批"}` : `共 ${batches[0]?.length ?? 0} 个可浏览会议`}</span>
      {count > 1 && <div className="flex items-center gap-1">
        <button type="button" aria-label={userPaused ? "恢复自动轮换" : "暂停自动轮换"} aria-pressed={userPaused}
          onClick={() => setUserPaused((value) => !value)}
          className="flex min-h-7 items-center gap-1 rounded-md px-2 hover:bg-panel hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
          {userPaused ? <Play className="size-3" /> : <Pause className="size-3" />}{userPaused ? "继续" : "暂停"}
        </button>
        <button type="button" aria-label="下一批会议" onClick={() => setBatchIndex((index) => (index + 1) % count)}
          className="flex min-h-7 items-center gap-1 rounded-md px-2 text-primary hover:bg-primary-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
          换一批 <ChevronRight className="size-3" />
        </button>
      </div>}
    </div>
  </div>;
}
