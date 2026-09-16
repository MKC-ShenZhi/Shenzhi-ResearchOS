/**
 * Auto Research 预录运行脚本 —— 确定性事件流(原型无后端,刻意不用随机)
 * 覆盖用户旅程 J1:全新课题全流程,含 1 轮评审回路、1 次停滞自愈、G1/G2 双诚信门
 */
import type { NodeStatus } from "./research-pipeline";

export type LogLevel = "info" | "decision" | "warn" | "error";

export interface LogLine {
  id: number;
  time: string;
  nodeId: string;
  source: string;
  level: LogLevel;
  text: string;
  detail?: string;
}

export interface Artifact {
  id: string;
  nodeId: string;
  name: string;
  kind: "json" | "xlsx" | "md" | "docx" | "pdf" | "tex" | "pptx" | "script" | "figure";
  version: string;
  hash: string;
}

export interface CheckpointMetric {
  label: string;
  value: string;
  state?: "ok" | "warn" | "bad";
}

export interface CheckpointOption {
  label: string;
  hint?: string;
  tone?: "primary" | "danger" | "ghost";
  action: "continue" | "skip-to" | "end";
  /** skip-to 目标事件标记 */
  target?: string;
}

export interface Checkpoint {
  id: string;
  nodeId: string;
  /** mandatory = 诚信门/评审决定,永远完整呈现且不可自动继续 */
  level: "full" | "mandatory";
  title: string;
  metrics?: CheckpointMetric[];
  deliverables?: string[];
  flagged?: string[];
  question: string;
  options: CheckpointOption[];
}

export interface HealthState {
  iteration: number;
  newFindings: number;
  staleCount: number;
  directions: string[];
  nextDirection: string | null;
  watchdog: { l0: "ok" | "recovered"; l1: "ok" | "recovered"; l2: "ok" | "recovered" };
  tokensUsed: number;
  tokensBudget: number;
  roundsUsed: number;
  roundsBudget: number;
  reviewRound: number;
}

export type RunEvent =
  | { at: number; kind: "status"; nodeId: string; status: NodeStatus }
  | { at: number; kind: "log"; nodeId: string; source: string; level: LogLevel; text: string; detail?: string }
  | { at: number; kind: "artifact"; artifact: Artifact }
  | { at: number; kind: "checkpoint"; checkpoint: Checkpoint }
  | { at: number; kind: "metric"; metric: Partial<HealthState> }
  | { at: number; kind: "marker"; id: string };

export const RUN_TASK = {
  title: "扩散模型在机器人策略学习中的工业部署瓶颈",
  startedAt: "2026-08-07 09:30",
  mode: "全流程 · 从选题到过程记录",
};

export const INITIAL_HEALTH: HealthState = {
  iteration: 0,
  newFindings: 0,
  staleCount: 0,
  directions: [],
  nextDirection: null,
  watchdog: { l0: "ok", l1: "ok", l2: "ok" },
  tokensUsed: 0,
  tokensBudget: 850000,
  roundsUsed: 0,
  roundsBudget: 24,
  reviewRound: 0,
};

let seq = 0;
const at = () => (seq += 1.5);

