import type { LibraryFolder, LibraryItem } from "@/types";

/** 知识库文件夹 —— 内容提取自「深知-知识库页面.svg」 */
export const libraryFolders: LibraryFolder[] = [
  { name: "我的发表", count: 3 },
  { name: "想读", count: 8 },
  { name: "在读", count: 12, active: true },
  { name: "已读", count: 47 },
  { name: "归档", count: 23 },
];

export const libraryTags = ["扩散模型", "Transformer", "智能体", "视频生成", "长上下文"];

export const libraryItems: LibraryItem[] = [
  {
    id: "lib-1",
    title: "Diffusion Models for Iterative Video Frame Interpolation",
    venue: "CVPR 2025",
    arxiv: "arXiv:2406.12345",
    authors: "Zhang Wei, Chen Li, Wang Ming",
    addedAt: "7月25日",
    pdfTone: "violet",
  },
  {
    id: "lib-2",
    title: "LLM Agents for Autonomous Scientific Discovery",
    venue: "NeurIPS 2024",
    arxiv: "arXiv:2411.08901",
    authors: "Li Ming, Chen Hao, Liu Yu",
    addedAt: "7月22日",
    pdfTone: "amber",
  },
  {
    id: "lib-3",
    title: "Long-Context Reasoning in Foundation Models",
    venue: "ICLR 2025",
    arxiv: "arXiv:2501.04567",
    authors: "Wang Hao, Liu Yang, Zhou Tong",
    addedAt: "7月18日",
    pdfTone: "green",
  },
];
