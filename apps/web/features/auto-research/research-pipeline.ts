/**
 * Auto Research 流水线静态定义 —— 节点 / 边 / 关卡
 * 依据 docs/auto-research-page-design.md §3:14 节点 + 2 道诚信门,八大模块分组
 */

export type NodeStatus =
  | "idle"
  | "ready"
  | "running"
  | "waiting_user"
  | "blocked"
  | "done"
  | "stalled"
  | "skipped";

export type GateKind = "decision" | "confirm" | "machine" | null;

export type ModuleId =
  | "ideation"
  | "literature"
  | "reading"
  | "design"
  | "analysis"
  | "writing"
  | "submission"
  | "dissemination";

/** 八大模块配色(昼/夜均有足够对比度的中间调) */
export const MODULES: Record<ModuleId, { label: string; color: string }> = {
  ideation: { label: "选题构思", color: "#7c3aed" },
  literature: { label: "文献", color: "var(--color-primary)" },
  reading: { label: "阅读整理", color: "#0e7490" },
  design: { label: "研究设计", color: "#059669" },
  analysis: { label: "数据分析", color: "#d97706" },
  writing: { label: "写作可视化", color: "#db2777" },
  submission: { label: "投稿返修", color: "#dc2626" },
  dissemination: { label: "成果传播", color: "#a16207" },
};

export interface PipelineNode {
  id: string;
  index: string;
  label: string;
  module: ModuleId;
  /** 节点收尾时的关卡类型 */
  gate: GateKind;
  shape: "stage" | "integrity";
  x: number;
  y: number;
  summary: string;
  deliverables: string[];
}

export interface PipelineEdge {
  from: string;
  to: string;
  label?: string;
  dashed?: boolean;
  /** 平行线横向偏移(评审回路双线) */
  offset?: number;
}

export const NODE_W = 132;
export const NODE_H = 52;
export const VIEW_W = 980;
export const VIEW_H = 540;

const R1 = 100;
const R2 = 280;
const R3 = 460;