/** 预录事件流(1x 速度约 3 分钟跑完) */
export const RUN_EVENTS: RunEvent[] = [
  // ── ① 选题验证 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "topic", status: "running" },
  { at: at(), kind: "log", nodeId: "topic", source: "orchestrator", level: "info", text: "任务初始化,状态已落盘 state/task_spec.md" },
  { at: at(), kind: "log", nodeId: "topic", source: "topic_agent", level: "info", text: "界定候选研究空白:拆解为 3 个精确研究问题与检索概念" },
  { at: at(), kind: "log", nodeId: "topic", source: "topic_agent", level: "info", text: "检索最相近已有工作:完全重合 0 · 相邻 4 · 里程碑 2 · 综述 3" },
  { at: at(), kind: "log", nodeId: "topic", source: "refuter ×2", level: "info", text: "并行反向求证:主动寻找会占据/削弱每个候选方向的证据" },
  { at: at(), kind: "log", nodeId: "topic", source: "refuter-2", level: "warn", text: "候选 B「仿真到真机迁移」发现 2025 年强基线占据核心claim", detail: "Zhao et al. 2025 (RSS) 已覆盖 sim-to-real 延迟补偿主线,候选 B 降级为相邻工作。" },
  { at: at(), kind: "log", nodeId: "topic", source: "topic_agent", level: "decision", text: "三关卡评分:开放性 4/5 · 贡献类型 4/5 · 可行性 3/5", detail: "结论由分数推导:有条件可以做。第三关仅依据你提供的资源条件打分——GPU 算力与真机平台是你的约束项。" },
  { at: at(), kind: "metric", metric: { iteration: 3, newFindings: 5, tokensUsed: 62000, directions: ["工业部署延迟瓶颈", "仿真到真机迁移(已排除)"], nextDirection: null } },
  { at: at(), kind: "artifact", artifact: { id: "a-topic", nodeId: "topic", name: "研究空白决策档案.md", kind: "md", version: "v1", hash: "9f2c7a" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-topic",
      nodeId: "topic",
      level: "full",
      title: "① 选题验证完成 —— 确认研究方向",
      metrics: [
        { label: "开放性", value: "4 / 5", state: "ok" },
        { label: "贡献类型", value: "4 / 5", state: "ok" },
        { label: "可行性", value: "3 / 5", state: "warn" },
      ],
      deliverables: ["研究空白决策档案.md"],
      flagged: ["候选 B 已被 2025 年强基线部分占据,已从主线排除"],
      question: "结论:有条件可以做。是否以「工业部署延迟瓶颈」为研究方向继续?",
      options: [
        { label: "确认方向,继续", tone: "primary", action: "continue" },
        { label: "调整方向后重评", tone: "ghost", action: "continue", hint: "原型中按继续处理" },
      ],
    },
  },

  // ── ② 文献检索 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "topic", status: "done" },
  { at: at(), kind: "status", nodeId: "search", status: "running" },
  { at: at(), kind: "log", nodeId: "search", source: "search_agent", level: "info", text: "检索路由:英文/国际主题 → OpenAlex 为主,中文补充走万方" },
  { at: at(), kind: "log", nodeId: "search", source: "search_agent", level: "info", text: "OpenAlex 翻页 3/5:命中 214 条(配额 60/100/300 分级内)" },
  { at: at(), kind: "log", nodeId: "search", source: "venue_tagger", level: "info", text: "附加期刊质量标签:IF · JCR · CAS · CCF · EI · 中文核心" },
  { at: at(), kind: "log", nodeId: "search", source: "citation_verifier", level: "info", text: "引文批量核验(每 20 条一批,不攒批):第 1-3 批全部通过" },
  { at: at(), kind: "metric", metric: { iteration: 4, newFindings: 9, tokensUsed: 118000, roundsUsed: 4 } },
  { at: at(), kind: "artifact", artifact: { id: "a-pool-json", nodeId: "search", name: "candidate-paper-pool.json", kind: "json", version: "v1", hash: "41be02" } },
  { at: at(), kind: "artifact", artifact: { id: "a-pool-xlsx", nodeId: "search", name: "candidate-paper-pool.xlsx", kind: "xlsx", version: "v1", hash: "77d1c9" } },
  { at: at(), kind: "status", nodeId: "search", status: "done" },

  // ── ③ 初筛分级 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "screen", status: "running" },
  { at: at(), kind: "log", nodeId: "screen", source: "screen_agent", level: "info", text: "规范化论文池:合并重复条目 214 → 168,补全元数据" },
  { at: at(), kind: "log", nodeId: "screen", source: "screen_agent", level: "info", text: "按标题/摘要标准初筛,逐条记录纳入/排除理由:纳入 46 · 排除 122" },
  { at: at(), kind: "log", nodeId: "screen", source: "screen_agent", level: "warn", text: "本轮 0 篇与「真机延迟」直接相关,停滞计数 +1", detail: "stale_count = 1。若再次停滞将触发结构性转向(改检索框架,而非调关键词)。" },
  { at: at(), kind: "log", nodeId: "screen", source: "orchestrator", level: "decision", text: "注入扰动策略:改从工业部署报告与专利反向溯源文献", detail: "pivot structure, not tactics——换证据来源框架,而不是在旧框架里调参。" },
  { at: at(), kind: "log", nodeId: "screen", source: "screen_agent", level: "info", text: "扰动生效:新增高相关 8 篇,停滞计数清零" },
  { at: at(), kind: "metric", metric: { iteration: 6, newFindings: 8, staleCount: 0, tokensUsed: 171000, roundsUsed: 6, directions: ["工业部署延迟瓶颈", "仿真到真机迁移(已排除)", "工业报告反向溯源"], nextDirection: null } },
  { at: at(), kind: "artifact", artifact: { id: "a-readlist", nodeId: "screen", name: "分级阅读清单.md", kind: "md", version: "v1", hash: "c30a55" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-screen",
      nodeId: "screen",
      level: "full",
      title: "③ 初筛分级完成 —— 确认阅读清单",
      metrics: [
        { label: "候选池", value: "214 → 168(去重)", state: "ok" },
        { label: "纳入", value: "46 篇", state: "ok" },
        { label: "停滞自愈", value: "1 次转向后恢复", state: "warn" },
      ],
      deliverables: ["分级阅读清单.md"],
      question: "阅读清单已按决策价值排序(必读 12 · 选读 34)。是否进入精读?",
      options: [
        { label: "进入精读", tone: "primary", action: "continue" },
        { label: "查看排除理由", tone: "ghost", action: "continue", hint: "原型中按继续处理" },
      ],
    },
  },
  { at: at(), kind: "status", nodeId: "screen", status: "done" },

  // ── ④ 精读与卡片 ────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "reading", status: "running" },
  { at: at(), kind: "log", nodeId: "reading", source: "reader ×3", level: "info", text: "并行精读:Paper Card 提取(研究问题/方法/证据/局限/来源索引)" },
  { at: at(), kind: "log", nodeId: "reading", source: "reader-1", level: "info", text: "全文双语对照:段落级原文+译文,图表卡片 14 张" },
  { at: at(), kind: "log", nodeId: "reading", source: "matrix_agent", level: "info", text: "证据矩阵:识别 3 组结论趋同、1 组冲突(延迟测量口径不一致)" },
  { at: at(), kind: "metric", metric: { iteration: 8, tokensUsed: 296000, roundsUsed: 9 } },
  { at: at(), kind: "artifact", artifact: { id: "a-cards", nodeId: "reading", name: "Paper Card ×12.md", kind: "md", version: "v1", hash: "e5b818" } },
  { at: at(), kind: "artifact", artifact: { id: "a-matrix", nodeId: "reading", name: "多论文证据矩阵.xlsx", kind: "xlsx", version: "v1", hash: "2a90fd" } },
  { at: at(), kind: "status", nodeId: "reading", status: "done" },

  // ── ⑤ 文献综述 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "survey", status: "running" },
  { at: at(), kind: "log", nodeId: "survey", source: "survey_agent", level: "info", text: "证据分层与证据地图完成,12 篇核心文献归位" },
  { at: at(), kind: "log", nodeId: "survey", source: "survey_agent", level: "info", text: "生成综述大纲(4 节,每节附分节材料包)" },
  { at: at(), kind: "artifact", artifact: { id: "a-outline", nodeId: "survey", name: "综述大纲.md", kind: "md", version: "v1", hash: "6c1e44" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-survey",
      nodeId: "survey",
      level: "full",
      title: "⑤ 综述大纲待确认 —— 动笔前的决策点",
      metrics: [
        { label: "核心文献", value: "12 篇", state: "ok" },
        { label: "证据覆盖", value: "4 / 4 节", state: "ok" },
      ],
      deliverables: ["综述大纲.md"],
      question: "大纲以「部署瓶颈三主线」组织:延迟压缩 / 硬件算力 / 可靠性验证。确认后开始撰写综述?",
      options: [
        { label: "确认大纲,开始撰写", tone: "primary", action: "continue" },
        { label: "调整结构", tone: "ghost", action: "continue", hint: "原型中按继续处理" },
      ],
    },
  },
  { at: at(), kind: "log", nodeId: "survey", source: "survey_agent", level: "info", text: "撰写综合论述(跨论文综合,非逐篇罗列)… 完成 3800 字" },
  { at: at(), kind: "metric", metric: { iteration: 10, tokensUsed: 402000, roundsUsed: 11 } },
  { at: at(), kind: "artifact", artifact: { id: "a-survey", nodeId: "survey", name: "文献综述稿.md", kind: "md", version: "v1", hash: "8d04b1" } },
  { at: at(), kind: "status", nodeId: "survey", status: "done" },

  // ── ⑥ 研究设计 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "design", status: "running" },
  { at: at(), kind: "log", nodeId: "design", source: "design_agent", level: "info", text: "操作化研究设计:延迟瓶颈 → 可测假设 H1-H3,估计目标与统计方案预定义" },
  { at: at(), kind: "log", nodeId: "design", source: "risk_auditor", level: "warn", text: "风险审计:真机样本量偏小(n=2 平台)存在外推局限,已记入方案约束" },
  { at: at(), kind: "metric", metric: { iteration: 11, tokensUsed: 447000 } },
  { at: at(), kind: "artifact", artifact: { id: "a-design", nodeId: "design", name: "研究设计与分析方案.md", kind: "md", version: "v1", hash: "b7f326" } },
  { at: at(), kind: "status", nodeId: "design", status: "done" },

  // ── ⑦ 数据分析与绘图 ────────────────────────────────────
  { at: at(), kind: "status", nodeId: "analysis", status: "running" },
  { at: at(), kind: "log", nodeId: "analysis", source: "analysis_agent", level: "info", text: "读取上传 benchmark.csv:结构/缺失/分布概览通过" },
  { at: at(), kind: "log", nodeId: "analysis", source: "analysis_agent", level: "info", text: "回归分析:模型规模 × 控制频率对成功率的影响,效应量 d=0.83" },
  { at: at(), kind: "log", nodeId: "analysis", source: "plot_agent", level: "info", text: "渲染期刊级图 1-3,附源数据表;可读性质检通过" },
  { at: at(), kind: "metric", metric: { iteration: 12, tokensUsed: 523000, roundsUsed: 13 } },
  { at: at(), kind: "artifact", artifact: { id: "a-stats", nodeId: "analysis", name: "统计结果表.xlsx", kind: "xlsx", version: "v1", hash: "f14c62" } },
  { at: at(), kind: "artifact", artifact: { id: "a-figs", nodeId: "analysis", name: "figures-1-3.pdf", kind: "figure", version: "v1", hash: "03a8e7" } },
  { at: at(), kind: "artifact", artifact: { id: "a-script", nodeId: "analysis", name: "analysis.R", kind: "script", version: "v1", hash: "59dd10" } },
  { at: at(), kind: "status", nodeId: "analysis", status: "done" },

  // ── ⑧ 章节写作 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "writing", status: "running" },
  { at: at(), kind: "log", nodeId: "writing", source: "writer_agent", level: "info", text: "论断提取:有证据论断 17 条 · 缺证据 2 条(已挂起)" },
  { at: at(), kind: "log", nodeId: "writing", source: "writer_agent", level: "warn", text: "反泄漏:真机能耗数据缺失,段落标记 [MATERIAL GAP],不编造填充" },
  { at: at(), kind: "log", nodeId: "writing", source: "figure_agent", level: "info", text: "并行分支:可视化与论证构建在大纲通过后同步推进" },
  { at: at(), kind: "log", nodeId: "writing", source: "citation_verifier", level: "info", text: "引文批量核验:第 4-6 批通过(累计 112 条)" },
  { at: at(), kind: "metric", metric: { iteration: 13, tokensUsed: 668000, roundsUsed: 15 } },
  { at: at(), kind: "artifact", artifact: { id: "a-draft-md", nodeId: "writing", name: "章节草稿.md", kind: "md", version: "v1", hash: "71aa09" } },
  { at: at(), kind: "artifact", artifact: { id: "a-draft-docx", nodeId: "writing", name: "章节草稿.docx", kind: "docx", version: "v1", hash: "de5503" } },
  { at: at(), kind: "status", nodeId: "writing", status: "done" },

  // ── ✓G1 诚信核查门 ──────────────────────────────────────
  { at: at(), kind: "status", nodeId: "integrity1", status: "running" },
  { at: at(), kind: "log", nodeId: "integrity1", source: "integrity_agent", level: "info", text: "引文三查:真实性 112/112 · 元数据 112/112 · 论断支持度审计中" },
  { at: at(), kind: "log", nodeId: "integrity1", source: "integrity_agent", level: "warn", text: "1 条引文仅「部分支持」邻近论断([7] 样本口径差异),已标注待你确认" },
  { at: at(), kind: "log", nodeId: "integrity1", source: "integrity_agent", level: "info", text: "7 类 AI 失败模式清单:全部 CLEAR(无幻觉引文/结果、无方法编造)" },
  { at: at(), kind: "metric", metric: { tokensUsed: 702000 } },
  { at: at(), kind: "artifact", artifact: { id: "a-g1", nodeId: "integrity1", name: "诚信核查报告-G1.md", kind: "md", version: "v1", hash: "a67c28" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-g1",
      nodeId: "integrity1",
      level: "mandatory",
      title: "✓ G1 诚信核查门 —— 机器核查已通过,待你确认",
      metrics: [
        { label: "引文真实性", value: "112 / 112", state: "ok" },
        { label: "论断支持度", value: "1 条部分支持", state: "warn" },
        { label: "失败模式清单", value: "7 / 7 CLEAR", state: "ok" },
      ],
      deliverables: ["诚信核查报告-G1.md"],
      flagged: ["[7] 样本口径与邻近论断存在差异——建议降格为背景引用"],
      question: "诚信门不可跳过。确认报告后进入模拟同行评审?",
      options: [
        { label: "确认报告,进入评审", tone: "primary", action: "continue" },
        { label: "退回修复后重验", tone: "ghost", action: "continue", hint: "原型中按继续处理" },
      ],
    },
  },
  { at: at(), kind: "status", nodeId: "integrity1", status: "done" },

  // ── ⑨ 模拟同行评审 ──────────────────────────────────────
  { at: at(), kind: "status", nodeId: "review", status: "running" },
  { at: at(), kind: "log", nodeId: "review", source: "review_panel", level: "info", text: "五人评审团就位:期刊契合 / 方法 / 领域 / 跨学科 / Devil's Advocate" },
  { at: at(), kind: "log", nodeId: "review", source: "R1 方法评审", level: "info", text: "方法严谨性 7/10:真机样本量与统计功效不足(P0)" },
  { at: at(), kind: "log", nodeId: "review", source: "R2 领域评审", level: "info", text: "工业相关性 8/10:建议补充与 Behavior Cloning 的公平对比(P1)" },
  { at: at(), kind: "log", nodeId: "review", source: "DA 魔鬼代言人", level: "decision", text: "反方攻击:核心论断「延迟是首要瓶颈」或可归因于算力;反驳评分 4/5 ≥ 阈值,部分让步", detail: "反谄媚机制:让步仅在反驳评分 ≥4/5 时发生。本次 DA 接受「延迟与算力耦合」的限定表述。" },
  { at: at(), kind: "metric", metric: { tokensUsed: 761000, reviewRound: 1 } },
  { at: at(), kind: "artifact", artifact: { id: "a-reviews", nodeId: "review", name: "评审报告×5+编辑决定.md", kind: "md", version: "v1", hash: "18b3e6" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-review",
      nodeId: "review",
      level: "mandatory",
      title: "⑨ 编辑决定:Minor Revision —— 由你裁决",
      metrics: [
        { label: "综合评分", value: "72 / 100", state: "warn" },
        { label: "P0 问题", value: "1(统计功效)", state: "bad" },
        { label: "P1 问题", value: "2", state: "warn" },
      ],
      deliverables: ["评审报告×5+编辑决定.md", "修改路线图"],
      question: "Accept 直达 G2 终审;Minor 进入修改-复审回路(上限 2 轮);Reject 终止任务。",
      options: [
        { label: "Minor:进入修改返修", tone: "primary", action: "continue" },
        { label: "Accept:跳至 G2 终审", tone: "ghost", action: "skip-to", target: "g2" },
        { label: "Reject:终止任务", tone: "danger", action: "end" },
      ],
    },
  },

  // ── ⑩ 修改返修(第 1 轮) ────────────────────────────────
  { at: at(), kind: "status", nodeId: "review", status: "done" },
  { at: at(), kind: "status", nodeId: "revise", status: "running" },
  { at: at(), kind: "log", nodeId: "revise", source: "revision_coach", level: "info", text: "修改路线图 10 条全部落位:接受 8 · 澄清 1 · 反驳 1(每条对应实际修改)" },
  { at: at(), kind: "log", nodeId: "revise", source: "analysis_agent", level: "info", text: "P0 修复:功效分析补充 + 样本局限改写为显式约束" },
  { at: at(), kind: "log", nodeId: "revise", source: "revision_agent", level: "info", text: "生成逐点回复信与 R&R 跟踪表(10/10 可核查)" },
  { at: at(), kind: "log", nodeId: "revise", source: "re_reviewer", level: "info", text: "复审:残留 0 条 P0、1 条 P2 措辞建议;Δ=+11 分 → 83/100" },
  { at: at(), kind: "log", nodeId: "revise", source: "orchestrator", level: "decision", text: "收敛判定:无 P0 且提升显著;P2 记为「已确认局限」,不再进入第 2 轮" },
  { at: at(), kind: "metric", metric: { iteration: 15, tokensUsed: 823000, roundsUsed: 19 } },
  { at: at(), kind: "artifact", artifact: { id: "a-revised", nodeId: "revise", name: "修改稿.md", kind: "md", version: "v2", hash: "c82f47" } },
  { at: at(), kind: "artifact", artifact: { id: "a-response", nodeId: "revise", name: "逐点回复信.md", kind: "md", version: "v1", hash: "5b19de" } },
  { at: at(), kind: "status", nodeId: "revise", status: "done" },

  // ── ✓G2 终审诚信门 ──────────────────────────────────────
  { at: at(), kind: "marker", id: "g2" },
  { at: at(), kind: "status", nodeId: "integrity2", status: "running" },
  { at: at(), kind: "log", nodeId: "integrity2", source: "integrity_agent", level: "info", text: "终审从头独立重验(不复用 G1 结论):引文 118/118 · 论断 100% 核验" },
  { at: at(), kind: "log", nodeId: "integrity2", source: "integrity_agent", level: "info", text: "7 类失败模式重跑:全部 CLEAR;G1 的「部分支持」引文已降格,无残留 SUSPECTED" },
  { at: at(), kind: "artifact", artifact: { id: "a-g2", nodeId: "integrity2", name: "终审诚信报告-G2.md", kind: "md", version: "v1", hash: "94e0b5" } },
  {
    at: at(),
    kind: "checkpoint",
    checkpoint: {
      id: "cp-g2",
      nodeId: "integrity2",
      level: "mandatory",
      title: "✓ G2 终审诚信门 —— 零容忍,全部通过",
      metrics: [
        { label: "引文核验", value: "118 / 118", state: "ok" },
        { label: "失败模式", value: "7 / 7 CLEAR", state: "ok" },
        { label: "残留问题", value: "0", state: "ok" },
      ],
      deliverables: ["终审诚信报告-G2.md"],
      question: "定稿前最后一道门。确认后进入润色与排版?",
      options: [{ label: "确认,进入定稿流程", tone: "primary", action: "continue" }],
    },
  },
  { at: at(), kind: "status", nodeId: "integrity2", status: "done" },

  // ── ⑪ 润色 ─────────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "polish", status: "running" },
  { at: at(), kind: "log", nodeId: "polish", source: "polish_agent", level: "info", text: "润色结构与文字:限定表述保留,论断边界核对无强化" },
  { at: at(), kind: "artifact", artifact: { id: "a-polish", nodeId: "polish", name: "润色稿+编辑说明.md", kind: "md", version: "v3", hash: "3f7a90" } },
  { at: at(), kind: "status", nodeId: "polish", status: "done" },

  // ── ⑫ 排版与投稿检查 ────────────────────────────────────
  { at: at(), kind: "status", nodeId: "format", status: "running" },
  { at: at(), kind: "log", nodeId: "format", source: "format_agent", level: "info", text: "重建为目标期刊 LaTeX 模板包,tectonic 编译 PDF 成功" },
  { at: at(), kind: "log", nodeId: "format", source: "compliance_agent", level: "info", text: "投稿完整性检查:阻断性问题 0 · 合规提醒 2(数据可用性声明、AI 披露)" },
  { at: at(), kind: "artifact", artifact: { id: "a-tex", nodeId: "format", name: "paper-latex.tar.gz", kind: "tex", version: "v1", hash: "6bd431" } },
  { at: at(), kind: "artifact", artifact: { id: "a-checklist", nodeId: "format", name: "投稿完整性检查表.md", kind: "md", version: "v1", hash: "0e58ac" } },
  { at: at(), kind: "status", nodeId: "format", status: "done" },

  // ── ⑬ 成果传播 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "disseminate", status: "running" },
  { at: at(), kind: "log", nodeId: "disseminate", source: "poster_agent", level: "info", text: "学术海报:版式与证据层级规划完成,导出 PDF" },
  { at: at(), kind: "log", nodeId: "disseminate", source: "slides_agent", level: "info", text: "学术幻灯片:12 页可编辑 PPTX + 演讲备注" },
  { at: at(), kind: "artifact", artifact: { id: "a-poster", nodeId: "disseminate", name: "学术海报.pdf", kind: "pdf", version: "v1", hash: "b26e79" } },
  { at: at(), kind: "artifact", artifact: { id: "a-slides", nodeId: "disseminate", name: "学术幻灯片.pptx", kind: "pptx", version: "v1", hash: "7c04f2" } },
  { at: at(), kind: "status", nodeId: "disseminate", status: "done" },

  // ── ⑭ 过程记录 ──────────────────────────────────────────
  { at: at(), kind: "status", nodeId: "record", status: "running" },
  { at: at(), kind: "log", nodeId: "record", source: "orchestrator", level: "info", text: "汇总协作史、协作深度观察与失败模式审计日志,生成双语过程记录" },
  { at: at(), kind: "artifact", artifact: { id: "a-record", nodeId: "record", name: "过程记录-双语.pdf", kind: "pdf", version: "v1", hash: "e91d36" } },
  { at: at(), kind: "status", nodeId: "record", status: "done" },
  { at: at(), kind: "log", nodeId: "record", source: "orchestrator", level: "decision", text: "流水线完成:全部 16 节点交付,诚信双门通过,预算内收官" },
];

