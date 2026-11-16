"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  EXIT_OPTIONS,
  NODE_MAP,
  PIPELINE_NODES,
  type NodeStatus,
} from "@/features/auto-research/research-pipeline";
import {
  INITIAL_HEALTH,
  RUN_EVENTS,
  RUN_TASK,
  pseudoTime,
  type Artifact,
  type Checkpoint,
  type CheckpointOption,
  type HealthState,
  type LogLine,
} from "@/features/auto-research/research-run";

type RunArtifacts = Record<string, Artifact>;
import { FlowCanvas } from "./flow-canvas";
import { ActivityStream } from "./activity-stream";
import { CheckpointCard } from "./checkpoint-card";
import { NodeDetail } from "./node-detail";
import { ArtifactsPanel } from "./artifacts-panel";
import { HealthBar } from "./health-bar";
import { cn } from "@/lib/utils";

type RunState = "idle" | "running" | "waiting" | "paused" | "finished" | "ended";
type Autonomy = "guided" | "auto" | "attended";

const RUN_STATE_LABEL: Record<RunState, { text: string; className: string }> = {
  idle: { text: "未开始", className: "bg-chip text-muted" },
  running: { text: "运行中", className: "bg-primary-soft text-primary" },
  waiting: { text: "等待你的决策", className: "bg-[#d97706]/10 text-[#d97706]" },
  paused: { text: "已暂停", className: "bg-chip text-muted" },
  finished: { text: "已完成", className: "bg-success-soft text-success" },
  ended: { text: "已终止", className: "bg-danger-soft text-danger" },
};

const AUTONOMY_OPTIONS: { id: Autonomy; label: string; hint: string }[] = [
  { id: "guided", label: "引导", hint: "每个节点完成后都等你确认" },
  { id: "auto", label: "自动", hint: "非关键关卡自动继续,诚信门与评审仍等你" },
  { id: "attended", label: "值守", hint: "零交互长跑,决策记入日志事后审阅" },
];

const SPEEDS = [1, 4, 16] as const;

