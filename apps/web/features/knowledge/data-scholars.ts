import type { Publication, Scholar } from "@/types";

/** 学者卡片 —— 内容提取自「深知-学者画像页.svg」 */
export const scholars: Scholar[] = [
  {
    id: "kaiming-he",
    nameCn: "何恺明",
    nameEn: "Kaiming He",
    initials: "KH",
    avatarColor: "#174A7E",
    role: "副教授",
    affiliation: "MIT EECS · Google DeepMind Distinguished Scientist",
    bio: "ResNet 作者之一,提出了残差连接使训练百层深度网络成为可能;Masked Autoencoders (MAE) 通过像素重建推动视觉自监督学习。",
    citations: "849k",
    hIndex: 77,
    tags: ["计算机视觉", "深度学习", "表征学习"],
  },
  {
    id: "geoffrey-hinton",
    nameCn: "Geoffrey Hinton",
    nameEn: "杰弗里 · 辛顿",
    initials: "GH",
    avatarColor: "#10B981",
    role: "荣誉教授",
    affiliation: "多伦多大学 · 2024 诺贝尔物理学奖得主",
    bio: "深度学习之父,ImageNet 分类竞赛中使用 CNN 与 GPU 加速实现大规模图像识别;反向传播算法的共同发明人之一。",
    citations: "1.1M",
    hIndex: 192,
    tags: ["机器学习", "神经网络", "认知心理学"],
  },
  {
    id: "yoshua-bengio",
    nameCn: "Yoshua Bengio",
    nameEn: "约书亚 · 本吉奥",
    initials: "YB",
    avatarColor: "#F59E0B",
    role: "全职教授",
    affiliation: "蒙特利尔大学 · Mila 创始人",
    bio: "GAN 生成式对抗网络的共同提出者,使生成模型通过两个神经网络的对抗训练得以发展;深度学习三巨头之一。",
    citations: "1.1M",
    hIndex: 256,
    tags: ["机器学习", "深度学习", "NLP"],
    followed: true,
  },
  {
    id: "fei-fei-li",
    nameCn: "李飞飞",
    nameEn: "Fei-Fei Li",
    initials: "FL",
    avatarColor: "#EC4899",
    role: "教授",
    affiliation: "斯坦福大学 · 斯坦福 AI Lab 前主任",
    bio: "ImageNet 与 ImageNet Challenge 创始人,推动了大规模视觉数据集与深度学习结合;现从事空间智能与具身 AI 研究。",
    citations: "395k",
    hIndex: 168,
    tags: ["计算机视觉", "具身智能", "数据集构建"],
  },
  {
    id: "pieter-abbeel",
    nameCn: "Pieter Abbeel",
    nameEn: "阿比希尔",
    initials: "PA",
    avatarColor: "#8B5CF6",
    role: "教授",
    affiliation: "UC Berkeley · Covariant 创始人",
    bio: "强化学习与机器人学先驱,提出 TRPO/GAE 等算法奠定策略梯度基础;近年专注于工业机器人的通用基础模型。",
    citations: "186k",
    hIndex: 94,
    tags: ["强化学习", "机器人学", "策略学习"],
    followed: true,
  },
  {
    id: "ilya-sutskever",
    nameCn: "Ilya Sutskever",
    nameEn: "伊利亚",
    initials: "IS",
    avatarColor: "#06B6D4",
    role: "联合创始人",
    affiliation: "Safe Superintelligence Inc.",
    bio: "OpenAI 前首席科学家,ImageNet 分类核心贡献者;与 Sutskever 一起推动 AlexNet 引入 GPU 训练,开启深度学习革命。",
    citations: "830k",
    hIndex: 102,
    tags: ["机器学习", "神经网络", "AI 安全"],
  },
];

/** 研究方向筛选(学者画像页左侧) */
export const scholarDirections = [
  { name: "机器学习", count: "2.1k", color: "#5046E5" },
  { name: "计算机视觉", count: "1.5k", color: "#10B981" },
  { name: "自然语言处理", count: "1.2k", color: "#F59E0B" },
  { name: "强化学习", count: "624", color: "#EF4444" },
  { name: "机器人学", count: "412", color: "#8B5CF6" },
];

/** 学者详情(何恺明)—— 内容提取自「深知-学者详情页.svg」 */
export const scholarDetail = {
  id: "kaiming-he",
  location: "美国 · 马萨诸塞州剑桥",
  email: "kaiming@mit.edu",
  bio: [
    "何恺明的 ResNet 提出了残差连接,使训练百层深度的神经网络成为可能;他同时是 Faster R-CNN 的共同作者,把区域提议网络集成进端到端检测;近年提出的 Masked Autoencoders (MAE) 通过像素重建扩展了视觉自监督学习的边界。",
    "此前他曾担任 Facebook AI Research 研究科学家、Microsoft Research Asia 研究员。本科毕业于清华大学,博士毕业于香港中文大学。",
  ],
  introTags: ["计算机视觉", "深度学习", "自监督学习", "目标检测"],
  metrics: { totalCitations: "849,099", hIndex: 77, i10Index: 91 },
  yearlyCitations: {
    years: [
      "2015", "2016", "2017", "2018", "2019", "2020",
      "2021", "2022", "2023", "2024", "2025", "2026",
    ],
    values: [
      3200, 5100, 8400, 12600, 18900, 24500,
      31200, 38900, 44100, 52300, 58800, 63481,
    ],
    highlight: "63,481 · 2026",
  },
  links: ["Google Scholar", "个人主页", "GitHub", "发送邮件"],
  toc: [
    { id: "intro", label: "个人简介", active: true },
    { id: "works", label: "研究成果 · 84" },
    { id: "coauthors", label: "合作者" },
    { id: "activity", label: "学术活动" },
  ],
  publications: [
    {
      id: "resnet",
      title: "Deep Residual Learning for Image Recognition",
      abstract:
        "Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously. We explicitly reformulate the layers as learning residual functions with reference to the layer inputs, instead of learning unreferenced functions. …",
      authors: "Kaiming He, Xiangyu Zhang, Shaoqing Ren, Jian Sun",
      venue: "CVPR 2016",
      citations: "引用 218k",
      citationsShort: "12k",
    },
    {
      id: "mae",
      title: "Masked Autoencoders Are Scalable Vision Learners",
      abstract:
        "This paper shows that masked autoencoders (MAE) are scalable self-supervised learners for computer vision. Our MAE approach is simple: we mask random patches of the input image and reconstruct the missing pixels. …",
      authors: "Kaiming He, Xinlei Chen, Saining Xie, Yanghao Li, Piotr Dollár, Ross Girshick",
      venue: "CVPR 2022",
      citations: "引用 14.5k",
      citationsShort: "3.2k",
    },
    {
      id: "meanflow",
      title: "Improved Mean Flows: On the Challenges of Fastforward Generative Models",
      abstract:
        "MeanFlow (MF) has recently been established as a framework for one-step generative modeling. However, its fastforward nature introduces key challenges in both the training objective and the guidance mechanism. …",
      authors: "Zhengyang Geng, Yiyang Lu, Zongze Wu + 3 more",
      venue: "2026",
      citations: "引用 158",
      citationsShort: "39",
    },
  ] satisfies Publication[],
};
