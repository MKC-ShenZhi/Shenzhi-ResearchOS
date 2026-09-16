import type { FeedPaper } from "@/types";

/** 主发现页 Feed 流 —— 内容提取自「深知-主发现页.svg」 */
export const feedPapers: FeedPaper[] = [
  {
    id: "ultralong-1m",
    date: "2026-07-25",
    venue: "ICML 2026 · Oral",
    venueTone: "violet",
    authors: "Wei-Lin Chiang · Zhuohan Li · et al. (UC Berkeley)",
    title:
      "UltraLong-1M: 一个面向百万级 Token 推理的自回归 Transformer 长程记忆机制",
    abstract:
      "UltraLong-1M 提出了一个分层的键值压缩与稀疏注意力机制,使 8B 参数的 Transformer 能在单张 H100 上稳定训练 1M Token 上下文。在 LongBench v2 与 RULER 上分别取得 78.3 与 91.4 分,相对 Llama-3-8B-1M 提升 12.7 分,训练成本下降 41%。",
    aiLink: "AI 深度解读",
    tags: ["长上下文", "Transformer", "稀疏注意力"],
    likes: 428,
    citations: 354,
    thumb: "论文摘要图",
  },
  {
    id: "sana-video-2",
    date: "2026-07-24",
    venue: "arXiv · cs.CV",
    venueTone: "amber",
    authors: "Junsong Chen · Jincheng Yu · Yitong Li (NVIDIA)",
    title:
      "SANA-Video 2.0: 基于混合线性注意力与残差机制的高效视频扩散 Transformer",
    abstract:
      "NVIDIA 的 SANA-Video 2.0 引入混合线性注意力与周期性 softmax 锚点机制,5B 参数模型在单张 H100 GPU 上 13.2 秒生成 81 帧视频,VBench 总分 84.30,相对全 softmax 基线实现 3.2 倍 DiT 前向加速。",
    aiLink: "查看解读",
    tags: ["视频生成", "扩散模型", "线性注意力"],
    likes: 196,
    citations: 293,
    thumb: "视频生成架构图",
  },
  {
    id: "arex",
    date: "2026-07-23",
    venue: "ICLR 2026",
    venueTone: "green",
    authors: "Yifei Ming · Sumanth Dathathri · et al. (Stanford)",
    title: "AREX: 面向深度研究的递归自我进化智能体",
    abstract:
      "AREX 提出了一种递归自进化机制:智能体在每次研究循环后自动重写自身的工具策略与检索流程,连续 4 轮迭代后在 DeepResearch Bench 上达到 73.8 分,相对静态智能体基线提升 19.2 分。",
    aiLink: "智能体实验记录",
    tags: ["智能体", "递归学习"],
    likes: 112,
    citations: 218,
    thumb: "智能体流程图",
  },
];