export const PIPELINE_NODES: PipelineNode[] = [
  {
    id: "topic",
    index: "①",
    label: "选题验证",
    module: "ideation",
    gate: "decision",
    shape: "stage",
    x: 90,
    y: R1,
    summary:
      "检索最相近已有工作,对每个候选方向反向求证,经开放性/贡献类型/可行性三道关卡打分,产出可以做/有条件可以做/不建议做的决策档案。",
    deliverables: ["研究空白决策档案"],
  },
  {
    id: "search",
    index: "②",
    label: "文献检索",
    module: "literature",
    gate: null,
    shape: "stage",
    x: 250,
    y: R1,
    summary:
      "按主题路由检索源(OpenAlex / 万方),附加 IF、JCR、CAS、CCF、EI、中文核心质量标签,建立候选论文池。",
    deliverables: ["candidate-paper-pool.json", "candidate-paper-pool.xlsx"],
  },
  {
    id: "screen",
    index: "③",
    label: "初筛分级",
    module: "literature",
    gate: "decision",
    shape: "stage",
    x: 410,
    y: R1,
    summary:
      "去重合并、补全元数据,按纳入/排除标准逐条记录理由,按决策价值排序生成阅读清单。",
    deliverables: ["分级阅读清单"],
  },
  {
    id: "reading",
    index: "④",
    label: "精读与卡片",
    module: "reading",
    gate: null,
    shape: "stage",
    x: 570,
    y: R1,
    summary:
      "Paper Card 深度精读、全文双语对照、图表卡片;横向比较多篇论文建立可追溯证据矩阵。",
    deliverables: ["Paper Card ×12", "多论文证据矩阵"],
  },
  {
    id: "survey",
    index: "⑤",
    label: "文献综述",
    module: "reading",
    gate: "decision",
    shape: "stage",
    x: 730,
    y: R1,
    summary:
      "证据分层→证据地图→大纲→综合论述成稿(非逐篇罗列),引用可追溯。大纲需你确认后才动笔。",
    deliverables: ["综述大纲", "文献综述稿"],
  },
  {
    id: "design",
    index: "⑥",
    label: "研究设计",
    module: "design",
    gate: null,
    shape: "stage",
    x: 730,
    y: R2,
    summary:
      "研究问题连接到假设、测量、样本、估计目标与统计分析方案,附偏倚/混杂/泄漏/伦理风险审计。",
    deliverables: ["研究设计与分析方案", "风险审计清单"],
  },
  {
    id: "analysis",
    index: "⑦",
    label: "数据分析与绘图",
    module: "analysis",
    gate: null,
    shape: "stage",
    x: 570,
    y: R2,
    summary:
      "对话式数据分析(CSV/XLSX):概览、比较、回归;产出统计结果表、期刊级图表与可复用脚本。",
    deliverables: ["统计结果表", "图 1-3(含源数据)", "analysis.R"],
  },
  {
    id: "writing",
    index: "⑧",
    label: "章节写作",
    module: "writing",
    gate: "machine",
    shape: "stage",
    x: 410,
    y: R2,
    summary:
      "先提取论断并区分有证据/缺证据,再按论证结构写作;无材料支撑的填充显式标记 [MATERIAL GAP]。MD + DOCX 双交付。",
    deliverables: ["章节草稿.md", "章节草稿.docx"],
  },
  {
    id: "integrity1",
    index: "✓",
    label: "G1 诚信核查门",
    module: "submission",
    gate: "confirm",
    shape: "integrity",
    x: 250,
    y: R2,
    summary:
      "阻断性门禁:引文三查(真实/元数据/论断支持度,每 20 条一批)+ 7 类 AI 失败模式清单。FAIL 须修复重验(≤3 轮)。",
    deliverables: ["诚信核查报告 G1"],
  },
  {
    id: "review",
    index: "⑨",
    label: "模拟同行评审",
    module: "submission",
    gate: "decision",
    shape: "stage",
    x: 90,
    y: R2,
    summary:
      "五人评审团(期刊契合/方法/领域/跨学科/Devil's Advocate),输出编辑决定与修改路线图。反方让步阈值:反驳评分 ≥4/5 才让。",
    deliverables: ["5 份评审报告", "编辑决定信", "修改路线图"],
  },
  {
    id: "revise",
    index: "⑩",
    label: "修改返修",
    module: "submission",
    gate: "decision",
    shape: "stage",
    x: 90,
    y: R3,
    summary:
      "按修改路线图逐条落实,生成逐点回复信与跟踪表;复审聚焦修改落实。回路最多 2 轮,收敛(Δ<3 分且无 P0)时建议停止。",
    deliverables: ["修改稿", "逐点回复信", "R&R 跟踪表"],
  },
  {
    id: "integrity2",
    index: "✓",
    label: "G2 终审诚信门",
    module: "submission",
    gate: "confirm",
    shape: "integrity",
    x: 250,
    y: R3,
    summary:
      "零容忍终审:从头独立重跑 7 类失败模式清单与 100% 论断核验,任何 SUSPECTED 均阻断。",
    deliverables: ["终审诚信报告 G2"],
  },
  {
    id: "polish",
    index: "⑪",
    label: "期刊润色",
    module: "writing",
    gate: null,
    shape: "stage",
    x: 410,
    y: R3,
    summary:
      "保留科学含义与论断边界,改进英文表达、论证节奏与期刊适配;附编辑说明,不强化论断。",
    deliverables: ["润色稿", "编辑说明"],
  },
  {
    id: "format",
    index: "⑫",
    label: "排版与投稿检查",
    module: "submission",
    gate: "machine",
    shape: "stage",
    x: 570,
    y: R3,
    summary:
      "重建为目标期刊 LaTeX 可编译包;对照期刊要求清点投稿材料,标出阻断性与合规问题。",
    deliverables: ["LaTeX 模板包 + PDF", "投稿完整性检查表"],
  },
  {
    id: "disseminate",
    index: "⑬",
    label: "成果传播",
    module: "dissemination",
    gate: null,
    shape: "stage",
    x: 730,
    y: R3,
    summary: "把论文与项目材料组织为会议学术海报与可编辑的学术幻灯片(PPTX + PDF)。",
    deliverables: ["学术海报.pdf", "学术幻灯片.pptx"],
  },
  {
    id: "record",
    index: "⑭",
    label: "过程记录",
    module: "dissemination",
    gate: "decision",
    shape: "stage",
    x: 890,
    y: R3,
    summary:
      "生成双语过程记录:人机协作史、协作深度观察、AI 自省报告与失败模式审计日志。",
    deliverables: ["过程记录.pdf(双语)"],
  },
];

export const NODE_MAP = new Map(PIPELINE_NODES.map((n) => [n.id, n]));

export const PIPELINE_EDGES: PipelineEdge[] = [
  { from: "topic", to: "search" },
  { from: "search", to: "screen" },
  { from: "screen", to: "reading" },
  { from: "reading", to: "survey" },
  { from: "survey", to: "design", offset: 24 },
  { from: "design", to: "analysis" },
  { from: "analysis", to: "writing" },
  { from: "writing", to: "integrity1" },
  { from: "integrity1", to: "review" },
  { from: "review", to: "revise", label: "Minor / Major", offset: -14 },
  { from: "revise", to: "review", label: "复审 · ≤2 轮", dashed: true, offset: 14 },
  { from: "revise", to: "integrity2", label: "Accept" },
  { from: "integrity2", to: "polish" },
  { from: "polish", to: "format" },
  { from: "format", to: "disseminate" },
  { from: "disseminate", to: "record" },
];

/** 关卡类型展示元数据 */
export const GATE_META: Record<
  Exclude<GateKind, null>,
  { label: string; hint: string }
> = {
  decision: { label: "决策关卡", hint: "你需要选择分支,流水线才会继续" },
  confirm: { label: "诚信确认门", hint: "机器先核查,你确认报告;不可跳过" },
  machine: { label: "机器门", hint: "自动质检,失败时给出处理选项" },
};

/** 可选终点输出(设计文档 J2:结尾也要能够选择) */
export const EXIT_OPTIONS = PIPELINE_NODES.filter((n) =>
  ["survey", "writing", "format", "disseminate", "record"].includes(n.id),
).map((n) => ({ id: n.id, label: `${n.index} ${n.label}` }));