/** 选题验证节点:三关卡评分(设计文档 §4.3) */
export const TOPIC_GATES = [
  { label: "开放性", score: 4, note: "最相近工作留下延迟-算力耦合未解" },
  { label: "贡献类型 / 死胡同", score: 4, note: "增量贡献明确;候选 B 死胡同已排除" },
  { label: "可行性", score: 3, note: "仅依据你提供的资源条件打分" },
];

/** 模拟评审节点:五人评审团 */
export const REVIEW_PANEL = [
  { role: "期刊契合", score: 8, tone: "ok" as const },
  { role: "方法严谨性", score: 7, tone: "warn" as const },
  { role: "领域相关", score: 8, tone: "ok" as const },
  { role: "跨学科视角", score: 6, tone: "warn" as const },
  { role: "Devil's Advocate", score: 4, tone: "da" as const },
];

/** 证据与论断追踪样例(综述/写作节点,设计文档 §4.4) */
export const EVIDENCE_SAMPLE = [
  {
    claim: "扩散策略在多 SKU 装配任务上成功率较 BC 高 28%",
    support: "直接支持",
    refs: ["[5] BMW 产线实测", "[1] Diffusion Policy"],
  },
  {
    claim: "延迟是工业部署的首要瓶颈",
    support: "部分支持",
    refs: ["[7] 样本口径差异", "[9] 算力耦合分析"],
  },
  {
    claim: "60Hz 控制频率需 RTX 4090 级算力",
    support: "仅背景",
    refs: ["[6] 硬件需求推算"],
  },
];

