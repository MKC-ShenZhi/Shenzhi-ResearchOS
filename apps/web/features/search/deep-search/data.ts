import type { AgentReference, RecentResearch } from "@/types";

/** AI 研究助手 —— 内容提取自「深知-AI研究助手.svg」 */
export const agentSession = {
  topic: "扩散模型在机器人策略学习中的最新进展",
  mode: "深度研究 · 自动更新中",
  question:
    "扩散模型在机器人策略学习中最近 6 个月有哪些突破性进展?请对比主流方法,并分析对实际工业部署的影响。",
  meta: "已阅读 28 篇论文 · 耗时 4.2s",
};

export const recentResearch: RecentResearch[] = [
  { id: "r1", title: "扩散模型综述", time: "刚刚", refs: 18, active: true },
  { id: "r2", title: "具身智能中的世界模型", time: "昨天", refs: 24 },
  { id: "r3", title: "Mamba 与状态空间模型", time: "2 天前", refs: 31 },
  { id: "r4", title: "稀疏注意力机制对比", time: "上周", refs: 9 },
];

export const answerBlocks = {
  intro:
    "过去 6 个月,扩散策略 (Diffusion Policy) [1] 在机器人操控领域已经从学术原型走向工业验证。核心进展可以归纳为三条主线:动作分块 (Action Chunking) 与时序一致性优化、跨本体数据融合,以及面向真实硬件的延迟压缩。",
  methodHeading: "1. 代表性方法与对比",
  methodBody:
    "Chi 等人的 Diffusion Policy [1] 首次将 DDPM 引入动作空间预测,奠定了 chunk-based 扩散策略的范式;之后的 3D Diffusion Policy (DP3) [2] 通过稀疏体素特征将推理扩展到 6 自由度操作;最近的 RDT-1B [3] 与 NVIDIA 的 DexMamba [4] 则把模型规模推到十亿参数,并在跨本体迁移上取得显著增益。",
  tableCaption: "性能对比(在 5 个公开基准上)",
  table: {
    header: ["方法", "平均成功率", "参数量", "推理延迟"],
    rows: [
      ["Diffusion Policy [1]", "62.4%", "73M", "48ms / chunk"],
      ["DP3 [2]", "71.8%", "180M", "62ms / chunk"],
      ["RDT-1B [3]", "84.6%", "1.2B", "94ms / chunk"],
    ],
    highlightRow: 2,
  },
  industryBody:
    "工业部署方面,BMW 与 Figure 的产线实测 [5] 表明:扩散策略在多 SKU 装配任务上比传统 Behavior Cloning 高 28% 成功率,但对硬件算力要求较高(≥ RTX 4090 级别 GPU 才能满足 60Hz 控制频率 [6])。",
  trendHeading: "2. 关键趋势与下一步",
  trends: [
    "模型规模从百 M 走向十亿级,与大语言模型的融合成为新方向 (PaLM-E [7]、RT-2)。",
    "动作分块从 8 步扩展到 64 步,时序一致性约束 (TCP [8]) 显著降低了抖动。",
    "与 VLA 模型 (Vision-Language-Action) 深度结合,出现通用机器人基础模型 (Octo [9]、OpenVLA)。",
  ],
  conclusion:
    "综上,扩散策略已从研究阶段进入工业可用阶段,建议关注 RDT-1B 系列工作与跨本体数据集 (如 DROID [10]) 的进展。",
};

export const agentReferences: AgentReference[] = [
  {
    id: 1,
    venue: "CoRL 2024 · Stanford",
    title: "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion",
    author: "Chi et al.",
    citations: "引用 1.8k",
    tone: "violet",
  },
  {
    id: 2,
    venue: "RSS 2025 · MIT",
    title: "3D Diffusion Policy: Generalizable Visuomotor Policy Learning via Sparse 3D Representation",
    author: "Ze et al.",
    citations: "引用 642",
    tone: "green",
  },
  {
    id: 3,
    venue: "ICML 2026 · 推荐",
    title: "RDT-1B: A Diffusion Foundation Model for Robotic Manipulation",
    author: "Liu et al.",
    citations: "引用 312",
    tone: "amber",
    recommended: true,
  },
  {
    id: 4,
    venue: "arXiv 2026 · NVIDIA",
    title: "DexMamba: 面向灵巧手控制的视觉状态空间扩散模型",
    author: "Wen et al.",
    citations: "引用 89",
    tone: "gray",
  },
];

export const followUps = [
  "RDT-1B 与 Octo 的性能差异?",
  "动作分块的最佳长度是多少?",
  "DROID 数据集如何申请?",
  "工业部署的延迟瓶颈在哪?",
  "扩散策略与 VLA 模型融合趋势",
];
