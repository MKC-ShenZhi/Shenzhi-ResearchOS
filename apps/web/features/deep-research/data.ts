/**
 * Deep Research mock 数据 —— 确定性、无随机(跟随 auto-research 惯例)
 * 内容主题沿用扩散模型语境,与 /agents/deep-search 页演示数据一致
 */
import type {
  DRHistoryItem,
  DRPlanSection,
  DRReport,
  DRStepEvent,
} from "@/types";

/** 研究计划:4 节大纲,节状态由事件流派生 */
export const drPlan: DRPlanSection[] = [
  { id: "s1", title: "1. 代表性方法与技术脉络", query: "diffusion policy robot manipulation 代表工作" },
  { id: "s2", title: "2. 性能对比与评测基准", query: "diffusion policy benchmark 成功率 对比" },
  { id: "s3", title: "3. 工业部署现状与瓶颈", query: "diffusion policy 工业部署 延迟 算力" },
  { id: "s4", title: "4. 趋势展望与研究方向", query: "VLA 基础模型 扩散策略 融合趋势" },
];

/** 报告全文(摘要 + 4 节 + 15 条参考文献) */
export const drReport: DRReport = {
  question:
    "扩散模型在机器人策略学习中最近 6 个月有哪些突破性进展?请对比主流方法,并分析对实际工业部署的影响。",
  title: "扩散模型在机器人策略学习中的最新进展",
  abstract:
    "本报告调研了 28 篇文献:梳理从 Diffusion Policy 到 RDT-1B 的技术脉络,对比主流方法在公开基准上的性能,分析工业部署的实时性与算力瓶颈,并给出 VLA 融合等下一步研究方向。",
  stats: { read: 28, cited: 15 },
  sections: [
    {
      id: "s1",
      heading: "1. 代表性方法与技术脉络",
      paragraphs: [
        "过去 6 个月,扩散策略 (Diffusion Policy) [1] 在机器人操控领域已经从学术原型走向工业验证。核心进展可以归纳为三条主线:动作分块 (Action Chunking) 与时序一致性优化、跨本体数据融合,以及面向真实硬件的延迟压缩。",
        "Chi 等人的 Diffusion Policy [1] 首次将 DDPM 引入动作空间预测,奠定了 chunk-based 扩散策略的范式;动作分块的思想可追溯至 ACT [14] 的时序集成;之后的 3D Diffusion Policy (DP3) [2] 通过稀疏体素特征将推理扩展到 6 自由度操作;最近的 RDT-1B [3] 与 NVIDIA 的 DexMamba [4] 则把模型规模推到十亿参数,并在跨本体迁移上取得显著增益。",
      ],
    },
    {
      id: "s2",
      heading: "2. 性能对比与评测基准",
      paragraphs: [
        "在 5 个公开基准(含 DROID [10] 真实场景子集)上,主流扩散策略的平均成功率与推理开销如下。可以看到,参数量的增长带来了显著的成功率收益,但推理延迟同步上升,这是工业部署的核心矛盾。",
      ],
      table: {
        caption: "性能对比(在 5 个公开基准上)",
        header: ["方法", "平均成功率", "参数量", "推理延迟"],
        rows: [
          ["Diffusion Policy [1]", "62.4%", "73M", "48ms / chunk"],
          ["DP3 [2]", "71.8%", "180M", "62ms / chunk"],
          ["RDT-1B [3]", "84.6%", "1.2B", "94ms / chunk"],
        ],
        highlightRow: 2,
      },
    },
    {
      id: "s3",
      heading: "3. 工业部署现状与瓶颈",
      paragraphs: [
        "工业部署方面,BMW 与 Figure 的产线实测 [5] 表明:扩散策略在多 SKU 装配任务上比传统 Behavior Cloning 高 28% 成功率,但对硬件算力要求较高(≥ RTX 4090 级别 GPU 才能满足 60Hz 控制频率 [6])。",
        "实时性方面,RTC [6] 通过异步动作分块与推理流水线将端到端延迟压到 20ms 以内;UMI [15] 则提供了低成本的跨本体数据采集路径,缓解了真机数据瓶颈。",
      ],
    },
    {
      id: "s4",
      heading: "4. 趋势展望与研究方向",
      paragraphs: ["综合 28 篇文献,三条趋势值得关注:"],
      list: [
        "模型规模从百 M 走向十亿级,与大语言模型的融合成为新方向 (PaLM-E [7]、RT-2 [12])。",
        "动作分块从 8 步扩展到 64 步,时序一致性约束 (TCP [8]) 显著降低了抖动。",
        "与 VLA 模型 (Vision-Language-Action) 深度结合,出现通用机器人基础模型 (Octo [9]、OpenVLA [11]、π0 [13])。",
      ],
    },
  ],
  references: [
    { id: 1, short: "Diffusion Policy", title: "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion", venue: "CoRL 2024 · Stanford", author: "Chi et al.", citations: "引用 1.8k" },
    { id: 2, short: "DP3", title: "3D Diffusion Policy: Generalizable Visuomotor Policy Learning via Sparse 3D Representation", venue: "RSS 2025 · MIT", author: "Ze et al.", citations: "引用 642" },
    { id: 3, short: "RDT-1B", title: "RDT-1B: A Diffusion Foundation Model for Robotic Manipulation", venue: "ICML 2026 · 推荐", author: "Liu et al.", citations: "引用 312", recommended: true },
    { id: 4, short: "DexMamba", title: "DexMamba: 面向灵巧手控制的视觉状态空间扩散模型", venue: "arXiv 2026 · NVIDIA", author: "Wen et al.", citations: "引用 89" },
    { id: 5, short: "产线实测", title: "Diffusion Policies on the Factory Floor: A Multi-SKU Assembly Field Study", venue: "Case Study 2026 · BMW / Figure", author: "Huber et al.", citations: "引用 45" },
    { id: 6, short: "RTC", title: "Real-Time Chunking: 面向 60Hz 控制的扩散推理压缩", venue: "arXiv 2026 · ETH Zurich", author: "Schmid et al.", citations: "引用 27" },
    { id: 7, short: "PaLM-E", title: "PaLM-E: An Embodied Multimodal Language Model", venue: "ICML 2023 · Google", author: "Driess et al.", citations: "引用 2.4k" },
    { id: 8, short: "TCP", title: "Temporally Consistent Policy Chunks for Manipulation", venue: "NeurIPS 2025 · THU", author: "Zhao et al.", citations: "引用 156" },
    { id: 9, short: "Octo", title: "Octo: An Open-Source Generalist Robot Policy", venue: "RSS 2024 · UC Berkeley", author: "Octo Model Team", citations: "引用 980" },
    { id: 10, short: "DROID", title: "DROID: A Large-Scale In-the-Wild Robot Manipulation Dataset", venue: "RA-L 2024 · Stanford", author: "Khazatsky et al.", citations: "引用 720" },
    { id: 11, short: "OpenVLA", title: "OpenVLA: An Open-Source Vision-Language-Action Model", venue: "CoRL 2024 · Stanford", author: "Kim et al.", citations: "引用 540" },
    { id: 12, short: "RT-2", title: "RT-2: Vision-Language-Action Models Transfer Web Knowledge", venue: "CoRL 2023 · Google DeepMind", author: "Brohan et al.", citations: "引用 1.5k" },
    { id: 13, short: "π0", title: "π0: A Vision-Language-Action Flow Model for General Robot Control", venue: "arXiv 2024 · Physical Intelligence", author: "Black et al.", citations: "引用 410" },
    { id: 14, short: "ACT", title: "Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware", venue: "RSS 2023 · Stanford", author: "Zhao et al.", citations: "引用 1.1k" },
    { id: 15, short: "UMI", title: "Universal Manipulation Interface: In-the-Wild Robot Teaching", venue: "RSS 2024 · Stanford", author: "Chi et al.", citations: "引用 380" },
  ],
};

