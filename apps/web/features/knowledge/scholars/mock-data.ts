import type { ScholarProfile } from "./types";

/** 所有人物、机构、任职及统计均为虚构，仅用于产品评审。ID 是固定 fixture 标识。 */
export const DEMO_SCHOLARS: ScholarProfile[] = [
  {
    scholar_id: "demo:scholar/01",
    name_zh: "林知遥",
    name_en: "Zhiyao Lin",
    avatar_path: "/images/scholars/demo-avatar.svg",
    affiliations: [
      { institution: "星澜大学 · 智能科学学院", position: "副教授" },
      { institution: "远川机器人研究院", position: "访问研究员" },
    ],
    bio_zh:
      "探索机器人如何从观察与交互中学习。研究围绕视觉运动策略、模仿学习与生成式模型展开，关注从实验环境走向开放世界时的泛化与可靠性。希望让机器人以更少的数据，理解更丰富的任务。",
    bio_en:
      "Exploring how robots learn from observation and interaction, with a focus on visuomotor policies, imitation learning, and generalization in open environments.",
    metrics: { paper_count: 38, citation_count: 2460 },
    annual_citations: [
      { year: 2022, count: 128 },
      { year: 2023, count: 286 },
      { year: 2024, count: 452 },
      { year: 2025, count: 637 },
      { year: 2026, count: 714 },
    ],
    updated_at: "2026-10-12",
  },
  {
    scholar_id: "demo:scholar/02",
    name_zh: null,
    name_en: "Avery Morgan",
    avatar_path: null,
    affiliations: [
      {
        institution: "Northhaven Institute of Technology",
        position: "Assistant Professor",
      },
    ],
    bio_zh: null,
    bio_en:
      "Studying how language, vision, and action come together in embodied systems. Current work explores transferable representations and learning from diverse demonstrations.",
    metrics: { paper_count: 24, citation_count: 1380 },
    annual_citations: [
      { year: 2022, count: 92 },
      { year: 2024, count: 218 },
      { year: 2026, count: 405 },
    ],
    updated_at: "2026-10-10",
  },
  {
    scholar_id: "demo:scholar/03",
    name_zh: "陈映舟",
    name_en: "Yingzhou Chen",
    avatar_path: null,
    affiliations: [{ institution: "云岫大学 · 计算机系", position: "教授" }],
    bio_zh:
      "关注序列决策与离线强化学习，研究如何从已有数据中学习稳健的决策策略，以及如何在有限交互下评估和改善策略表现。",
    bio_en:
      "Research on sequential decision-making and reliable offline reinforcement learning.",
    metrics: { paper_count: 56, citation_count: 4820 },
    annual_citations: [
      { year: 2022, count: 420 },
      { year: 2023, count: 560 },
      { year: 2024, count: 725 },
      { year: 2025, count: 910 },
      { year: 2026, count: 1042 },
    ],
    updated_at: "2026-10-09",
  },
  {
    scholar_id: "demo:scholar/04",
    name_zh: "许沐青",
    name_en: "Muqing Xu",
    // 故意保留不可访问头像，供评审验证图片加载失败后的首字母回退。
    avatar_path: "/images/scholars/unavailable-demo-avatar.png",
    affiliations: [{ institution: "澄光智能实验室", position: "研究员" }],
    bio_zh:
      "研究生成模型与规划的交叉问题，尝试用扩散模型表达多模态的行为分布，连接轨迹生成、控制与长期任务规划。",
    bio_en: null,
    metrics: { paper_count: 17, citation_count: null },
    annual_citations: [
      { year: 2024, count: 46 },
      { year: 2026, count: 172 },
    ],
    updated_at: null,
  },
  {
    scholar_id: "demo:scholar/05",
    name_zh: "沈听澜",
    name_en: "Tinglan Shen",
    avatar_path: null,
    affiliations: [
      { institution: "星澜大学 · 智能科学学院", position: "博士研究生" },
    ],
    bio_zh:
      "正在探索面向日常操作任务的机器人学习方法，关注低成本设备上的数据采集与策略学习。",
    bio_en: null,
    metrics: { paper_count: 0, citation_count: 0 },
    annual_citations: [],
    updated_at: null,
  },
  {
    // 含保留字符和字面百分号的 opaque ID，禁止按姓名重建或重复解码。
    scholar_id: "demo:scholar/06?key=%2F",
    name_zh: "周予安",
    name_en: null,
    avatar_path: null,
    affiliations: [],
    bio_zh: null,
    bio_en: null,
    metrics: { paper_count: null, citation_count: null },
    annual_citations: [],
    updated_at: null,
  },
];

/** 只保存关联 ID，论文元数据复用 clients/knowledge/mock-data，不依赖姓名匹配。 */
export const DEMO_SCHOLAR_PAPER_IDS: Record<string, string[]> = {
  "demo:scholar/01": ["p-diffusion-policy", "p-act", "p-rt-1"],
  "demo:scholar/02": ["p-rt-1", "p-rt-2"],
  "demo:scholar/03": ["p-iql", "p-diffuser"],
  "demo:scholar/04": ["p-diffuser"],
};