/** Auto Research 主面板 —— 预录事件流播放器 + 三栏交互 */
export function ResearchBoard() {
  const [runState, setRunState] = useState<RunState>("idle");
  const [autonomy, setAutonomy] = useState<Autonomy>("guided");
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(4);
  const [cursor, setCursor] = useState(0);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeStatus>>({});
  const [currentAction, setCurrentAction] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [artifacts, setArtifacts] = useState<RunArtifacts>({});
  const [health, setHealth] = useState<HealthState>(INITIAL_HEALTH);
  const [pending, setPending] = useState<Checkpoint | null>(null);
  const [pendingSlim, setPendingSlim] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>("topic");
  const [rightTab, setRightTab] = useState<"stream" | "detail">("stream");
  const [exitId, setExitId] = useState("record");
  const logSeq = useRef(0);

  const pushLog = useCallback(
    (nodeId: string, source: string, level: LogLine["level"], text: string, detail?: string) => {
      logSeq.current += 1;
      setLogs((prev) => [
        ...prev,
        { id: logSeq.current, time: pseudoTime(logSeq.current), nodeId, source, level, text, detail },
      ]);
      setCurrentAction((prev) => ({ ...prev, [nodeId]: text.slice(0, 14) }));
    },
    [],
  );

  /** 终止/完成:未到达的节点标记跳过 */
  const finishRun = useCallback(
    (state: "finished" | "ended", note: string) => {
      setNodeStatus((prev) => {
        const next = { ...prev };
        for (const n of PIPELINE_NODES) {
          const s = next[n.id];
          if (s !== "done" && s !== "skipped") next[n.id] = "skipped";
        }
        return next;
      });
      pushLog("record", "orchestrator", "decision", note);
      setRunState(state);
      setPending(null);
    },
    [pushLog],
  );

  /** 关卡分支处理;auto = 自动模式超时触发的继续 */
  const resolveOption = useCallback(
    (cp: Checkpoint, opt: CheckpointOption, auto = false) => {
      setPending(null);
      if (opt.action === "end") {
        if (opt.label === "暂停") {
          setRunState("paused");
          pushLog(cp.nodeId, "orchestrator", "decision", "你已暂停流水线,状态已保存,可随时恢复");
          return;
        }
        pushLog(cp.nodeId, "orchestrator", "decision", `你选择「${opt.label}」,任务终止`);
        finishRun("ended", "任务由用户裁决终止,产物与状态已归档");
        return;
      }
      if (opt.action === "skip-to" && opt.target) {
        const markerIdx = RUN_EVENTS.findIndex((e) => e.kind === "marker" && e.id === opt.target);
        if (markerIdx > cursor) {
          const skipped = new Set<string>();
          for (let i = cursor; i < markerIdx; i++) {
            const e = RUN_EVENTS[i];
            if ("nodeId" in e) skipped.add(e.nodeId);
          }
          skipped.delete(cp.nodeId);
          setNodeStatus((prev) => {
            const next = { ...prev, [cp.nodeId]: "done" as NodeStatus };
            skipped.forEach((id) => {
              if (next[id] !== "done") next[id] = "skipped";
            });
            return next;
          });
          pushLog(cp.nodeId, "orchestrator", "decision", `你选择「${opt.label}」:跳过修改返修回路,直达终审`);
          setCursor(markerIdx + 1);
          setRunState("running");
          return;
        }
      }
      setNodeStatus((prev) => ({ ...prev, [cp.nodeId]: "done" }));
      if (auto) {
        pushLog(cp.nodeId, "orchestrator", "decision", `自动模式:倒计时后继续「${opt.label}」,已记录不静默`);
      } else {
        pushLog(cp.nodeId, "you", "decision", `你确认:「${opt.label}」`);
      }
      setCursor((c) => c + 1);
      setRunState("running");
    },
    [cursor, finishRun, pushLog],
  );

  /** 事件应用 */
  const applyEvent = useCallback(
    (index: number) => {
      const ev = RUN_EVENTS[index];
      if (!ev) return;
      switch (ev.kind) {
        case "status": {
          setNodeStatus((prev) => {
            const next = { ...prev, [ev.nodeId]: ev.status };
            return next;
          });
          if (ev.status === "done") {
            setCurrentAction((prev) => {
              const next = { ...prev };
              delete next[ev.nodeId];
              return next;
            });
            if (ev.nodeId === exitId) {
              finishRun("finished", `到达你选择的终点输出「${NODE_MAP.get(exitId)?.label}」,任务完成`);
              return;
            }
          }
          setCursor(index + 1);
          break;
        }
        case "log":
          pushLog(ev.nodeId, ev.source, ev.level, ev.text, ev.detail);
          setCursor(index + 1);
          break;
        case "artifact":
          setArtifacts((prev) => ({ ...prev, [ev.artifact.id]: ev.artifact }));
          pushLog(ev.artifact.nodeId, "artifacts", "info", `交付产物:${ev.artifact.name}(${ev.artifact.version})`);
          setCursor(index + 1);
          break;
        case "metric":
          setHealth((prev) => ({ ...prev, ...ev.metric }));
          setCursor(index + 1);
          break;
        case "marker":
          setCursor(index + 1);
          break;
        case "checkpoint": {
          const cp = ev.checkpoint;
          if (autonomy === "attended") {
            pushLog(
              cp.nodeId,
              "orchestrator",
              "decision",
              `值守模式:自动选择「${cp.options[0].label}」,已记入待审决策`,
              `关卡「${cp.title}」按值守策略自动裁决,详情可在过程记录中审阅。`,
            );
            resolveOption(cp, cp.options[0]);
            return;
          }
          setNodeStatus((prev) => ({ ...prev, [cp.nodeId]: "waiting_user" }));
          setPending(cp);
          setPendingSlim(autonomy === "auto" && cp.level !== "mandatory");
          setRunState("waiting");
          break;
        }
      }
    },
    [autonomy, exitId, finishRun, pushLog, resolveOption],
  );

  /** 播放驱动 */
  useEffect(() => {
    if (runState !== "running" || pending) return;
    if (cursor >= RUN_EVENTS.length) {
      const done = setTimeout(() => finishRun("finished", "全部事件回放完毕,任务完成"), 0);
      return () => clearTimeout(done);
    }
    const prevAt = cursor > 0 ? RUN_EVENTS[cursor - 1].at : 0;
    const delay = Math.max(120, ((RUN_EVENTS[cursor].at - prevAt) * 1000) / speed);
    const timer = setTimeout(() => applyEvent(cursor), delay);
    return () => clearTimeout(timer);
  }, [runState, cursor, pending, speed, applyEvent, finishRun]);

  /** 重置并(可选)从入口节点开始 —— J2 中途进入 */
  const resetRun = useCallback(
    (entryId: string | null, autoStart: boolean) => {
      logSeq.current = 0;
      setLogs([]);
      setArtifacts({});
      setHealth(INITIAL_HEALTH);
      setPending(null);
      setCurrentAction({});
      const base: Record<string, NodeStatus> = {};
      PIPELINE_NODES.forEach((n) => (base[n.id] = "idle"));

      let startIdx = 0;
      if (entryId) {
        startIdx = RUN_EVENTS.findIndex((e) => "nodeId" in e && e.nodeId === entryId);
        if (startIdx < 0) startIdx = 0;
        // 静默回放上游事件:节点置 done、产物预填,不回放日志与关卡
        const preArtifacts: RunArtifacts = {};
        for (let i = 0; i < startIdx; i++) {
          const e = RUN_EVENTS[i];
          if (e.kind === "status") base[e.nodeId] = e.status;
          if (e.kind === "artifact") preArtifacts[e.artifact.id] = e.artifact;
        }
        setArtifacts(preArtifacts);
        const count = Object.keys(preArtifacts).length;
        if (count > 0) {
          logSeq.current += 1;
          setLogs([
            {
              id: 1,
              time: pseudoTime(1),
              nodeId: entryId,
              source: "orchestrator",
              level: "decision",
              text: `中途进入:已加载上游既有产物 ${count} 项,诚信核查门不因此跳过`,
            },
          ]);
        }
      }
      setNodeStatus(base);
      setCursor(startIdx);
      setRunState(autoStart ? "running" : "idle");
      setSelectedId(entryId);
      setRightTab("stream");
    },
    [],
  );

  const togglePlay = () => {
    if (runState === "running") setRunState("paused");
    else if (runState === "idle") resetRun(null, true);
    else if (runState === "paused") setRunState("running");
  };

  /** ?autostart=1&mode=auto|attended 自动开跑(演示与截图用) */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("mode");
    const autostart = params.get("autostart");
    if (!mode && !autostart) return;
    const t = setTimeout(() => {
      if (mode === "auto" || mode === "attended") setAutonomy(mode);
      if (autostart) resetRun(null, true);
    }, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const artifactList = useMemo(() => Object.values(artifacts), [artifacts]);
  const artifactCount = useMemo(() => {
    const map: Record<string, number> = {};
    artifactList.forEach((a) => {
      map[a.nodeId] = (map[a.nodeId] ?? 0) + 1;
    });
    return map;
  }, [artifactList]);

  const selectedNode = selectedId ? NODE_MAP.get(selectedId) : null;
  const stateMeta = RUN_STATE_LABEL[runState];
  const integrityPassed = {
    g1: nodeStatus.integrity1 === "done",
    g2: nodeStatus.integrity2 === "done",
  };
  /** 入口可用:运行未开始,或该节点尚未到达 */
  const canEnter = (nodeId: string) =>
    runState === "idle" || nodeStatus[nodeId] === "idle" || nodeStatus[nodeId] === "ready";

  return (
    <div className="space-y-4 p-4 lg:p-6">
      {/* 顶栏:任务 / 状态 / 自治度 / 终点 / 播放控制 */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-5 gap-y-3 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-[15px] font-semibold text-ink">{RUN_TASK.title}</h1>
              <span className={cn("shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium", stateMeta.className)}>
                {stateMeta.text}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-faint">
              Auto Research · {RUN_TASK.mode} · 开始于 {RUN_TASK.startedAt}
            </p>
          </div>

          <div className="flex items-center gap-1 rounded-xl bg-chip p-1" title="自治度档位">
            {AUTONOMY_OPTIONS.map((o) => (
              <button
                key={o.id}
                type="button"
                title={o.hint}
                onClick={() => setAutonomy(o.id)}
                className={cn(
                  "cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                  autonomy === o.id ? "bg-card text-ink shadow-card" : "text-muted hover:text-ink-2",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-1.5 text-xs text-muted">
            终点输出
            <select
              value={exitId}
              onChange={(e) => setExitId(e.target.value)}
              className="cursor-pointer rounded-lg border border-line bg-card px-2 py-1.5 text-xs text-ink-2"
            >
              {EXIT_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-xl bg-chip p-1">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSpeed(s)}
                  className={cn(
                    "cursor-pointer rounded-lg px-2 py-1 text-[11px] font-medium",
                    speed === s ? "bg-card text-ink shadow-card" : "text-muted",
                  )}
                >
                  {s}x
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={togglePlay}
              disabled={runState === "waiting" || runState === "finished" || runState === "ended"}
              className="flex cursor-pointer items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {runState === "running" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              {runState === "running"
                ? "暂停"
                : runState === "paused"
                  ? "继续"
                  : runState === "waiting"
                    ? "等待决策…"
                    : "开始运行"}
            </button>
            <button
              type="button"
              onClick={() => resetRun(null, false)}
              title="重置"
              className="cursor-pointer rounded-xl border border-line p-2 text-muted transition-colors hover:bg-panel"
            >
              <RotateCcw className="size-3.5" />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* 流程画布(主视图,整行) */}
      <Card>
        <CardHeader>
          <CardTitle>流程画布</CardTitle>
          <span className="ml-auto text-[11px] text-faint">16 节点 · 2 道诚信门 · 1 条评审回路</span>
        </CardHeader>
        <CardContent className="pt-2">
          <FlowCanvas
            status={nodeStatus}
            currentAction={currentAction}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setRightTab("detail");
            }}
            reviewRound={health.reviewRound}
            artifactCount={artifactCount}
          />
        </CardContent>
      </Card>

      {/* 执行面板 / 产物档案 */}
      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 lg:col-span-7">
          <CardHeader>
            <CardTitle>执行面板</CardTitle>
            <div className="ml-auto flex gap-1 text-[11px]">
              {(
                [
                  ["stream", "动作流"],
                  ["detail", "节点详情"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setRightTab(key)}
                  className={cn(
                    "cursor-pointer rounded-md px-2 py-1",
                    rightTab === key ? "bg-primary-soft text-primary" : "text-faint hover:text-ink-2",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="pt-2">
            {pending && (
              <CheckpointCard
                checkpoint={pending}
                slim={pendingSlim}
                autoContinueAfter={pendingSlim ? 3 : 0}
                onResolve={(opt) => resolveOption(pending, opt)}
              />
            )}
            {rightTab === "stream" ? (
              <ActivityStream logs={logs} />
            ) : selectedNode ? (
              <div className="scrollbar-subtle h-72 overflow-y-auto pr-1">
                <NodeDetail
                  node={selectedNode}
                  status={nodeStatus[selectedNode.id] ?? "idle"}
                  canEnter={canEnter(selectedNode.id)}
                  onEnter={(id) => resetRun(id, true)}
                />
              </div>
            ) : (
              <p className="flex h-72 items-center justify-center text-xs text-faint">
                在画布上点击一个节点查看详情
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="col-span-12 lg:col-span-5">
          <CardHeader>
            <CardTitle>产物档案</CardTitle>
            <span className="ml-auto text-[11px] text-faint">{artifactList.length} 项</span>
          </CardHeader>
          <CardContent className="pt-2">
            <ArtifactsPanel artifacts={artifactList} integrityPassed={integrityPassed} />
          </CardContent>
        </Card>
      </div>

      {/* 健康度底栏 */}
      <Card>
        <CardContent className="py-3.5">
          <HealthBar health={health} />
        </CardContent>
      </Card>
    </div>
  );
}