/** 7 类 AI 失败模式清单(诚信报告面板) */
export const FAILURE_MODES = [
  { id: "M1", label: "实现 bug 过自检", status: "CLEAR" },
  { id: "M2", label: "幻觉引文", status: "CLEAR" },
  { id: "M3", label: "幻觉实验结果", status: "CLEAR" },
  { id: "M4", label: "捷径依赖", status: "CLEAR" },
  { id: "M5", label: "bug 当创新", status: "CLEAR" },
  { id: "M6", label: "方法编造", status: "CLEAR" },
  { id: "M7", label: "框架锁定", status: "CLEAR" },
];

/** 材料护照:数据访问级别跃迁(产物档案面板) */
export const PASSPORT_LEVELS = [
  { level: "raw", label: "原始材料", desc: "任意来源,可能含对抗内容", until: "②文献检索" },
  { level: "redacted", label: "脱敏材料", desc: "经来源核验,不再引入新原始数据", until: "③初筛 ~ ⑧写作" },
  { level: "verified_only", label: "已验证材料", desc: "仅消费通过诚信门的产物", until: "✓G1 之后全部阶段" },
];

/** 日志时间戳:从 09:30 起按事件序号推进的伪时钟(确定性) */
export function pseudoTime(index: number): string {
  const base = 9 * 3600 + 30 * 60;
  const total = base + index * 47;
  const h = String(Math.floor(total / 3600) % 24).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