/**
 * 预录步骤事件流 —— 总时长约 12s
 * (plan_ready 由初始态表达,done 由播完推导,均不占事件)
 */
export const drEvents: DRStepEvent[] = [
  { offsetMs: 900, kind: "search", label: "检索「diffusion policy robot manipulation」· 命中 32 个来源" },
  { offsetMs: 2500, kind: "search", label: "扩展检索「VLA / 世界模型 技术路线」· 补入 14 个来源" },
  { offsetMs: 4200, kind: "read", label: "去重、按引用量与时效加权,精读 28 篇" },
  { offsetMs: 5600, kind: "analyze", label: "按方法谱系聚类,归纳 3 条技术主线" },
  { offsetMs: 6800, kind: "write", sectionId: "s1", label: "撰写第 1 节 · 代表性方法与技术脉络" },
  { offsetMs: 8000, kind: "write", sectionId: "s2", label: "撰写第 2 节 · 性能对比与评测基准" },
  { offsetMs: 9200, kind: "write", sectionId: "s3", label: "撰写第 3 节 · 工业部署现状与瓶颈" },
  { offsetMs: 10400, kind: "write", sectionId: "s4", label: "撰写第 4 节 · 趋势展望与研究方向" },
  { offsetMs: 11300, kind: "analyze", label: "交叉核对引用,生成参考文献列表(15 篇)" },
];

/** 运行总时长(末尾事件 + 缓冲) */
export const DR_RUN_TOTAL_MS = 12000;

/** 入口态:历史研究(全部加载同一份示例报告) */
export const drHistory: DRHistoryItem[] = [
  { id: "dr1", title: "扩散模型在机器人策略学习中的进展", status: "已完成", sources: 28, time: "昨天" },
  { id: "dr2", title: "具身智能中的世界模型综述", status: "进行中", sources: 17, time: "2 天前" },
  { id: "dr3", title: "Mamba 与状态空间模型在控制中的应用", status: "已完成", sources: 31, time: "上周" },
  { id: "dr4", title: "稀疏注意力机制系统对比", status: "已完成", sources: 9, time: "2 周前" },
];

/** 入口态:建议主题(点击填入输入框) */
export const drSuggestions = [
  "扩散策略在工业部署中的现状与瓶颈",
  "世界模型与 VLA 技术路线有什么差异?",
  "具身智能评测基准的最新综述",
];

/** 入口态:研究范围选项(单选,纯展示) */
export const drScopeOptions = ["全网文献", "我的知识库", "近 12 个月"];
