import type { PaperDetail, SimilarPaper } from "@/types";

/** 论文阅读器 —— 内容提取自「深知-论文详情页.svg」(RDT-1B) */
export const paperDetail: PaperDetail = {
  id: "rdt-1b",
  title: "RDT-1B: A Diffusion Foundation Model for Robotic Manipulation",
  authors: [
    "Songming Liu",
    "Lingxuan Wu",
    "Bangguo Li",
    "Hengkai Tan",
    "Huayu Chen",
    "Zhengyi Wang",
    "Ke Xu",
    "Hang Su",
    "Jun Zhu",
  ],
  affiliation: "Tsinghua University · Shanghai AI Lab",
  likes: 428,
  page: { current: 1, total: 18 },
  toc: [
    { id: "abstract", label: "摘要 Abstract", active: true },
    { id: "intro", label: "1. 引言" },
    { id: "related", label: "2. 相关工作" },
    { id: "method", label: "3. 方法" },
    { id: "exp", label: "4. 实验" },
    { id: "conclusion", label: "5. 结论" },
  ],
  abstract:
    "We introduce RDT (Robotics Diffusion Transformer), a diffusion foundation model for robotic manipulation. RDT is pre-trained on the largest multi-robot dataset to date (DROID, 1.0M+ trajectories) and then fine-tuned on a target robot. With 1.2B parameters, RDT significantly outperforms existing methods such as Diffusion Policy and OpenVLA across 5 benchmarks and 60+ tasks, achieving a 14× increase in success rate on dexterous tasks and demonstrating strong generalization to unseen objects, scenes, and instructions.",
  introduction:
    "Recent advances in generative modeling have unlocked new capabilities in language and vision, yet robotics still relies heavily on task-specific imitation learning. We argue that the lack of large-scale, diverse robot data — not model architecture — is the primary bottleneck. RDT tackles this by training a 1.2B-parameter transformer-based diffusion model on the DROID corpus, then transferring to downstream robots via lightweight fine-tuning (≈ 2 GPU-hours).",
};

export const similarPapers: SimilarPaper[] = [
  {
    title:
      "Transformer-XL: Attentive Language Models Beyond a Fixed-Length Context",
    meta: "NeurIPS 2019 · Cited 2,341",
  },
  {
    title: "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
    meta: "arXiv 2019 · Cited 8,912",
  },
  {
    title:
      "XLNet: Generalized Autoregressive Pretraining for Language Understanding",
    meta: "NeurIPS 2019 · Cited 5,678",
  },
];

/** 领域相关作者 → 关联学者页(有主页的给链接) */
export const relatedAuthors: { name: string; scholarId?: string }[] = [
  { name: "Jacob Devlin" },
  { name: "Ashish Vaswani" },
  { name: "Zhilin Yang" },
  { name: "Yoshua Bengio", scholarId: "yoshua-bengio" },
  { name: "Geoffrey Hinton", scholarId: "geoffrey-hinton" },
  { name: "Yann LeCun" },
  { name: "Fei-Fei Li", scholarId: "fei-fei-li" },
];

export const additionalLinks = [
  "添加 GitHub 链接",
  "查看引用本论文的其他研究",
  "相关综述与文献综述",
  "社区讨论与延伸观点",
];
