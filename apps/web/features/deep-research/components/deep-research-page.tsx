"use client";

import { useState, useSyncExternalStore } from "react";
import { drReport } from "@/features/deep-research/data";
import { DeepResearchHome } from "./deep-research-home";
import { ResearchWorkbench } from "./research-workbench";

/**
 * Deep Research 页主体 —— 视图机:home(入口态)/ session(双栏工作台)
 * URL 参数(客户端解析,沿用 research-board 惯例,规避 useSearchParams 的 Suspense 约束):
 *   ?mode=instant  直接完成态(headless 截图稳定;与 autostart 并存时优先)
 *   ?autostart=1   进入 session 从头播放(演示)
 *   ?q=xxx         预填问题并进入 session 播放;空串则停留 home
 */
type PageState = {
  view: "home" | "session";
  question: string;
  instant: boolean;
};

const DEFAULT_PAGE_STATE: PageState = {
  view: "home",
  question: drReport.question,
  instant: false,
};

function getPageState(search: string): PageState {
  const params = new URLSearchParams(search);
  if (params.get("mode") === "instant") {
    return { ...DEFAULT_PAGE_STATE, view: "session", instant: true };
  }
  if (params.get("autostart") === "1") {
    return { ...DEFAULT_PAGE_STATE, view: "session" };
  }
  const q = params.get("q");
  if (q?.trim()) {
    return { view: "session", question: q, instant: false };
  }
  return DEFAULT_PAGE_STATE;
}

export function DeepResearchPageClient() {
  const search = useSyncExternalStore(
    () => () => undefined,
    () => window.location.search,
    () => "",
  );
  const urlState = getPageState(search);
  const [stateOverride, setStateOverride] = useState<PageState | null>(null);
  const { view, question, instant } = stateOverride ?? urlState;
  /** 每次进入 session 自增:重挂载工作台,运行从头播放 */
  const [sessionKey, setSessionKey] = useState(0);

  const startResearch = (q: string) => {
    setStateOverride({ view: "session", question: q, instant: false });
    setSessionKey((k) => k + 1);
  };

  const openHistory = () => {
    setStateOverride({
      view: "session",
      question: drReport.question,
      instant: true,
    });
    setSessionKey((k) => k + 1);
  };

  if (view === "home") {
    return (
      <DeepResearchHome onStart={startResearch} onOpenHistory={openHistory} />
    );
  }
  return (
    <ResearchWorkbench
      key={sessionKey}
      question={question}
      instant={instant}
      onBack={() => {
        setStateOverride({ view: "home", question, instant: false });
      }}
    />
  );
}
