/**
 * 知识底座前端 Mock 数据集。
 *
 * 仅用于页面与交互开发；真实联调时由 BffKnowledgeClient 取代。
 * 数据契约与 clients/knowledge/types.ts 保持一致。
 */
import type {
  KnowledgeGraph,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgePaperDetail,
  KnowledgeTopic,
} from "./types";

/** 主题广场第一阶段 fixture；后端联调时由主题接口替换。 */
export const MOCK_TOPICS: KnowledgeTopic[] = [
  {
    id: "deep-learning",
    imagePath: "/images/topics/deep-learning-cover.png",
    nameZh: "深度学习",
    nameEn: "Deep Learning",
    author: "shenzhi",
    descriptionZh: "关注深层神经网络、表示学习与训练方法的研究进展。",
    descriptionEn: "Research on deep neural networks, representation learning, and training methods.",
    followersCount: 32,
    category: "机器学习",
    subjectQuery: "deep learning",
    paperCount: 25,
    enabled: true,
  },
  {
    id: "reinforcement-learning",
    imagePath: "/images/topics/reinforcement-learning-cover.png",
    nameZh: "强化学习",
    nameEn: "Reinforcement Learning",
    author: "shenzhi",
    descriptionZh: "研究智能体如何利用环境反馈学习决策，在不确定环境中规划长期策略，并通过试错、价值估计与策略优化持续提升行为表现。",
    descriptionEn: "How agents learn decisions and long-horizon strategies from environmental feedback.",
    followersCount: 18,
    category: "机器学习",
    subjectQuery: "reinforcement learning",
    paperCount: 661,
    enabled: true,
  },
  {
    id: "representation-learning",
    imagePath: "/images/topics/representation-learning-cover.png",
    nameZh: "表示学习",
    nameEn: "Representation Learning",
    author: "shenzhi",
    descriptionZh: "探索从数据中学习有效特征、结构与可迁移表示的方法。",
    descriptionEn: "Methods for learning useful features, structures, and transferable representations.",
    followersCount: 14,
    category: "机器学习",
    subjectQuery: "representation learning",
    paperCount: 48,
    enabled: true,
  },
  {
    id: "transfer-learning",
    imagePath: "/images/topics/representation-learning-cover.png",
    nameZh: "迁移学习",
    nameEn: "Transfer Learning",
    author: "shenzhi",
    descriptionZh: "追踪跨任务、跨领域复用知识与适配模型的研究工作。",
    descriptionEn: "Reusing knowledge across tasks and domains through model adaptation.",
    followersCount: 9,
    category: "机器学习",
    subjectQuery: "transfer learning",
    paperCount: 22,
    enabled: true,
  },
  {
    id: "large-language-models",
    imagePath: "/images/topics/language-models-cover.png",
    nameZh: "大语言模型",
    nameEn: "Large Language Models",
    author: "shenzhi",
    descriptionZh: "聚焦语言模型的预训练、对齐、推理能力与应用边界。",
    descriptionEn: "Pre-training, alignment, reasoning, and applications of large language models.",
    followersCount: 46,
    category: "自然语言处理",
    subjectQuery: "llm",
    paperCount: 2225,
    enabled: true,
  },
  {
    id: "retrieval-augmented-generation",
    imagePath: "/images/topics/language-models-cover.png",
    nameZh: "检索增强生成",
    nameEn: "Retrieval-Augmented Generation",
    author: "shenzhi",
    descriptionZh: "研究外部知识检索与生成模型结合的系统、评测与可靠性。",
    descriptionEn: "Systems, evaluation, and reliability of retrieval-augmented generation.",
    followersCount: 27,
    category: "自然语言处理",
    subjectQuery: "retrieval augmented generation",
    paperCount: 232,
    enabled: true,
  },
  {
    id: "machine-translation",
    imagePath: "/images/topics/translation-cover.png",
    nameZh: "机器翻译",
    nameEn: "Machine Translation",
    author: "shenzhi",
    descriptionZh: "汇集神经机器翻译、多语言建模与低资源翻译研究。",
    descriptionEn: "Neural machine translation, multilingual modeling, and low-resource translation.",
    followersCount: 11,
    category: "自然语言处理",
    subjectQuery: "translation",
    paperCount: 47,
    enabled: true,
  },
];

export interface MockPaperRecord {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  year: number;
  venue: string;
  doi: string | null;
  pdfUrl: string | null;
  keywords: string[];
  subjects: string[];
  citationCount: number | null;
  referenceCount: number | null;
  /** 引用关系：本论文引用的其他论文 id（References） */
  cites: string[];
}

