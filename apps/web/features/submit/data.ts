import type { Venue, VenueBadgeName } from "@/types";

/** 徽章配色 —— 与投稿详情页 SVG 的 BD 调色板一致 */
export const BADGE_PALETTE: Record<VenueBadgeName, { bg: string; fg: string }> = {
  "CCF A": { bg: "#D1FAE5", fg: "#059669" },
  "CCF C": { bg: "#FEF3C7", fg: "#D97706" },
  "CORE A*": { bg: "#EDE9FE", fg: "#7C3AED" },
  "TH-CPL A": { bg: "#FCE7F3", fg: "#DB2777" },
  "TH-CPL B": { bg: "#FCE7F3", fg: "#DB2777" },
  CSRanking: { bg: "#CCFBF1", fg: "#0D9488" },
  "CAAI A": { bg: "#E0E7FF", fg: "#4F46E5" },
  "CAAI C": { bg: "#E0E7FF", fg: "#4F46E5" },
  中科院1区: { bg: "#FFEDD5", fg: "#EA580C" },
  "JCR Q1": { bg: "#D1FAE5", fg: "#059669" },
  "高质量期刊 T1": { bg: "#F3E8FF", fg: "#9333EA" },
};

/** 等级筛选 chips(左侧面板) */
export const LEVEL_CHIPS = [
  "CCF-A",
  "CCF-B",
  "CCF-C",
  "CAAI-A",
  "CAAI-B",
  "CAAI-C",
  "中科院1区",
  "中科院2区",
  "中科院3区",
  "中科院4区",
  "CORE-A*",
  "CORE-A",
  "CORE-B",
  "CORE-C",
  "TH-CPL A",
  "TH-CPL B",
] as const;

/** 研究方向筛选(长名称按原型两行展示) */
export const DIRECTION_ROWS: { lines: string[]; count: string }[] = [
  { lines: ["计算机体系结构/并行", "与分布计算/存储系统"], count: "104" },
  { lines: ["计算机网络"], count: "75" },
  { lines: ["网络与信息安全"], count: "67" },
  { lines: ["软件工程/系统软件/程", "序设计语言"], count: "95" },
  { lines: ["数据库/数据挖掘/内容", "检索"], count: "90" },
  { lines: ["计算机科学理论"], count: "77" },
  { lines: ["计算机图形学与多媒体"], count: "81" },
  { lines: ["人工智能"], count: "147" },
  { lines: ["人机交互与普适计算"], count: "48" },
  { lines: ["交叉/综合/新兴"], count: "136" },
];

/** 会议/期刊卡片 —— 内容提取自「深知-投稿详情页.svg」 */
export const venues: Venue[] = [
  {
    id: "dai-2026",
    kind: "conference",
    abbr: "DAI",
    fullName: "International Conference on Distributed Artificial Intelligence",
    badges: ["CCF C"],
    metaRows: [
      [
        ["folder", "人工智能"],
        ["pin", "Hong Kong, China"],
        ["cal", "November 29-December 2, 2026"],
      ],
    ],
    chips: [],
    accent: "danger",
    deadline: {
      label: "摘要截止",
      dateText: "2026年7月28日 19:59",
      offsetMs: 28 * 60_000 + 11_000,
    },
  },
  {
    id: "aaai-2027",
    kind: "conference",
    abbr: "AAAI",
    fullName: "AAAI人工智能会议",
    badges: ["CCF A", "CORE A*", "TH-CPL A", "CSRanking", "CAAI A"],
    metaRows: [
      [
        ["folder", "人工智能"],
        ["chart", "2026录用率: 17.6%"],
        ["pin", "Montréal, Québec, Canada"],
        ["cal", "February 16-23, 2027"],
        ["quote", "平均引用: 8.09964"],
      ],
    ],
    chips: [
      "Artificial Intelligence",
      "Machine Learning",
      "Knowledge Representation",
      "Planning",
    ],
    accent: "success",
    deadline: {
      label: "全文截止",
      dateText: "2026年7月29日 19:59",
      offsetMs: 24 * 3600_000 + 28 * 60_000 + 11_000,
    },
  },
  {
    id: "hpca-2027",
    kind: "conference",
    abbr: "HPCA",
    fullName:
      "IEEE International Symposium on High-Performance Computer Architecture",
    badges: ["CCF A", "CORE A*", "TH-CPL B", "CAAI C"],
    metaRows: [
      [
        ["folder", "计算机体系结构/并行与分布计算/存储系统"],
        ["chart", "2026录用率: 19.8%"],
      ],
      [
        ["pin", "Salt Lake City, Utah, USA"],
        ["cal", "March 20-24, 2027"],
        ["quote", "平均引用: 18.5792"],
      ],
    ],
    chips: ["Computer Architecture", "Parallel Computing", "Storage Systems"],
    accent: "success",
    deadline: {
      label: "全文截止",
      dateText: "2026年8月1日 19:59",
      offsetMs: 4 * 24 * 3600_000 + 28 * 60_000 + 11_000,
    },
  },
  {
    id: "ieee-tkde",
    kind: "journal",
    abbr: "IEEE TKDE",
    fullName: "IEEE Transactions on Knowledge and Data Engineering",
    badges: ["CCF A", "TH-CPL B", "CAAI A", "中科院1区", "JCR Q1", "高质量期刊 T1"],
    metaRows: [
      [
        ["folder", "数据库/数据挖掘/内容检索"],
        ["quote", "平均引用: 15.8638"],
      ],
    ],
    chips: ["Data Mining", "Knowledge Engineering", "Database Systems", "Big Data"],
    accent: "success",
  },
  {
    id: "ieee-tpami",
    kind: "journal",
    abbr: "IEEE TPAMI",
    fullName: "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    badges: ["CCF A", "TH-CPL B", "CAAI A", "中科院1区", "JCR Q1", "高质量期刊 T1"],
    metaRows: [
      [
        ["folder", "人工智能"],
        ["quote", "平均引用: 16.2350"],
      ],
    ],
    chips: [
      "Computer Vision",
      "Pattern Recognition",
      "Machine Learning",
      "Deep Learning",
    ],
    accent: "success",
  },
];
