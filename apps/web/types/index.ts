/** 论文 Feed 卡片 */
export interface FeedPaper {
  id: string;
  date: string;
  venue: string;
  venueTone: "violet" | "amber" | "green";
  authors: string;
  title: string;
  abstract: string;
  aiLink: string;
  tags: string[];
  /** 仅在真实数据源提供时展示；发现页 Knowledge 搜索结果不伪造指标。 */
  likes?: number;
  citations?: number;
  thumb: string;
}

/** 投稿目标(会议/期刊) */
export interface Venue {
  id: string;
  kind: "conference" | "journal";
  abbr: string;
  fullName: string;
  badges: VenueBadgeName[];
  /** [icon, text] 元信息行,支持多行 */
  metaRows: [VenueMetaIcon, string][][];
  chips: string[];
  accent: "danger" | "success";
  /** 仅会议有倒计时 */
  deadline?: {
    label: string;
    dateText: string;
    /** 相对当前时间的毫秒偏移(演示用实时倒计时) */
    offsetMs: number;
  };
}

export type VenueMetaIcon = "folder" | "pin" | "cal" | "chart" | "quote";

export type VenueBadgeName =
  | "CCF A"
  | "CCF C"
  | "CORE A*"
  | "TH-CPL A"
  | "TH-CPL B"
  | "CSRanking"
  | "CAAI A"
  | "CAAI C"
  | "中科院1区"
  | "JCR Q1"
  | "高质量期刊 T1";

/** 学者 */
export interface Scholar {
  id: string;
  nameCn: string;
  nameEn: string;
  initials: string;
  avatarColor: string;
  role: string;
  affiliation: string;
  bio: string;
  citations: string;
  hIndex: number;
  tags: string[];
  followed?: boolean;
}

export interface Publication {
  id: string;
  title: string;
  abstract: string;
  authors: string;
  venue: string;
  citations: string;
  citationsShort: string;
}

/** 知识库文献 */
export interface LibraryItem {
  id: string;
  title: string;
  venue: string;
  arxiv: string;
  authors: string;
  addedAt: string;
  pdfTone: "violet" | "amber" | "green";
}

export interface LibraryFolder {
  name: string;
  count: number;
  active?: boolean;
}

/** AI 研究助手 */
export interface AgentReference {
  id: number;
  venue: string;
  title: string;
  author: string;
  citations: string;
  tone: "violet" | "green" | "amber" | "gray";
  recommended?: boolean;
}

export interface RecentResearch {
  id: string;
  title: string;
  time: string;
  refs: number;
  active?: boolean;
}

/** 论文详情(阅读器) */
export interface PaperDetail {
  id: string;
  title: string;
  authors: string[];
  affiliation: string;
  likes: number;
  page: { current: number; total: number };
  toc: { id: string; label: string; active?: boolean }[];
  abstract: string;
  introduction: string;
}

export interface SimilarPaper {
  title: string;
  meta: string;
}

/** 知识图谱节点 */
export interface GraphNode {
  id: string;
  /** 圆下两行标签:公域 ["Liu", "2024"],私域 ["扩散策略", "2025"] */
  labelLines: [string, string];
  /** 0~1 关系强度 → 圆半径与透明度 */
  weight: number;
  year: number;
  title: string;
  authors: string;
  venue: string;
  citations: string;
  abstract: string;
  /** 右栏「查看论文详情」跳转目标(/papers/[paperId]) */
  paperId?: string;
  /** 私域分层;公域不设 */
  layer?: "mine" | "folder";
}

export interface GraphEdge {
  source: string;
  target: string;
  strength: number;
  /** 私域跨层边(虚线) */
  crossLayer?: boolean;
}

export interface PaperGraph {
  origin: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** 左栏列表顺序 */
  relatedIds: string[];
}