/** 论文库（Diffusion Policy / 机器人操作方向示例） */
export const MOCK_PAPERS: MockPaperRecord[] = [
  {
    id: "p-diffusion-policy",
    title: "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion",
    abstract:
      "We introduce Diffusion Policy, a new way of learning robotic visuomotor policies. We formulate visuomotor policy learning as a conditional denoising diffusion process, which generates the action sequence conditioned on the visual observations. Diffusion policy is highly expressive in modeling complex and multimodal action distributions, while remaining easy to train and robust to high-dimensional action spaces.",
    authors: ["Cheng Chi", "Siyuan Feng", "Yilun Du", "Zhenjia Xu", "Eric Cousineau", "Benjamin Burchfiel", "Shuran Song"],
    year: 2023,
    venue: "RSS",
    doi: "10.15607/rss.2023.xix.079",
    pdfUrl: "https://arxiv.org/pdf/2303.04137",
    keywords: ["Diffusion Policy", "Visuomotor Policy", "Action Chunking"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 1200,
    referenceCount: 58,
    cites: ["p-act", "p-bc-transformer", "p-diffuser", "p-iql", "p-rt-1"],
  },
  {
    id: "p-act",
    title: "Learning Precise Pick-and-Place with a Minimalist Dual-Arm Robot",
    abstract:
      "We present Action Chunking with Transformers (ACT), a formulation for learning visuomotor policies for precise manipulation tasks. ACT learns a generative model of action sequences with a transformer, achieving precise and robust pick-and-place performance on a low-cost dual-arm robot.",
    authors: ["Tony Z. Zhao", "Vijay Kumar", "Sergey Levine", "Chelsea Finn"],
    year: 2023,
    venue: "ICRA",
    doi: "10.1109/icra48891.2023.10160523",
    pdfUrl: "https://arxiv.org/pdf/2304.13705",
    keywords: ["Action Chunking", "Transformers", "Imitation Learning"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 860,
    referenceCount: 41,
    cites: ["p-diffuser", "p-iql", "p-bc-transformer"],
  },
  {
    id: "p-rt-1",
    title: "RT-1: Robotics Transformer for Real-World Control at Scale",
    abstract:
      "RT-1 is a multi-task transformer that enables a mobile manipulator to execute hundreds of everyday household tasks from natural language and image observations. It is trained on a large-scale dataset collected with a fleet of robots and generalizes to novel instructions and environments.",
    authors: ["Anthony Brohan", "Noah Brown", "James Carbajal", "Yevgen Chebotar", "Joseph Dabis", "Chelsea Finn"],
    year: 2023,
    venue: "RSS",
    doi: "10.15607/rss.2023.xix.033",
    pdfUrl: "https://arxiv.org/pdf/2212.06817",
    keywords: ["Robotics Transformer", "Multi-task", "Language"],
    subjects: ["Robotics", "Vision-Language"],
    citationCount: 980,
    referenceCount: 62,
    cites: ["p-act", "p-bc-transformer", "p-diffuser"],
  },
  {
    id: "p-rt-2",
    title: "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
    abstract:
      "We study how vision-language models trained on internet-scale data can be transferred directly to robotic control. RT-2 shows improved generalization and emergent capabilities, enabling robots to reason about novel objects and instructions grounded in web knowledge.",
    authors: ["Anthony Brohan", "Noah Brown", "James Carbajal", "Yevgen Chebotar", "Xi Chen", "Chelsea Finn"],
    year: 2023,
    venue: "arXiv",
    doi: "10.48550/arXiv.2307.15818",
    pdfUrl: "https://arxiv.org/pdf/2307.15818",
    keywords: ["Vision-Language-Action", "Co-training", "Emergent Capability"],
    subjects: ["Robotics", "Vision-Language"],
    citationCount: 620,
    referenceCount: 45,
    cites: ["p-rt-1", "p-diffusion-policy", "p-act"],
  },
  {
    id: "p-bc-transformer",
    title: "Robust Manipulation with Transformer-Based Behavior Cloning",
    abstract:
      "We show that a single transformer-based behavior cloning model can acquire diverse manipulation skills from offline data and exhibit robustness to visual distractors and unseen task configurations in real-world evaluation.",
    authors: ["Shagun Uppal", "Ananye Agarwal", "Jitendra Malik"],
    year: 2023,
    venue: "RSS",
    doi: "10.15607/rss.2023.xix.015",
    pdfUrl: "https://arxiv.org/pdf/2303.08319",
    keywords: ["Behavior Cloning", "Transformers", "Robustness"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 240,
    referenceCount: 36,
    cites: ["p-diffuser", "p-iql"],
  },
  {
    id: "p-3d-diffusion-policy",
    title: "3D Diffusion Policy: Generalizable Visuomotor Policy Learning via Simple 3D Representations",
    abstract:
      "We introduce 3D Diffusion Policy (DP3), which leverages simple 3D visual representations, such as point clouds, with diffusion policies. DP3 achieves strong generalization across diverse manipulation tasks with only a small number of demonstrations.",
    authors: ["Yanjie Ze", "Gu Zhang", "Kangning Zhang", "Chenyuan Hu", "Muhan Wang", "Huazhe Xu"],
    year: 2024,
    venue: "RSS",
    doi: "10.15607/rss.2024.xix.027",
    pdfUrl: "https://arxiv.org/pdf/2403.03954",
    keywords: ["3D Representations", "Diffusion Policy", "Generalization"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 380,
    referenceCount: 50,
    cites: ["p-diffusion-policy", "p-vqbet", "p-act"],
  },
  {
    id: "p-vqbet",
    title: "VQ-BeT: Behavior Generation with Latent Actions",
    abstract:
      "We propose VQ-BeT, a behavior generation method that combines a tokenizer learning latent actions with a transformer for behavior prediction, enabling multimodal action generation for embodied agents.",
    authors: ["Seungjae Lee", "Yibin Wang", "Haritheja Etukuru", "H. Jin Kim", "Nur Muhammad Mahi Shafiullah", "Lerrel Pinto"],
    year: 2024,
    venue: "ICRA",
    doi: "10.1109/icra57147.2024.10611507",
    pdfUrl: "https://arxiv.org/pdf/2403.17481",
    keywords: ["Latent Actions", "Behavior Generation", "Tokenizer"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 120,
    referenceCount: 38,
    cites: ["p-diffusion-policy", "p-bc-transformer", "p-diffuser"],
  },
  {
    id: "p-diffuser",
    title: "Diffuser: Diffusion Models as Planning",
    abstract:
      "We cast planning as a conditional sampling problem using diffusion models. Diffuser generates entire trajectories and enables long-horizon planning that can be repurposed to solve a range of control tasks.",
    authors: ["Michael Janner", "Yilun Du", "Joshua B. Tenenbaum", "Sergey Levine"],
    year: 2022,
    venue: "ICLR",
    doi: "10.48550/arXiv.2201.09707",
    pdfUrl: "https://arxiv.org/pdf/2201.09707",
    keywords: ["Diffusion Models", "Planning", "Trajectory Generation"],
    subjects: ["Reinforcement Learning", "Planning"],
    citationCount: 950,
    referenceCount: 55,
    cites: ["p-iql"],
  },
  {
    id: "p-iql",
    title: "Offline Reinforcement Learning with Implicit Q-Learning",
    abstract:
      "We introduce Implicit Q-Learning (IQL), an offline reinforcement learning algorithm that avoids querying actions outside of the dataset and learns a value function that is robust to distributional shift.",
    authors: ["Ilya Kostrikov", "Ashvin Nair", "Sergey Levine"],
    year: 2022,
    venue: "ICLR",
    doi: "10.48550/arXiv.2110.06169",
    pdfUrl: "https://arxiv.org/pdf/2110.06169",
    keywords: ["Offline RL", "Implicit Q-Learning", "Value Function"],
    subjects: ["Reinforcement Learning"],
    citationCount: 1100,
    referenceCount: 47,
    cites: ["p-diffuser"],
  },
  {
    id: "p-mobile-aloha",
    title: "Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware",
    abstract:
      "We present Mobile ALOHA, a low-cost and whole-body teleoperation system for data collection, and demonstrate that co-training with static ALOHA data enables learning of complex bimanual mobile manipulation skills.",
    authors: ["Zipeng Fu", "Tony Z. Zhao", "Chelsea Finn"],
    year: 2024,
    venue: "RSS",
    doi: "10.15607/rss.2024.xix.033",
    pdfUrl: "https://arxiv.org/pdf/2401.02117",
    keywords: ["Bimanual Manipulation", "Teleoperation", "Imitation Learning"],
    subjects: ["Robotics", "Imitation Learning"],
    citationCount: 560,
    referenceCount: 39,
    cites: ["p-diffusion-policy", "p-act", "p-rt-1"],
  },
];

/** 图谱节点（Paper 之外的类型） */
/** 已知作者 → 机构（用于图谱机构节点，未列出的作者不生成机构） */
const AUTHOR_INSTITUTIONS: Record<string, string> = {
  "Cheng Chi": "Columbia University",
  "Shuran Song": "Columbia University",
  "Tony Z. Zhao": "Stanford University",
  "Zipeng Fu": "Stanford University",
  "Chelsea Finn": "UC Berkeley",
  "Sergey Levine": "UC Berkeley",
  "Jitendra Malik": "UC Berkeley",
};

const PAPER_BY_ID = new Map(MOCK_PAPERS.map((paper) => [paper.id, paper]));

/** 文本 → 节点 id 用的 slug（小写 + 短横线） */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function paperNode(paper: MockPaperRecord): KnowledgeGraphNode {
  return {
    id: paper.id,
    kind: "Paper",
    label: paper.title,
    properties: {
      year: paper.year,
      venue: paper.venue,
      abstract: paper.abstract,
      authors: paper.authors,
      doi: paper.doi,
      pdfUrl: paper.pdfUrl,
      keywords: paper.keywords,
      external: false,
    },
    provenance: { source: "mock" },
  };
}

/**
 * 为任意论文生成 depth=1 关系图谱（Mock）。
 * 未在数据集中找到论文时返回 null（对应 NOT_FOUND）。
 *
 * 生成内容：root 论文 + 其引用论文（References）+ 引用它的论文（Citations）
 * + 作者（Author）+ 机构（Institution）+ 会议（Venue）+ 关键词/学科（Topic）。
 */
export function buildMockGraph(paperId: string): KnowledgeGraph | null {
  const root = PAPER_BY_ID.get(paperId);
  if (!root) return null;

  const nodes: KnowledgeGraphNode[] = [];
  const edges: KnowledgeGraphEdge[] = [];
  const seen = new Set<string>();

  const addNode = (node: KnowledgeGraphNode) => {
    if (seen.has(node.id)) return;
    seen.add(node.id);
    nodes.push(node);
  };
  const addEdge = (edge: Omit<KnowledgeGraphEdge, "provenance">) => {
    edges.push({ ...edge, provenance: { source: "mock" } });
  };

  addNode(paperNode(root));

  // References：root 引用的论文（sourceId === rootId）
  for (const refId of root.cites) {
    const ref = PAPER_BY_ID.get(refId);
    if (!ref) continue;
    addNode(paperNode(ref));
    addEdge({ sourceId: root.id, targetId: ref.id, relation: "CITES", description: "引用", weight: 0.85 });
  }

  // Citations：引用 root 的论文（targetId === rootId）
  for (const paper of MOCK_PAPERS) {
    if (paper.id === root.id) continue;
    if (paper.cites.includes(root.id)) {
      addNode(paperNode(paper));
      addEdge({ sourceId: paper.id, targetId: root.id, relation: "CITES", description: "被引用", weight: 0.75 });
    }
  }

  // 作者（AUTHORED_BY）+ 机构（AFFILIATED_WITH）
  root.authors.forEach((author, index) => {
    const authorId = `a-${slugify(author)}`;
    addNode({ id: authorId, kind: "Author", label: author, properties: {}, provenance: { source: "mock" } });
    addEdge({ sourceId: root.id, targetId: authorId, relation: "AUTHORED_BY", description: index === 0 ? "第一作者" : "作者", weight: 1 });

    const institution = AUTHOR_INSTITUTIONS[author];
    if (institution) {
      const institutionId = `i-${slugify(institution)}`;
      addNode({ id: institutionId, kind: "Institution", label: institution, properties: {}, provenance: { source: "mock" } });
      addEdge({ sourceId: authorId, targetId: institutionId, relation: "AFFILIATED_WITH", description: "所属机构", weight: 1 });
    }
  });

  // 会议（PUBLISHED_IN）
  if (root.venue) {
    const venueId = `v-${slugify(root.venue)}`;
    addNode({ id: venueId, kind: "Venue", label: root.venue, properties: { year: root.year }, provenance: { source: "mock" } });
    addEdge({ sourceId: root.id, targetId: venueId, relation: "PUBLISHED_IN", description: "发表会议", weight: 1 });
  }

  // 关键词 / 学科 → 主题（HAS_TOPIC）
  [...root.keywords, ...root.subjects].forEach((topic, index) => {
    const topicId = `t-${slugify(topic)}`;
    addNode({ id: topicId, kind: "Topic", label: topic, properties: {}, provenance: { source: "mock" } });
    addEdge({ sourceId: root.id, targetId: topicId, relation: "HAS_TOPIC", description: "研究主题", weight: index < root.keywords.length ? 0.85 : 0.7 });
  });

  return { rootId: root.id, nodes, edges };
}

/** 根论文关系图谱（兼容旧引用；等价于 buildMockGraph(根)） */
export const MOCK_GRAPH: KnowledgeGraph = (() => {
  const graph = buildMockGraph("p-diffusion-policy");
  if (!graph) throw new Error("mock root paper missing");
  return graph;
})();

export function mockPaperDetail(id: string): KnowledgePaperDetail | null {
  const paper = PAPER_BY_ID.get(id);
  if (!paper) return null;
  return {
    id: paper.id,
    title: paper.title,
    abstract: paper.abstract,
    authors: paper.authors,
    year: paper.year,
    venue: paper.venue,
    doi: paper.doi,
    pdfUrl: paper.pdfUrl,
    keywords: paper.keywords,
    subjects: paper.subjects,
    citationCount: paper.citationCount,
    referenceCount: paper.referenceCount,
    provenance: { source: "mock" },
  };
}