/** 专利 */
export interface Patent {
  id: string;
  /** 专利名称 */
  title: string;
  /** 申请号,如 CN202410123456.7 */
  applicationNo: string;
  /** 申请人 */
  applicant: string;
  /** 公开日 YYYY-MM-DD(字典序即可排序) */
  publishedAt: string;
  /** 技术领域(左栏筛选维度) */
  field: string;
  status: "已授权" | "实质审查" | "已公开" | "PCT";
  kind: "发明" | "实用新型";
  /** 被引次数(排序用) */
  citations: number;
}

/** 项目基金 */
export interface Funding {
  id: string;
  /** 项目名称 */
  title: string;
  /** 批准号 */
  grantNo: string;
  /** 负责人 */
  pi: string;
  /** 依托单位 */
  institution: string;
  /** 资助金额,如 300 万元 */
  amount: string;
  /** 起止年限,如 2024-01 ~ 2027-12 */
  period: string;
  /** 资助类别(左栏筛选维度) */
  category: string;
  status: "在研" | "结题";
}

/** 机构统计项 */
export interface InstitutionStat {
  label: string;
  value: string;
}

/** 研究机构 */
export interface Institution {
  id: string;
  nameCn: string;
  nameEn: string;
  /** logo 色块字母,如 THU */
  initials: string;
  logoColor: string;
  type: "高校" | "研究院" | "企业实验室";
  location: string;
  /** 详细介绍:历史沿革、学科优势、代表平台(3~4 句,卡片直接全文展示) */
  intro: string;
  /** 固定 4 项:研究人员 / 年论文 / 总引用 / 国家级平台 */
  stats: InstitutionStat[];
  /** 优势方向 tags */
  fields: string[];
  /** 代表性成果一句话 */
  highlight: string;
  /** 默认已收藏(mock) */
  bookmarked?: boolean;
  /** 综合排名(升序排序用) */
  rank: number;
  /** 年论文数(降序排序用) */
  papersPerYear: number;
}

/** Deep Research 研究计划节 */
export interface DRPlanSection {
  id: string;
  /** 大纲节标题,如 "1. 代表性方法与技术脉络" */
  title: string;
  /** 该节检索意图(计划卡内展示) */
  query: string;
}

/** Deep Research 来源 / 参考文献条目 */
export interface DRSource {
  /** 引用编号 [n] */
  id: number;
  /** 来源墙 chip 用短名,如 "Diffusion Policy" */
  short: string;
  title: string;
  /** 如 "CoRL 2024 · Stanford" */
  venue: string;
  author: string;
  /** 如 "引用 1.8k" */
  citations: string;
  recommended?: boolean;
}

/** Deep Research 报告节 */
export interface DRReportSection {
  /** 与 DRPlanSection.id 对应 */
  id: string;
  heading: string;
  /** 段落,含 [n] 引用标记 */
  paragraphs: string[];
  table?: {
    caption: string;
    header: string[];
    rows: string[][];
    highlightRow?: number;
  };
  /** 编号列表(趋势等) */
  list?: string[];
}

/** Deep Research 报告 */
export interface DRReport {
  question: string;
  title: string;
  abstract: string;
  stats: { read: number; cited: number };
  sections: DRReportSection[];
  references: DRSource[];
}

export type DRStepKind = "search" | "read" | "analyze" | "write";

/** Deep Research 预录步骤事件(确定性时间轴) */
export interface DRStepEvent {
  offsetMs: number;
  kind: DRStepKind;
  label: string;
  /** write 类事件关联的章节 */
  sectionId?: string;
}

/** Deep Research 历史研究条目 */
export interface DRHistoryItem {
  id: string;
  title: string;
  status: "已完成" | "进行中";
  sources: number;
  time: string;
}

/** 首页统一搜索框入口：普通搜索 / 问 AI */
export type ComposerEntryMode = "search" | "ai";

export type {
  ChatAttachment,
  ChatCapabilities,
  ChatModelId,
  ChatReplyMode,
  ComposerSubmitPayload,
} from "./ai-search";
