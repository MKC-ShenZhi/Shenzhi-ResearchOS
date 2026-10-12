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
    "id": "reinforcement-learning",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "强化学习",
    "nameEn": "Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过智能体与环境交互并以奖励信号优化决策策略的机器学习方法。",
    "descriptionEn": "A machine learning method in which an agent learns decision policies by interacting with an environment and maximizing reward.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "reinforcement learning",
    "paperCount": 661,
    "enabled": true
  },
  {
    "id": "deep-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "深度学习",
    "nameEn": "Deep Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于多层神经网络自动学习层次化特征表示的机器学习方法。",
    "descriptionEn": "A machine learning method that learns hierarchical feature representations through multi-layer neural networks.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "deep learning",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "transfer-learning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "迁移学习",
    "nameEn": "Transfer Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将从源任务中学到的知识迁移应用到目标任务的机器学习方法。",
    "descriptionEn": "A machine learning method that transfers knowledge learned from a source task to a target task.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "transfer learning",
    "paperCount": 22,
    "enabled": true
  },
  {
    "id": "representation-learning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "表征学习",
    "nameEn": "Representation Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从原始数据中自动学习有效特征表示的机器学习方法。",
    "descriptionEn": "A machine learning method that automatically learns effective feature representations from raw data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "representation learning",
    "paperCount": 48,
    "enabled": true
  },
  {
    "id": "contrastive-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "对比学习",
    "nameEn": "Contrastive Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过拉近相似样本、推远不相似样本来学习表征的机器学习方法。",
    "descriptionEn": "A machine learning method that learns representations by pulling similar samples closer and pushing dissimilar samples apart.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "contrastive learning",
    "paperCount": 119,
    "enabled": true
  },
  {
    "id": "self-supervised-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "自监督学习",
    "nameEn": "Self-Supervised Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用数据自身构造监督信号进行表征学习的机器学习方法。",
    "descriptionEn": "A machine learning method that constructs supervisory signals from the data itself for representation learning.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "self-supervised learning",
    "paperCount": 85,
    "enabled": true
  },
  {
    "id": "unsupervised-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "无监督学习",
    "nameEn": "Unsupervised Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在无标注数据上发现内在结构与模式的机器学习方法。",
    "descriptionEn": "A machine learning method that discovers intrinsic structures and patterns from unlabeled data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "unsupervised learning",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "semi-supervised-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "半监督学习",
    "nameEn": "Semi-Supervised Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时利用少量标注数据与大量未标注数据进行训练的机器学习方法。",
    "descriptionEn": "A machine learning method that trains using both a small amount of labeled data and a large amount of unlabeled data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "semi-supervised learning",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "knowledge-distillation",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "知识蒸馏",
    "nameEn": "Knowledge Distillation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将大模型的知识迁移到小模型以提升其性能的机器学习方法。",
    "descriptionEn": "A machine learning method that transfers knowledge from a large model to a smaller model to improve its performance.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "knowledge distillation",
    "paperCount": 104,
    "enabled": true
  },
  {
    "id": "graph-neural-networks",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "图神经网络",
    "nameEn": "Graph Neural Networks",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种直接在图结构数据上进行消息传递与特征聚合的神经网络模型。",
    "descriptionEn": "A neural network model that performs message passing and feature aggregation directly on graph-structured data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "graph neural networks",
    "paperCount": 77,
    "enabled": true
  },
  {
    "id": "federated-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "联邦学习",
    "nameEn": "Federated Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在不共享原始数据的前提下多方协同训练模型的机器学习方法。",
    "descriptionEn": "A machine learning method that enables multiple parties to collaboratively train a model without sharing raw data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "federated learning",
    "paperCount": 69,
    "enabled": true
  },
  {
    "id": "continual-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "持续学习",
    "nameEn": "Continual Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使模型在连续到来的任务流中不断学习且不遗忘旧知识的机器学习方法。",
    "descriptionEn": "A machine learning method that enables a model to learn continuously from a stream of tasks without forgetting previous knowledge.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "continual learning",
    "paperCount": 59,
    "enabled": true
  },
  {
    "id": "curriculum-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "课程学习",
    "nameEn": "Curriculum Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种按照由易到难的顺序组织训练样本以加速模型收敛的机器学习方法。",
    "descriptionEn": "A machine learning method that organizes training samples from easy to difficult to accelerate model convergence.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "curriculum learning",
    "paperCount": 58,
    "enabled": true
  },
  {
    "id": "multi-task-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "多任务学习",
    "nameEn": "Multi-Task Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时学习多个相关任务并共享表征以提升泛化能力的机器学习方法。",
    "descriptionEn": "A machine learning method that learns multiple related tasks simultaneously and shares representations to improve generalization.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "multi-task learning",
    "paperCount": 40,
    "enabled": true
  },
  {
    "id": "active-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "主动学习",
    "nameEn": "Active Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由模型主动选择最有价值的未标注样本进行标注以降低标注成本的机器学习方法。",
    "descriptionEn": "A machine learning method in which the model actively selects the most valuable unlabeled samples for annotation to reduce labeling cost.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "active learning",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "online-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "在线学习",
    "nameEn": "Online Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在数据逐到来时实时更新模型参数的机器学习方法。",
    "descriptionEn": "A machine learning method that updates model parameters in real time as data arrives sequentially.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "online learning",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "meta-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "元学习",
    "nameEn": "Meta-Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使模型学会如何学习从而快速适应新任务的机器学习方法。",
    "descriptionEn": "A machine learning method that enables a model to learn how to learn and adapt quickly to new tasks.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "meta-learning",
    "paperCount": 26,
    "enabled": true
  },
  {
    "id": "imitation-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "模仿学习",
    "nameEn": "Imitation Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过学习专家演示轨迹来训练智能体决策策略的机器学习方法。",
    "descriptionEn": "A machine learning method that trains an agent's decision policy by learning from expert demonstration trajectories.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "imitation learning",
    "paperCount": 26,
    "enabled": true
  },
  {
    "id": "deep-reinforcement-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "深度强化学习",
    "nameEn": "Deep Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将深度神经网络与强化学习结合以解决高维决策问题的机器学习方法。",
    "descriptionEn": "A machine learning method that combines deep neural networks with reinforcement learning to solve high-dimensional decision problems.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "deep reinforcement learning",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "offline-reinforcement-learning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "离线强化学习",
    "nameEn": "Offline Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种仅利用预先采集的固定数据集进行策略学习而无需与环境交互的强化学习方法。",
    "descriptionEn": "A reinforcement learning method that learns policies solely from a pre-collected fixed dataset without interacting with the environment.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "offline reinforcement learning",
    "paperCount": 30,
    "enabled": true
  },
  {
    "id": "policy-optimization",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "策略优化",
    "nameEn": "Policy Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过直接优化参数化策略来最大化期望回报的强化学习方法。",
    "descriptionEn": "A reinforcement learning method that directly optimizes a parameterized policy to maximize expected return.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "policy optimization",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "policy-gradient",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "策略梯度",
    "nameEn": "Policy Gradient",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过计算回报对策略参数的梯度来更新策略的强化学习方法。",
    "descriptionEn": "A reinforcement learning method that updates the policy by computing the gradient of return with respect to policy parameters.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "policy gradient",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "reward-modeling",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "奖励建模",
    "nameEn": "Reward Modeling",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从人类偏好或反馈中学习奖励函数以指导智能体训练的机器学习方法。",
    "descriptionEn": "A machine learning method that learns a reward function from human preferences or feedback to guide agent training.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "reward modeling",
    "paperCount": 34,
    "enabled": true
  },
  {
    "id": "bayesian-optimization",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "贝叶斯优化",
    "nameEn": "Bayesian Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于概率代理模型高效搜索黑盒函数最优解的优化方法。",
    "descriptionEn": "An optimization method that efficiently searches for the optimum of a black-box function using a probabilistic surrogate model.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "bayesian optimization",
    "paperCount": 27,
    "enabled": true
  },
  {
    "id": "uncertainty-quantification",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "不确定性量化",
    "nameEn": "Uncertainty Quantification",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对模型预测结果中的不确定性进行估计与度量的机器学习方法。",
    "descriptionEn": "A machine learning method that estimates and measures the uncertainty in model predictions.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "uncertainty quantification",
    "paperCount": 68,
    "enabled": true
  },
  {
    "id": "differential-privacy",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "差分隐私",
    "nameEn": "Differential Privacy",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过添加受控噪声使模型训练过程不泄露个体数据隐私的隐私保护方法。",
    "descriptionEn": "A privacy-preserving method that adds controlled noise so that model training does not reveal individual data privacy.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "differential privacy",
    "paperCount": 45,
    "enabled": true
  },
  {
    "id": "adversarial-robustness",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "对抗鲁棒性",
    "nameEn": "Adversarial Robustness",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种提升模型在对抗性扰动输入下仍保持正确预测能力的机器学习方法。",
    "descriptionEn": "A machine learning method that improves a model's ability to maintain correct predictions under adversarially perturbed inputs.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "adversarial robustness",
    "paperCount": 45,
    "enabled": true
  },
  {
    "id": "adversarial-attacks",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "对抗攻击",
    "nameEn": "Adversarial Attacks",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过对输入添加人眼不可察的扰动来诱导模型输出错误结果的攻击方法。",
    "descriptionEn": "An attack method that induces a model to produce incorrect outputs by adding imperceptible perturbations to inputs.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "adversarial attacks",
    "paperCount": 30,
    "enabled": true
  },
  {
    "id": "adversarial-training",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "对抗训练",
    "nameEn": "Adversarial Training",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在训练过程中混入对抗样本以提升模型鲁棒性的机器学习方法。",
    "descriptionEn": "A machine learning method that incorporates adversarial examples during training to improve model robustness.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "adversarial training",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "catastrophic-forgetting",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "灾难性遗忘",
    "nameEn": "Catastrophic Forgetting",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种模型在学习新任务时突然丧失已学旧任务知识的现象。",
    "descriptionEn": "A phenomenon in which a model abruptly loses knowledge of previously learned tasks when learning new ones.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "catastrophic forgetting",
    "paperCount": 64,
    "enabled": true
  },
  {
    "id": "domain-adaptation",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "域适应",
    "nameEn": "Domain Adaptation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将在源域训练的模型适配到分布不同的目标域的机器学习方法。",
    "descriptionEn": "A machine learning method that adapts a model trained on a source domain to a target domain with a different distribution.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "domain adaptation",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "distribution-shift",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "分布偏移",
    "nameEn": "Distribution Shift",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种训练数据与测试数据分布不一致导致模型性能下降的现象。",
    "descriptionEn": "A phenomenon in which the distribution of training data differs from that of test data, causing degraded model performance.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "distribution shift",
    "paperCount": 41,
    "enabled": true
  },
  {
    "id": "data-augmentation",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "数据增强",
    "nameEn": "Data Augmentation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过对现有样本施加变换生成更多训练数据以提升模型泛化能力的方法。",
    "descriptionEn": "A method that generates more training data by applying transformations to existing samples to improve model generalization.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "data augmentation",
    "paperCount": 40,
    "enabled": true
  },
  {
    "id": "knowledge-graph",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "知识图谱",
    "nameEn": "Knowledge Graph",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种以实体为节点、关系为边结构化表示事实知识的图数据模型。",
    "descriptionEn": "A graph data model that represents factual knowledge in a structured manner with entities as nodes and relations as edges.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "knowledge graph",
    "paperCount": 43,
    "enabled": true
  },
  {
    "id": "optimal-transport",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "最优传输",
    "nameEn": "Optimal Transport",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究如何以最小代价将一个概率分布变换为另一个概率分布的数学方法。",
    "descriptionEn": "A mathematical method that studies how to transform one probability distribution into another with minimal cost.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "optimal transport",
    "paperCount": 49,
    "enabled": true
  },
  {
    "id": "mechanistic-interpretability",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "机制可解释性",
    "nameEn": "Mechanistic Interpretability",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过逆向工程神经网络内部电路来理解模型推理机制的研究方法。",
    "descriptionEn": "A research method that reverse-engineers the internal circuits of neural networks to understand their reasoning mechanisms.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "mechanistic interpretability",
    "paperCount": 57,
    "enabled": true
  },
  {
    "id": "explainable-artificial-intelligence",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "可解释人工智能",
    "nameEn": "Explainable Artificial Intelligence",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使人工智能模型的决策过程可被人类理解与解释的技术方法。",
    "descriptionEn": "A technical method that makes the decision-making process of artificial intelligence models understandable and interpretable by humans.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "explainable artificial intelligence",
    "paperCount": 29,
    "enabled": true
  },
  {
    "id": "machine-unlearning",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "机器遗忘",
    "nameEn": "Machine Unlearning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使已训练模型移除特定训练数据影响的机器学习方法。",
    "descriptionEn": "A machine learning method that removes the influence of specific training data from an already trained model.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "machine unlearning",
    "paperCount": 35,
    "enabled": true
  },
  {
    "id": "time-series-forecasting",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "时间序列预测",
    "nameEn": "Time Series Forecasting",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于历史时间序列数据预测未来数值的机器学习方法。",
    "descriptionEn": "A machine learning method that predicts future values based on historical time series data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "time series forecasting",
    "paperCount": 35,
    "enabled": true
  },
  {
    "id": "causal-inference",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "因果推断",
    "nameEn": "Causal Inference",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从观测或实验数据中推断变量间因果关系的统计方法。",
    "descriptionEn": "A statistical method that infers causal relationships between variables from observational or experimental data.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "causal inference",
    "paperCount": 20,
    "enabled": true
  },
  {
    "id": "model-merging",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "模型合并",
    "nameEn": "Model Merging",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将多个独立训练的模型参数直接合并为一个模型的方法。",
    "descriptionEn": "A method that directly combines the parameters of multiple independently trained models into a single model.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "model merging",
    "paperCount": 62,
    "enabled": true
  },
  {
    "id": "low-rank-adaptation",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "低秩适配",
    "nameEn": "Low-Rank Adaptation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过注入低秩矩阵对预训练模型进行参数高效微调的方法。",
    "descriptionEn": "A parameter-efficient fine-tuning method that injects low-rank matrices into a pre-trained model.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "low-rank adaptation",
    "paperCount": 65,
    "enabled": true
  },
  {
    "id": "test-time-adaptation",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "测试时适应",
    "nameEn": "Test-Time Adaptation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在推理阶段根据测试输入动态调整模型以应对分布变化的方法。",
    "descriptionEn": "A method that dynamically adjusts the model during inference based on test inputs to handle distribution shifts.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "test-time adaptation",
    "paperCount": 46,
    "enabled": true
  },
  {
    "id": "post-training-quantization",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "训练后量化",
    "nameEn": "Post-Training Quantization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在模型训练完成后将其浮点参数转换为低比特整数以压缩模型的方法。",
    "descriptionEn": "A method that converts floating-point parameters of a trained model to low-bit integers to compress the model.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "post-training quantization",
    "paperCount": 35,
    "enabled": true
  },
  {
    "id": "automl",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "自动机器学习",
    "nameEn": "Automated Machine Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动完成模型选择、超参数调优与特征工程的机器学习方法。",
    "descriptionEn": "A machine learning method that automates model selection, hyperparameter tuning, and feature engineering.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "automl",
    "paperCount": 32,
    "enabled": true
  },
  {
    "id": "model-compression",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "模型压缩",
    "nameEn": "Model Compression",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过剪枝、量化或蒸馏减小模型体积与计算量的方法。",
    "descriptionEn": "A method that reduces model size and computational cost through pruning, quantization, or distillation.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "model compression",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "neural-networks",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "神经网络",
    "nameEn": "Neural Networks",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由大量互连神经元分层组成、可学习非线性映射的计算模型。",
    "descriptionEn": "A computational model composed of layers of interconnected neurons that can learn nonlinear mappings.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "neural networks",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "clustering",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "聚类",
    "nameEn": "Clustering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将无标注数据按相似度划分为若干组的无监督学习方法。",
    "descriptionEn": "An unsupervised learning method that partitions unlabeled data into groups based on similarity.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "clustering",
    "paperCount": 966,
    "enabled": true
  },
  {
    "id": "conformal-prediction",
    "imagePath": "/images/topics/deep-learning-cover.png",
    "nameZh": "共形预测",
    "nameEn": "Conformal Prediction",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种为模型预测结果提供具有统计保证置信区间的预测方法。",
    "descriptionEn": "A prediction method that provides statistically guaranteed confidence intervals for model predictions.",
    "followersCount": 0,
    "category": "机器学习",
    "subjectQuery": "conformal prediction",
    "paperCount": 28,
    "enabled": true
  },
  {
    "id": "autonomous-driving",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "自动驾驶",
    "nameEn": "Autonomous Driving",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使车辆在无人工干预下感知环境并自主导航行驶的技术。",
    "descriptionEn": "A technology that enables a vehicle to perceive its environment and navigate autonomously without human intervention.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "autonomous driving",
    "paperCount": 142,
    "enabled": true
  },
  {
    "id": "3d-gaussian-splatting",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "三维高斯溅射",
    "nameEn": "3D Gaussian Splatting",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用三维高斯函数表示场景并实现实时高质量新视角合成的渲染方法。",
    "descriptionEn": "A rendering method that represents a scene with 3D Gaussian functions and achieves real-time high-quality novel view synthesis.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "3d gaussian splatting",
    "paperCount": 137,
    "enabled": true
  },
  {
    "id": "object-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "目标检测",
    "nameEn": "Object Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在图像中定位并识别特定类别物体的计算机视觉方法。",
    "descriptionEn": "A computer vision method that locates and identifies objects of specific categories in an image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "object detection",
    "paperCount": 26,
    "enabled": true
  },
  {
    "id": "image-classification",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "图像分类",
    "nameEn": "Image Classification",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将输入图像分配到预定义类别中的计算机视觉方法。",
    "descriptionEn": "A computer vision method that assigns an input image to one of predefined categories.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "image classification",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "semantic-segmentation",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "语义分割",
    "nameEn": "Semantic Segmentation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对图像中每个像素进行类别标注的计算机视觉方法。",
    "descriptionEn": "A computer vision method that assigns a category label to every pixel in an image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "semantic segmentation",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "action-recognition",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "动作识别",
    "nameEn": "Action Recognition",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从视频序列中识别并分类人体动作的计算机视觉方法。",
    "descriptionEn": "A computer vision method that recognizes and classifies human actions from video sequences.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "action recognition",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "video-understanding",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视频理解",
    "nameEn": "Video Understanding",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对视频内容进行语义分析与事件理解的计算机视觉方法。",
    "descriptionEn": "A computer vision method that performs semantic analysis and event understanding of video content.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "video understanding",
    "paperCount": 37,
    "enabled": true
  },
  {
    "id": "3d-reconstruction",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "三维重建",
    "nameEn": "3D Reconstruction",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从二维图像或传感器数据恢复物体三维几何结构的计算机视觉方法。",
    "descriptionEn": "A computer vision method that recovers the 3D geometric structure of objects from 2D images or sensor data.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "3d reconstruction",
    "paperCount": 32,
    "enabled": true
  },
  {
    "id": "vision-transformer",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉Transformer",
    "nameEn": "Vision Transformer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将图像划分为补丁序列并利用Transformer架构进行特征提取的神经网络模型。",
    "descriptionEn": "A neural network model that divides an image into a sequence of patches and extracts features using the Transformer architecture.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "vision transformer",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "visual-reasoning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉推理",
    "nameEn": "Visual Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于视觉信息进行逻辑推断与关系推理的计算机视觉方法。",
    "descriptionEn": "A computer vision method that performs logical inference and relational reasoning based on visual information.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "visual reasoning",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "vision-foundation-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉基础模型",
    "nameEn": "Vision Foundation Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大规模图像数据上预训练、可适配多种下游视觉任务的神经网络模型。",
    "descriptionEn": "A neural network model pre-trained on large-scale image data that can be adapted to various downstream vision tasks.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "vision foundation models",
    "paperCount": 29,
    "enabled": true
  },
  {
    "id": "out-of-distribution-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "分布外检测",
    "nameEn": "Out-of-Distribution Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种识别输入数据是否偏离训练数据分布的计算机视觉方法。",
    "descriptionEn": "A computer vision method that identifies whether input data deviates from the training data distribution.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "out-of-distribution detection",
    "paperCount": 27,
    "enabled": true
  },
  {
    "id": "remote-sensing",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "遥感",
    "nameEn": "Remote Sensing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过卫星或航空传感器获取地表影像并进行解译分析的技术。",
    "descriptionEn": "A technology that acquires and interprets surface imagery through satellite or aerial sensors.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "remote sensing",
    "paperCount": 24,
    "enabled": true
  },
  {
    "id": "point-cloud",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "点云",
    "nameEn": "Point Cloud",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由三维空间中大量离散点组成的几何数据表示。",
    "descriptionEn": "A geometric data representation composed of a large number of discrete points in 3D space.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "point cloud",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "anomaly-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "异常检测",
    "nameEn": "Anomaly Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从数据中识别偏离正常模式的异常样本的方法。",
    "descriptionEn": "A method that identifies anomalous samples deviating from normal patterns in data.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "anomaly detection",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "image-restoration",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "图像复原",
    "nameEn": "Image Restoration",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从退化图像中恢复清晰原始图像的计算机视觉方法。",
    "descriptionEn": "A computer vision method that recovers a clear original image from a degraded image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "image restoration",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "deepfake-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "深度伪造检测",
    "nameEn": "Deepfake Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种识别由人工智能生成或篡改的伪造人脸视频的方法。",
    "descriptionEn": "A method that identifies forged face videos generated or manipulated by artificial intelligence.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "deepfake detection",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "egocentric-video",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "第一人称视频",
    "nameEn": "Egocentric Video",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种以佩戴者第一人称视角拍摄的视频数据及其分析方法。",
    "descriptionEn": "Video data captured from a wearer's first-person perspective and its analysis methods.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "egocentric video",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "optical-flow",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "光流",
    "nameEn": "Optical Flow",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种估计图像序列中像素运动矢量场的计算机视觉方法。",
    "descriptionEn": "A computer vision method that estimates the motion vector field of pixels in an image sequence.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "optical flow",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "medical-image-segmentation",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "医学图像分割",
    "nameEn": "Medical Image Segmentation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对医学影像中器官或病灶区域进行像素级分割的方法。",
    "descriptionEn": "A method that performs pixel-level segmentation of organs or lesion regions in medical images.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "medical image segmentation",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "video-question-answering",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视频问答",
    "nameEn": "Video Question Answering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据视频内容回答自然语言问题的多模态方法。",
    "descriptionEn": "A multimodal method that answers natural language questions based on video content.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "video question answering",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "neural-rendering",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "神经渲染",
    "nameEn": "Neural Rendering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用神经网络从场景表示生成新视角图像的渲染方法。",
    "descriptionEn": "A rendering method that generates novel-view images from scene representations using neural networks.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "neural rendering",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "3d-scene-understanding",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "三维场景理解",
    "nameEn": "3D Scene Understanding",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对三维场景中的物体、布局与空间关系进行语义解析的方法。",
    "descriptionEn": "A method that semantically parses objects, layouts, and spatial relationships in a 3D scene.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "3d scene understanding",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "image-quality-assessment",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "图像质量评价",
    "nameEn": "Image Quality Assessment",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动度量图像感知质量的计算机视觉方法。",
    "descriptionEn": "A computer vision method that automatically measures the perceptual quality of images.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "image quality assessment",
    "paperCount": 13,
    "enabled": true
  },
  {
    "id": "3d-object-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "三维目标检测",
    "nameEn": "3D Object Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在三维空间中定位并识别物体的计算机视觉方法。",
    "descriptionEn": "A computer vision method that locates and identifies objects in 3D space.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "3d object detection",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "ai-generated-image-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "AI生成图像检测",
    "nameEn": "AI-Generated Image Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种识别由人工智能模型生成的伪造图像的方法。",
    "descriptionEn": "A method that identifies forged images generated by artificial intelligence models.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "ai-generated image detection",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "segment-anything-model",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "分割一切模型",
    "nameEn": "Segment Anything Model",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种可对任意图像中任意物体进行零样本分割的基础模型。",
    "descriptionEn": "A foundation model that performs zero-shot segmentation of any object in any image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "segment anything model",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "human-object-interaction",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "人物交互",
    "nameEn": "Human-Object Interaction",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种识别图像中人与物体之间交互关系的计算机视觉方法。",
    "descriptionEn": "A computer vision method that recognizes interaction relationships between humans and objects in images.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "human-object interaction",
    "paperCount": 13,
    "enabled": true
  },
  {
    "id": "long-video-understanding",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "长视频理解",
    "nameEn": "Long Video Understanding",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对时长较长的视频进行全局语义分析与事件理解的方法。",
    "descriptionEn": "A method that performs global semantic analysis and event understanding of long-duration videos.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "long video understanding",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "nerf",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "神经辐射场",
    "nameEn": "Neural Radiance Fields",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用多层感知机隐式表示场景辐射场并实现新视角合成的方法。",
    "descriptionEn": "A method that implicitly represents a scene's radiance field with a multilayer perceptron for novel view synthesis.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "nerf",
    "paperCount": 344,
    "enabled": true
  },
  {
    "id": "ocr",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "光学字符识别",
    "nameEn": "Optical Character Recognition",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从图像中自动识别并提取文字内容的计算机视觉方法。",
    "descriptionEn": "A computer vision method that automatically recognizes and extracts text content from images.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "ocr",
    "paperCount": 82,
    "enabled": true
  },
  {
    "id": "slam",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "同步定位与地图构建",
    "nameEn": "Simultaneous Localization and Mapping",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使移动设备在未知环境中同时估计自身位姿并构建环境地图的方法。",
    "descriptionEn": "A method that enables a mobile device to estimate its pose and build an environment map simultaneously in an unknown environment.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "slam",
    "paperCount": 74,
    "enabled": true
  },
  {
    "id": "super-resolution",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "超分辨率",
    "nameEn": "Super-Resolution",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从低分辨率图像重建高分辨率图像的计算机视觉方法。",
    "descriptionEn": "A computer vision method that reconstructs a high-resolution image from a low-resolution image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "super-resolution",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "hallucination-detection",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "幻觉检测",
    "nameEn": "Hallucination Detection",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种识别视觉模型输出中与输入图像不符的虚假内容的方法。",
    "descriptionEn": "A method that identifies fabricated content in visual model outputs that does not match the input image.",
    "followersCount": 0,
    "category": "计算机视觉",
    "subjectQuery": "hallucination detection",
    "paperCount": 44,
    "enabled": true
  },
  {
    "id": "machine-translation",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "机器翻译",
    "nameEn": "Machine Translation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用计算机自动将一种自然语言翻译为另一种自然语言的方法。",
    "descriptionEn": "A method that automatically translates one natural language into another using a computer.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "machine translation",
    "paperCount": 22,
    "enabled": true
  },
  {
    "id": "question-answering",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "问答",
    "nameEn": "Question Answering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据给定文本或知识库自动回答自然语言问题的方法。",
    "descriptionEn": "A method that automatically answers natural language questions based on given text or a knowledge base.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "question answering",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "natural-language-inference",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "自然语言推理",
    "nameEn": "Natural Language Inference",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种判断前提句与假设句之间蕴含、矛盾或中立关系的方法。",
    "descriptionEn": "A method that determines whether a premise entails, contradicts, or is neutral to a hypothesis.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "natural language inference",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "multi-hop-question-answering",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "多跳问答",
    "nameEn": "Multi-Hop Question Answering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种需要从多个文档或证据中逐步推理才能回答问题的问答方法。",
    "descriptionEn": "A question answering method that requires step-by-step reasoning across multiple documents or pieces of evidence.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "multi-hop question answering",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "low-resource-languages",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "低资源语言",
    "nameEn": "Low-Resource Languages",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类训练数据稀缺的自然语言及其相关处理方法。",
    "descriptionEn": "Natural languages with scarce training data and the related processing methods.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "low-resource languages",
    "paperCount": 26,
    "enabled": true
  },
  {
    "id": "content-moderation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "内容审核",
    "nameEn": "Content Moderation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动检测并过滤文本中违规或有害内容的方法。",
    "descriptionEn": "A method that automatically detects and filters violating or harmful content in text.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "content moderation",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "cross-lingual-transfer",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "跨语言迁移",
    "nameEn": "Cross-Lingual Transfer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将从高资源语言学到的知识迁移到低资源语言的方法。",
    "descriptionEn": "A method that transfers knowledge learned from high-resource languages to low-resource languages.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "cross-lingual transfer",
    "paperCount": 17,
    "enabled": true
  },
  {
    "id": "conversational-agents",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "对话代理",
    "nameEn": "Conversational Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够与人类进行自然语言对话交互的人工智能系统。",
    "descriptionEn": "An artificial intelligence system that can interact with humans through natural language dialogue.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "conversational agents",
    "paperCount": 16,
    "enabled": true
  },
  {
    "id": "multi-turn-dialogue",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "多轮对话",
    "nameEn": "Multi-Turn Dialogue",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种处理多轮上下文连续对话的自然语言处理方法。",
    "descriptionEn": "A natural language processing method that handles continuous dialogue with multi-turn context.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "multi-turn dialogue",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "dense-retrieval",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "稠密检索",
    "nameEn": "Dense Retrieval",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将查询与文档编码为稠密向量并按相似度检索的方法。",
    "descriptionEn": "A retrieval method that encodes queries and documents as dense vectors and retrieves by similarity.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "dense retrieval",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "conversational-ai",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "对话式AI",
    "nameEn": "Conversational AI",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使计算机能够以自然语言与人类进行对话交互的人工智能技术。",
    "descriptionEn": "An artificial intelligence technology that enables computers to interact with humans through natural language dialogue.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "conversational ai",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "long-form-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "长文本生成",
    "nameEn": "Long-Form Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种生成篇幅较长、结构连贯的自然语言文本的方法。",
    "descriptionEn": "A method that generates long, structurally coherent natural language text.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "long-form generation",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "synthetic-data-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "合成数据生成",
    "nameEn": "Synthetic Data Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用模型自动生成人工标注数据以扩充训练集的方法。",
    "descriptionEn": "A method that uses models to automatically generate artificially labeled data to expand training sets.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "synthetic data generation",
    "paperCount": 33,
    "enabled": true
  },
  {
    "id": "monte-carlo-tree-search",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "蒙特卡洛树搜索",
    "nameEn": "Monte Carlo Tree Search",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过随机采样与树搜索结合来寻找最优决策的搜索方法。",
    "descriptionEn": "A search method that combines random sampling with tree search to find optimal decisions.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "monte carlo tree search",
    "paperCount": 27,
    "enabled": true
  },
  {
    "id": "information-bottleneck",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "信息瓶颈",
    "nameEn": "Information Bottleneck",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在保留相关信息的同时压缩输入表示的信息论方法。",
    "descriptionEn": "An information-theoretic method that compresses input representations while preserving relevant information.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "information bottleneck",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "web-agents",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "Web代理",
    "nameEn": "Web Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够自主浏览网页并完成复杂在线任务的智能体系统。",
    "descriptionEn": "An agent system that can autonomously browse the web and complete complex online tasks.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "web agents",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "approximate-nearest-neighbor-search",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "近似最近邻搜索",
    "nameEn": "Approximate Nearest Neighbor Search",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在高维向量空间中高效查找近似最近邻点的检索方法。",
    "descriptionEn": "A retrieval method that efficiently finds approximate nearest neighbors in a high-dimensional vector space.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "approximate nearest neighbor search",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "sequential-recommendation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "序列推荐",
    "nameEn": "Sequential Recommendation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据用户历史交互序列预测下一个感兴趣物品的推荐方法。",
    "descriptionEn": "A recommendation method that predicts the next item of interest based on a user's historical interaction sequence.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "sequential recommendation",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "recommender-systems",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "推荐系统",
    "nameEn": "Recommender Systems",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据用户偏好与历史行为推荐相关物品的信息过滤系统。",
    "descriptionEn": "An information filtering system that recommends relevant items based on user preferences and historical behavior.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "recommender systems",
    "paperCount": 17,
    "enabled": true
  },
  {
    "id": "nlp",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "自然语言处理",
    "nameEn": "Natural Language Processing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一门研究计算机与人类自然语言之间交互的人工智能分支。",
    "descriptionEn": "A branch of artificial intelligence that studies interactions between computers and human natural language.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "nlp",
    "paperCount": 736,
    "enabled": true
  },
  {
    "id": "ner",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "命名实体识别",
    "nameEn": "Named Entity Recognition",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从文本中自动识别并分类人名、地名、机构名等实体的方法。",
    "descriptionEn": "A method that automatically identifies and classifies entities such as person names, locations, and organizations in text.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "ner",
    "paperCount": 276,
    "enabled": true
  },
  {
    "id": "nmt",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "神经机器翻译",
    "nameEn": "Neural Machine Translation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于端到端神经网络的机器翻译方法。",
    "descriptionEn": "A machine translation method based on end-to-end neural networks.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "nmt",
    "paperCount": 312,
    "enabled": true
  },
  {
    "id": "transliteration",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "音译",
    "nameEn": "Transliteration",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将一种文字系统中的字符转换为另一种文字系统对应字符的方法。",
    "descriptionEn": "A method that converts characters from one writing system to corresponding characters in another writing system.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "transliteration",
    "paperCount": 32,
    "enabled": true
  },
  {
    "id": "sentiment",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "情感分析",
    "nameEn": "Sentiment Analysis",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动识别文本中情感倾向与情绪类别 的自然语言处理方法。",
    "descriptionEn": "A natural language processing method that automatically identifies sentiment orientation and emotion categories in text.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "sentiment",
    "paperCount": 454,
    "enabled": true
  },
  {
    "id": "summarization",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "文本摘要",
    "nameEn": "Text Summarization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动将长文本压缩为简洁摘要并保留核心信息的方法。",
    "descriptionEn": "A method that automatically compresses long text into a concise summary while preserving core information.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "summarization",
    "paperCount": 767,
    "enabled": true
  },
  {
    "id": "parsing",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "句法分析",
    "nameEn": "Syntactic Parsing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种分析句子语法结构并构建句法树的自然语言处理方法。",
    "descriptionEn": "A natural language processing method that analyzes the grammatical structure of sentences and constructs parse trees.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "parsing",
    "paperCount": 700,
    "enabled": true
  },
  {
    "id": "retrieval",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "信息检索",
    "nameEn": "Information Retrieval",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从大规模文档集合中查找与查询相关信息的方法。",
    "descriptionEn": "A method that finds information relevant to a query from a large collection of documents.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "retrieval",
    "paperCount": 1619,
    "enabled": true
  },
  {
    "id": "extraction",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "信息抽取",
    "nameEn": "Information Extraction",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从非结构化文本中自动提取结构化信息的自然语言处理方法。",
    "descriptionEn": "A natural language processing method that automatically extracts structured information from unstructured text.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "extraction",
    "paperCount": 1108,
    "enabled": true
  },
  {
    "id": "dialogue",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "对话系统",
    "nameEn": "Dialogue Systems",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使计算机能够与人类进行自然语言对话交互的系统。",
    "descriptionEn": "A system that enables computers to interact with humans through natural language dialogue.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "dialogue",
    "paperCount": 1161,
    "enabled": true
  },
  {
    "id": "multilingual",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "多语言处理",
    "nameEn": "Multilingual Processing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时处理多种自然语言的自然语言处理方法。",
    "descriptionEn": "A natural language processing method that processes multiple natural languages simultaneously.",
    "followersCount": 0,
    "category": "自然语言处理",
    "subjectQuery": "multilingual",
    "paperCount": 1136,
    "enabled": true
  },
  {
    "id": "large-language-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型",
    "nameEn": "Large Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于海量文本数据训练、具有大量参数、能理解和生成自然语言的深度学习模型。",
    "descriptionEn": "A deep learning model trained on massive text data with a large number of parameters that can understand and generate natural language.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "large language models",
    "paperCount": 2143,
    "enabled": true
  },
  {
    "id": "retrieval-augmented-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "检索增强生成",
    "nameEn": "Retrieval-Augmented Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在生成回答前先从外部知识库检索相关文档并结合上下文的大语言模型方法。",
    "descriptionEn": "A large language model method that retrieves relevant documents from an external knowledge base before generating answers.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "retrieval-augmented generation",
    "paperCount": 232,
    "enabled": true
  },
  {
    "id": "llm-evaluation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型评估",
    "nameEn": "LLM Evaluation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对大语言模型的能力、安全性与输出质量进行系统评测的方法。",
    "descriptionEn": "A method that systematically evaluates the capabilities, safety, and output quality of large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm evaluation",
    "paperCount": 125,
    "enabled": true
  },
  {
    "id": "parameter-efficient-fine-tuning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "参数高效微调",
    "nameEn": "Parameter-Efficient Fine-Tuning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种仅更新少量参数即可使预训练大模型适配下游任务的微调方法。",
    "descriptionEn": "A fine-tuning method that adapts a pre-trained large model to downstream tasks by updating only a small number of parameters.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "parameter-efficient fine-tuning",
    "paperCount": 98,
    "enabled": true
  },
  {
    "id": "language-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "语言模型",
    "nameEn": "Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种对自然语言序列的概率分布进行建模的深度学习模型。",
    "descriptionEn": "A deep learning model that models the probability distribution of natural language sequences.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "language models",
    "paperCount": 84,
    "enabled": true
  },
  {
    "id": "in-context-learning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "上下文学习",
    "nameEn": "In-Context Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种大语言模型仅通过提示中的示例即可学习新任务而无需更新参数的能力。",
    "descriptionEn": "An ability of large language models to learn new tasks from examples in the prompt without updating parameters.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "in-context learning",
    "paperCount": 82,
    "enabled": true
  },
  {
    "id": "chain-of-thought-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "思维链推理",
    "nameEn": "Chain-of-Thought Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种引导大语言模型逐步展示推理过程以提升复杂问题求解能力的方法。",
    "descriptionEn": "A method that guides large language models to display reasoning step by step to improve complex problem-solving ability.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "chain-of-thought reasoning",
    "paperCount": 73,
    "enabled": true
  },
  {
    "id": "llm-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型推理",
    "nameEn": "LLM Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究大语言模型进行逻辑推理与复杂问题求解能力的方法。",
    "descriptionEn": "A method that studies the logical reasoning and complex problem-solving abilities of large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm reasoning",
    "paperCount": 69,
    "enabled": true
  },
  {
    "id": "mathematical-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "数学推理",
    "nameEn": "Mathematical Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使大语言模型具备数学问题求解与逻辑推导能力的方法。",
    "descriptionEn": "A method that equips large language models with mathematical problem-solving and logical deduction abilities.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "mathematical reasoning",
    "paperCount": 65,
    "enabled": true
  },
  {
    "id": "large-reasoning-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大推理模型",
    "nameEn": "Large Reasoning Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种以强化学习训练、具备长链推理与验证能力的大语言模型。",
    "descriptionEn": "A large language model trained with reinforcement learning that possesses long-chain reasoning and verification abilities.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "large reasoning models",
    "paperCount": 62,
    "enabled": true
  },
  {
    "id": "preference-optimization",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "偏好优化",
    "nameEn": "Preference Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用人类偏好数据直接优化大语言模型生成策略的对齐方法。",
    "descriptionEn": "An alignment method that directly optimizes the generation policy of large language models using human preference data.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "preference optimization",
    "paperCount": 62,
    "enabled": true
  },
  {
    "id": "test-time-scaling",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "测试时扩展",
    "nameEn": "Test-Time Scaling",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在推理阶段通过增加计算量（如多次采样与验证）提升大模型性能的方法。",
    "descriptionEn": "A method that improves large model performance at inference time by increasing computation, such as multiple sampling and verification.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "test-time scaling",
    "paperCount": 62,
    "enabled": true
  },
  {
    "id": "direct-preference-optimization",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "直接偏好优化",
    "nameEn": "Direct Preference Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种无需显式训练奖励模型即可从人类偏好中直接优化策略的对齐方法。",
    "descriptionEn": "An alignment method that directly optimizes the policy from human preferences without explicitly training a reward model.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "direct preference optimization",
    "paperCount": 56,
    "enabled": true
  },
  {
    "id": "llm-safety",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型安全",
    "nameEn": "LLM Safety",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究大语言模型有害输出防范与安全对齐的方法。",
    "descriptionEn": "A method that studies the prevention of harmful outputs and safety alignment of large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm safety",
    "paperCount": 54,
    "enabled": true
  },
  {
    "id": "safety-alignment",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "安全对齐",
    "nameEn": "Safety Alignment",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使大语言模型的行为符合人类安全价值观与规范的对齐方法。",
    "descriptionEn": "An alignment method that makes the behavior of large language models conform to human safety values and norms.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "safety alignment",
    "paperCount": 54,
    "enabled": true
  },
  {
    "id": "code-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "代码生成",
    "nameEn": "Code Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据自然语言描述自动生成程序代码的大语言模型方法。",
    "descriptionEn": "A large language model method that automatically generates program code from natural language descriptions.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "code generation",
    "paperCount": 53,
    "enabled": true
  },
  {
    "id": "spatial-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "空间推理",
    "nameEn": "Spatial Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使大语言模型具备空间关系理解与几何推理能力的方法。",
    "descriptionEn": "A method that equips large language models with spatial relationship understanding and geometric reasoning abilities.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "spatial reasoning",
    "paperCount": 53,
    "enabled": true
  },
  {
    "id": "supervised-fine-tuning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "监督微调",
    "nameEn": "Supervised Fine-Tuning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使用高质量标注数据对预训练大语言模型进行微调的对齐方法。",
    "descriptionEn": "An alignment method that fine-tunes a pre-trained large language model using high-quality labeled data.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "supervised fine-tuning",
    "paperCount": 52,
    "enabled": true
  },
  {
    "id": "hallucination-mitigation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "幻觉缓解",
    "nameEn": "Hallucination Mitigation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种减少大语言模型生成与事实不符内容的方法。",
    "descriptionEn": "A method that reduces the generation of factually inconsistent content by large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "hallucination mitigation",
    "paperCount": 51,
    "enabled": true
  },
  {
    "id": "mixture-of-experts",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "混合专家",
    "nameEn": "Mixture of Experts",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过路由网络动态激活部分子网络以扩展模型容量的神经网络架构。",
    "descriptionEn": "A neural network architecture that dynamically activates a subset of subnetworks through a routing network to expand model capacity.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "mixture of experts",
    "paperCount": 51,
    "enabled": true
  },
  {
    "id": "foundation-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "基础模型",
    "nameEn": "Foundation Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大规模数据上预训练、可适配多种下游任务的大规模神经网络模型。",
    "descriptionEn": "A large-scale neural network model pre-trained on massive data that can be adapted to various downstream tasks.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "foundation models",
    "paperCount": 49,
    "enabled": true
  },
  {
    "id": "llm-inference",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型推理",
    "nameEn": "LLM Inference",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究大语言模型推理加速与服务部署效率的方法。",
    "descriptionEn": "A method that studies inference acceleration and serving deployment efficiency of large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm inference",
    "paperCount": 49,
    "enabled": true
  },
  {
    "id": "speculative-decoding",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "投机解码",
    "nameEn": "Speculative Decoding",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用小模型快速生成候选序列再由大模型验证以加速推理的解码方法。",
    "descriptionEn": "A decoding method that uses a small model to quickly generate candidate sequences and a large model to verify them, accelerating inference.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "speculative decoding",
    "paperCount": 48,
    "enabled": true
  },
  {
    "id": "llm-alignment",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型对齐",
    "nameEn": "LLM Alignment",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使大语言模型的输出与人类意图、价值观和安全规范保持一致的方法。",
    "descriptionEn": "A method that aligns the outputs of large language models with human intentions, values, and safety norms.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm alignment",
    "paperCount": 45,
    "enabled": true
  },
  {
    "id": "small-language-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "小语言模型",
    "nameEn": "Small Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种参数量较小、可在边缘设备部署的语言模型。",
    "descriptionEn": "A language model with a small number of parameters that can be deployed on edge devices.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "small language models",
    "paperCount": 39,
    "enabled": true
  },
  {
    "id": "instruction-tuning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "指令微调",
    "nameEn": "Instruction Tuning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使用指令-回答对微调大语言模型以提升其遵循指令能力的方法。",
    "descriptionEn": "A method that fine-tunes large language models using instruction-response pairs to improve their instruction-following ability.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "instruction tuning",
    "paperCount": 32,
    "enabled": true
  },
  {
    "id": "scaling-laws",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "缩放定律",
    "nameEn": "Scaling Laws",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种描述大语言模型性能随参数量、数据量与计算量变化规律的经验法则。",
    "descriptionEn": "An empirical law that describes how large language model performance varies with parameter count, data volume, and computation.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "scaling laws",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "multi-hop-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "多跳推理",
    "nameEn": "Multi-Hop Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种需要经过多个推理步骤才能得出结论的复杂推理方法。",
    "descriptionEn": "A complex reasoning method that requires multiple reasoning steps to reach a conclusion.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "multi-hop reasoning",
    "paperCount": 30,
    "enabled": true
  },
  {
    "id": "sparse-attention",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "稀疏注意力",
    "nameEn": "Sparse Attention",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过限制每个token仅关注部分位置以降低注意力计算复杂度的方法。",
    "descriptionEn": "A method that reduces attention computation complexity by restricting each token to attend only to a subset of positions.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "sparse attention",
    "paperCount": 30,
    "enabled": true
  },
  {
    "id": "formal-verification",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "形式化验证",
    "nameEn": "Formal Verification",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使用数学方法严格证明大语言模型满足特定安全属性的方法。",
    "descriptionEn": "A method that uses mathematical techniques to rigorously prove that large language models satisfy specific safety properties.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "formal verification",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "temporal-reasoning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "时序推理",
    "nameEn": "Temporal Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使大语言模型理解时间关系并进行时序逻辑推理的方法。",
    "descriptionEn": "A method that equips large language models with temporal relationship understanding and temporal logical reasoning abilities.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "temporal reasoning",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "token-efficiency",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "词元效率",
    "nameEn": "Token Efficiency",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在不损失性能的前提下减少大语言模型处理所需词元数量的方法。",
    "descriptionEn": "A method that reduces the number of tokens required for large language model processing without losing performance.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "token efficiency",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "kv-cache",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "KV缓存",
    "nameEn": "KV Cache",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大语言模型推理时缓存键值矩阵以避免重复计算的加速技术。",
    "descriptionEn": "An acceleration technique that caches key-value matrices during large language model inference to avoid redundant computation.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "kv cache",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "token-pruning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "词元剪枝",
    "nameEn": "Token Pruning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在推理过程中移除不重要词元以加速大语言模型的方法。",
    "descriptionEn": "A method that removes unimportant tokens during inference to accelerate large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "token pruning",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "zero-shot-generalization",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "零样本泛化",
    "nameEn": "Zero-Shot Generalization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种大语言模型在未见过目标任务示例的情况下仍能完成该任务的能力。",
    "descriptionEn": "An ability of large language models to perform a target task without having seen examples of that task.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "zero-shot generalization",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "attention-mechanism",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "注意力机制",
    "nameEn": "Attention Mechanism",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使模型在处理序列时动态关注相关位置信息的神经网络机制。",
    "descriptionEn": "A neural network mechanism that enables a model to dynamically focus on relevant positions when processing sequences.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "attention mechanism",
    "paperCount": 22,
    "enabled": true
  },
  {
    "id": "jailbreak-attacks",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "越狱攻击",
    "nameEn": "Jailbreak Attacks",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过构造特殊提示诱导大语言模型输出有害内容的攻击方法。",
    "descriptionEn": "An attack method that induces large language models to output harmful content by constructing special prompts.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "jailbreak attacks",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "zero-shot-learning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "零样本学习",
    "nameEn": "Zero-Shot Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种大语言模型在无任务示例的情况下仅通过指令描述完成新任务的能力。",
    "descriptionEn": "An ability of large language models to perform new tasks from instruction descriptions alone without task examples.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "zero-shot learning",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "few-shot-learning",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "少样本学习",
    "nameEn": "Few-Shot Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种大语言模型仅通过提示中少量示例即可学习新任务的能力。",
    "descriptionEn": "An ability of large language models to learn new tasks from only a few examples in the prompt.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "few-shot learning",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "instruction-following",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "指令遵循",
    "nameEn": "Instruction Following",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种衡量大语言模型准确理解并执行人类指令能力的方法。",
    "descriptionEn": "A method that measures the ability of large language models to accurately understand and execute human instructions.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "instruction following",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "llm-serving",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "大语言模型服务",
    "nameEn": "LLM Serving",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究大语言模型高并发低延迟在线推理服务部署的方法。",
    "descriptionEn": "A method that studies the deployment of high-concurrency low-latency online inference services for large language models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llm serving",
    "paperCount": 19,
    "enabled": true
  },
  {
    "id": "gpt",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "GPT",
    "nameEn": "Generative Pre-trained Transformer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于Transformer架构的生成式预训练大语言模型系列。",
    "descriptionEn": "A series of generative pre-trained large language models based on the Transformer architecture.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "gpt",
    "paperCount": 370,
    "enabled": true
  },
  {
    "id": "bert",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "BERT",
    "nameEn": "Bidirectional Encoder Representations from Transformers",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于Transformer编码器的双向预训练语言模型。",
    "descriptionEn": "A bidirectional pre-trained language model based on the Transformer encoder.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "bert",
    "paperCount": 364,
    "enabled": true
  },
  {
    "id": "rag",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "检索增强生成",
    "nameEn": "Retrieval-Augmented Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在生成前检索外部知识并结合上下文以提升回答准确性的大语言模型方法。",
    "descriptionEn": "A large language model method that retrieves external knowledge before generation and combines it with context to improve answer accuracy.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "rag",
    "paperCount": 361,
    "enabled": true
  },
  {
    "id": "lora",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "低秩适配",
    "nameEn": "Low-Rank Adaptation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过注入低秩矩阵对预训练大模型进行参数高效微调的方法。",
    "descriptionEn": "A parameter-efficient fine-tuning method that injects low-rank matrices into a pre-trained large model.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "lora",
    "paperCount": 300,
    "enabled": true
  },
  {
    "id": "mamba",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "Mamba",
    "nameEn": "Mamba",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于结构化状态空间模型的线性时间序列建模架构。",
    "descriptionEn": "A linear-time sequence modeling architecture based on structured state space models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "mamba",
    "paperCount": 232,
    "enabled": true
  },
  {
    "id": "grpo",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "组相对策略优化",
    "nameEn": "Group Relative Policy Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种无需价值函数、以组内相对奖励优化策略的强化学习对齐方法。",
    "descriptionEn": "A reinforcement learning alignment method that optimizes the policy using group-relative rewards without a value function.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "grpo",
    "paperCount": 213,
    "enabled": true
  },
  {
    "id": "cot",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "思维链",
    "nameEn": "Chain-of-Thought",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种引导大语言模型逐步展示推理过程以提升复杂问题求解能力的提示方法。",
    "descriptionEn": "A prompting method that guides large language models to display reasoning step by step to improve complex problem-solving ability.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "cot",
    "paperCount": 308,
    "enabled": true
  },
  {
    "id": "dpo",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "直接偏好优化",
    "nameEn": "Direct Preference Optimization",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种无需奖励模型即可从人类偏好中直接优化策略的对齐方法。",
    "descriptionEn": "An alignment method that directly optimizes the policy from human preferences without a reward model.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "dpo",
    "paperCount": 174,
    "enabled": true
  },
  {
    "id": "peft",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "参数高效微调",
    "nameEn": "Parameter-Efficient Fine-Tuning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种仅更新少量参数即可适配预训练大模型的微调方法集合。",
    "descriptionEn": "A collection of fine-tuning methods that adapt pre-trained large models by updating only a small number of parameters.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "peft",
    "paperCount": 161,
    "enabled": true
  },
  {
    "id": "llama",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "LLaMA",
    "nameEn": "Large Language Model Meta AI",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由Meta开发的开源大语言模型系列。",
    "descriptionEn": "A series of open-source large language models developed by Meta.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "llama",
    "paperCount": 180,
    "enabled": true
  },
  {
    "id": "transformer",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "Transformer",
    "nameEn": "Transformer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于自注意力机制的并行化序列建模神经网络架构。",
    "descriptionEn": "A parallelized sequence modeling neural network architecture based on the self-attention mechanism.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "transformer",
    "paperCount": 1853,
    "enabled": true
  },
  {
    "id": "prompt",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "提示工程",
    "nameEn": "Prompt Engineering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过设计输入提示来引导大语言模型产生期望输出的方法。",
    "descriptionEn": "A method that guides large language models to produce desired outputs by designing input prompts.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "prompt",
    "paperCount": 1234,
    "enabled": true
  },
  {
    "id": "alignment",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "模型对齐",
    "nameEn": "Alignment",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使人工智能模型的行为与人类意图和价值观保持一致的方法。",
    "descriptionEn": "A method that aligns the behavior of artificial intelligence models with human intentions and values.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "alignment",
    "paperCount": 1490,
    "enabled": true
  },
  {
    "id": "hallucination",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "幻觉",
    "nameEn": "Hallucination",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种大语言模型生成与事实不符或无依据内容的现象。",
    "descriptionEn": "A phenomenon in which large language models generate content that is factually inconsistent or unsupported.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "hallucination",
    "paperCount": 323,
    "enabled": true
  },
  {
    "id": "decoding",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "解码策略",
    "nameEn": "Decoding Strategies",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种控制大语言模型生成文本时词元选择方式的策略集合。",
    "descriptionEn": "A collection of strategies that control how large language models select tokens when generating text.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "decoding",
    "paperCount": 808,
    "enabled": true
  },
  {
    "id": "pretraining",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "预训练",
    "nameEn": "Pre-training",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大规模无标注数据上训练模型通用表征的初始训练阶段。",
    "descriptionEn": "An initial training phase that trains a model's general representations on large-scale unlabeled data.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "pretraining",
    "paperCount": 628,
    "enabled": true
  },
  {
    "id": "safety",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "模型安全",
    "nameEn": "Model Safety",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究人工智能模型有害输出防范与安全行为保障的方法。",
    "descriptionEn": "A method that studies the prevention of harmful outputs and the assurance of safe behavior in artificial intelligence models.",
    "followersCount": 0,
    "category": "大语言模型",
    "subjectQuery": "safety",
    "paperCount": 509,
    "enabled": true
  },
  {
    "id": "llm-agents",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "大语言模型智能体",
    "nameEn": "LLM Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种以大语言模型为核心推理引擎、能自主规划并执行复杂任务的智能体系统。",
    "descriptionEn": "An agent system that uses a large language model as its core reasoning engine and can autonomously plan and execute complex tasks.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "llm agents",
    "paperCount": 148,
    "enabled": true
  },
  {
    "id": "multi-agent-framework",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "多智能体框架",
    "nameEn": "Multi-Agent Framework",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种支持多个智能体协作交互以完成复杂任务的软件架构。",
    "descriptionEn": "A software architecture that supports multiple agents collaborating and interacting to complete complex tasks.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "multi-agent framework",
    "paperCount": 61,
    "enabled": true
  },
  {
    "id": "multi-agent-systems",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "多智能体系统",
    "nameEn": "Multi-Agent Systems",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由多个自主智能体通过交互与协作解决问题的计算系统。",
    "descriptionEn": "A computational system in which multiple autonomous agents solve problems through interaction and collaboration.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "multi-agent systems",
    "paperCount": 52,
    "enabled": true
  },
  {
    "id": "human-ai-collaboration",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "人机协作",
    "nameEn": "Human-AI Collaboration",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究人类与人工智能系统协同工作以提升任务效率的方法。",
    "descriptionEn": "A method that studies how humans and artificial intelligence systems work together to improve task efficiency.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "human-ai collaboration",
    "paperCount": 44,
    "enabled": true
  },
  {
    "id": "robotic-manipulation",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "机器人操作",
    "nameEn": "Robotic Manipulation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使机器人手臂对物体进行抓取、移动与操作的控制方法。",
    "descriptionEn": "A control method that enables robotic arms to grasp, move, and manipulate objects.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "robotic manipulation",
    "paperCount": 44,
    "enabled": true
  },
  {
    "id": "world-models",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "世界模型",
    "nameEn": "World Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种学习环境动态规律并可在内部模拟中进行规划的智能体模型。",
    "descriptionEn": "An agent model that learns the dynamics of an environment and can plan within internal simulations.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "world models",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "agentic-framework",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "智能体框架",
    "nameEn": "Agentic Framework",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种支持智能体自主规划、工具调用与任务执行的软件架构。",
    "descriptionEn": "A software architecture that supports autonomous planning, tool calling, and task execution by agents.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "agentic framework",
    "paperCount": 26,
    "enabled": true
  },
  {
    "id": "gui-agents",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "GUI智能体",
    "nameEn": "GUI Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够理解图形用户界面并通过鼠标键盘操作完成任务的智能体。",
    "descriptionEn": "An agent that can understand graphical user interfaces and complete tasks through mouse and keyboard operations.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "gui agents",
    "paperCount": 24,
    "enabled": true
  },
  {
    "id": "agentic-ai",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "智能体AI",
    "nameEn": "Agentic AI",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种具备自主规划、决策与执行能力的人工智能系统范式。",
    "descriptionEn": "A paradigm of artificial intelligence systems with autonomous planning, decision-making, and execution capabilities.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "agentic ai",
    "paperCount": 20,
    "enabled": true
  },
  {
    "id": "multi-agent-reinforcement-learning",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "多智能体强化学习",
    "nameEn": "Multi-Agent Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种多个智能体在共享环境中通过强化学习协同学习策略的方法。",
    "descriptionEn": "A method in which multiple agents collaboratively learn policies through reinforcement learning in a shared environment.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "multi-agent reinforcement learning",
    "paperCount": 20,
    "enabled": true
  },
  {
    "id": "embodied-ai",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "具身智能",
    "nameEn": "Embodied AI",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使人工智能系统具备物理身体并通过与环境交互学习的智能范式。",
    "descriptionEn": "A paradigm of intelligence in which an artificial intelligence system possesses a physical body and learns through interaction with the environment.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "embodied ai",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "tool-use",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "工具使用",
    "nameEn": "Tool Use",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使智能体能够调用外部工具（如搜索引擎、计算器）扩展能力的方法。",
    "descriptionEn": "A method that enables agents to call external tools such as search engines and calculators to extend their capabilities.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "tool use",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "embodied-agents",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "具身智能体",
    "nameEn": "Embodied Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在物理或仿真环境中具备身体并通过感知与行动完成任务的智能体。",
    "descriptionEn": "An agent that possesses a body in a physical or simulated environment and completes tasks through perception and action.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "embodied agents",
    "paperCount": 16,
    "enabled": true
  },
  {
    "id": "multi-agent-collaboration",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "多智能体协作",
    "nameEn": "Multi-Agent Collaboration",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种研究多个智能体通过分工与协作高效完成复杂任务的方法。",
    "descriptionEn": "A method that studies how multiple agents efficiently complete complex tasks through division of labor and collaboration.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "multi-agent collaboration",
    "paperCount": 16,
    "enabled": true
  },
  {
    "id": "theory-of-mind",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "心智理论",
    "nameEn": "Theory of Mind",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使智能体能够推断其他智能体或人类心理状态的认知建模方法。",
    "descriptionEn": "A cognitive modeling method that enables agents to infer the mental states of other agents or humans.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "theory of mind",
    "paperCount": 16,
    "enabled": true
  },
  {
    "id": "ai-agents",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "AI智能体",
    "nameEn": "AI Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够感知环境、自主决策并执行动作以达成目标的人工智能系统。",
    "descriptionEn": "An artificial intelligence system that can perceive its environment, make autonomous decisions, and execute actions to achieve goals.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "ai agents",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "agentic-reinforcement-learning",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "智能体强化学习",
    "nameEn": "Agentic Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将强化学习与智能体架构结合以训练自主决策智能体的方法。",
    "descriptionEn": "A method that combines reinforcement learning with agent architectures to train autonomous decision-making agents.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "agentic reinforcement learning",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "computer-use-agents",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "计算机使用智能体",
    "nameEn": "Computer-Use Agents",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够像人类一样操作计算机界面完成数字任务的智能体。",
    "descriptionEn": "An agent that can operate computer interfaces like a human to complete digital tasks.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "computer-use agents",
    "paperCount": 13,
    "enabled": true
  },
  {
    "id": "episodic-memory",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "情景记忆",
    "nameEn": "Episodic Memory",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使智能体存储并检索过往经历片段以辅助决策的记忆机制。",
    "descriptionEn": "A memory mechanism that enables agents to store and retrieve past experience episodes to aid decision-making.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "episodic memory",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "trajectory-planning",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "轨迹规划",
    "nameEn": "Trajectory Planning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种为机器人或智能体规划从起点到目标点的无碰撞运动路径的方法。",
    "descriptionEn": "A method that plans a collision-free motion path from a starting point to a target point for a robot or agent.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "trajectory planning",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "agent",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "智能体",
    "nameEn": "Agent",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够感知环境、自主决策并采取行动以达成目标的计算实体。",
    "descriptionEn": "A computational entity that can perceive its environment, make autonomous decisions, and take actions to achieve goals.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "agent",
    "paperCount": 1631,
    "enabled": true
  },
  {
    "id": "planning",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "任务规划",
    "nameEn": "Task Planning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将复杂目标分解为可执行步骤序列的智能体决策方法。",
    "descriptionEn": "An agent decision-making method that decomposes complex goals into sequences of executable steps.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "planning",
    "paperCount": 735,
    "enabled": true
  },
  {
    "id": "navigation",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "导航",
    "nameEn": "Navigation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种使移动机器人或智能体在环境中自主规划路径并到达目标的方法。",
    "descriptionEn": "A method that enables mobile robots or agents to autonomously plan paths and reach targets in an environment.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "navigation",
    "paperCount": 331,
    "enabled": true
  },
  {
    "id": "marl",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "多智能体强化学习",
    "nameEn": "Multi-Agent Reinforcement Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种多个智能体在共享环境中通过强化学习协同学习策略的方法。",
    "descriptionEn": "A method in which multiple agents collaboratively learn policies through reinforcement learning in a shared environment.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "marl",
    "paperCount": 162,
    "enabled": true
  },
  {
    "id": "robot",
    "imagePath": "/images/topics/reinforcement-learning-cover.png",
    "nameZh": "机器人",
    "nameEn": "Robot",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种能够自动执行任务的可编程机电装置。",
    "descriptionEn": "A programmable electromechanical device that can automatically execute tasks.",
    "followersCount": 0,
    "category": "智能体",
    "subjectQuery": "robot",
    "paperCount": 507,
    "enabled": true
  },
  {
    "id": "vision-language-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉语言模型",
    "nameEn": "Vision-Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时处理图像与文本并学习跨模态对齐表示的深度学习模型。",
    "descriptionEn": "A deep learning model that processes both images and text and learns cross-modal aligned representations.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "vision-language models",
    "paperCount": 634,
    "enabled": true
  },
  {
    "id": "multimodal-large-language-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态大语言模型",
    "nameEn": "Multimodal Large Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大语言模型基础上扩展视觉等多模态输入理解与生成能力的模型。",
    "descriptionEn": "A model that extends large language models with multimodal input understanding and generation capabilities such as vision.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal large language models",
    "paperCount": 282,
    "enabled": true
  },
  {
    "id": "large-vision-language-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "大视觉语言模型",
    "nameEn": "Large Vision-Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种具有大规模参数、能同时理解图像与文本的视觉语言模型。",
    "descriptionEn": "A vision-language model with large-scale parameters that can simultaneously understand images and text.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "large vision-language models",
    "paperCount": 92,
    "enabled": true
  },
  {
    "id": "vision-language-action-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉语言动作模型",
    "nameEn": "Vision-Language-Action Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将视觉感知、语言理解与动作决策统一建模的具身智能模型。",
    "descriptionEn": "An embodied intelligence model that unifies visual perception, language understanding, and action decision-making.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "vision-language-action models",
    "paperCount": 89,
    "enabled": true
  },
  {
    "id": "visual-grounding",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉定位",
    "nameEn": "Visual Grounding",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据自然语言描述在图像中定位对应物体区域的多模态方法。",
    "descriptionEn": "A multimodal method that locates the corresponding object region in an image based on a natural language description.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "visual grounding",
    "paperCount": 46,
    "enabled": true
  },
  {
    "id": "multimodal-reasoning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态推理",
    "nameEn": "Multimodal Reasoning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种融合多种模态信息进行逻辑推理与问题求解的方法。",
    "descriptionEn": "A method that fuses information from multiple modalities for logical reasoning and problem-solving.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal reasoning",
    "paperCount": 45,
    "enabled": true
  },
  {
    "id": "multimodal-learning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态学习",
    "nameEn": "Multimodal Learning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时利用多种模态数据进行模型训练与表征学习的机器学习方法。",
    "descriptionEn": "A machine learning method that simultaneously utilizes data from multiple modalities for model training and representation learning.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal learning",
    "paperCount": 42,
    "enabled": true
  },
  {
    "id": "multimodal-llms",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态大语言模型",
    "nameEn": "Multimodal LLMs",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种扩展了视觉等多模态输入能力的大语言模型。",
    "descriptionEn": "Large language models extended with multimodal input capabilities such as vision.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal llms",
    "paperCount": 38,
    "enabled": true
  },
  {
    "id": "cross-modal-alignment",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "跨模态对齐",
    "nameEn": "Cross-Modal Alignment",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种学习不同模态数据之间语义对应关系的多模态方法。",
    "descriptionEn": "A multimodal method that learns semantic correspondences between data from different modalities.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "cross-modal alignment",
    "paperCount": 37,
    "enabled": true
  },
  {
    "id": "large-multimodal-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "大多模态模型",
    "nameEn": "Large Multimodal Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种具有大规模参数、能处理与生成多种模态内容的基础模型。",
    "descriptionEn": "A foundation model with large-scale parameters that can process and generate content from multiple modalities.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "large multimodal models",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "visual-question-answering",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉问答",
    "nameEn": "Visual Question Answering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据图像内容回答自然语言问题的多模态方法。",
    "descriptionEn": "A multimodal method that answers natural language questions based on image content.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "visual question answering",
    "paperCount": 27,
    "enabled": true
  },
  {
    "id": "multimodal-benchmark",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态基准",
    "nameEn": "Multimodal Benchmark",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用于评测多模态模型能力的标准化数据集与评测指标集合。",
    "descriptionEn": "A standardized dataset and evaluation metric set used to assess the capabilities of multimodal models.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal benchmark",
    "paperCount": 23,
    "enabled": true
  },
  {
    "id": "multimodal-fusion",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态融合",
    "nameEn": "Multimodal Fusion",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将来自不同模态的特征进行整合以提升任务性能的多模态方法。",
    "descriptionEn": "A multimodal method that integrates features from different modalities to improve task performance.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal fusion",
    "paperCount": 22,
    "enabled": true
  },
  {
    "id": "cross-modal-retrieval",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "跨模态检索",
    "nameEn": "Cross-Modal Retrieval",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用一种模态的查询检索另一种模态相关数据的检索方法。",
    "descriptionEn": "A retrieval method that uses a query from one modality to retrieve relevant data from another modality.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "cross-modal retrieval",
    "paperCount": 16,
    "enabled": true
  },
  {
    "id": "unified-multimodal-models",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "统一多模态模型",
    "nameEn": "Unified Multimodal Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用单一模型架构同时处理多种模态理解与生成任务的模型。",
    "descriptionEn": "A model that uses a single architecture to simultaneously handle understanding and generation tasks across multiple modalities.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "unified multimodal models",
    "paperCount": 12,
    "enabled": true
  },
  {
    "id": "multimodal",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态",
    "nameEn": "Multimodal",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类涉及多种感官模态（如图像、文本、音频）联合处理的人工智能研究方向。",
    "descriptionEn": "A research direction in artificial intelligence involving the joint processing of multiple sensory modalities such as images, text, and audio.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "multimodal",
    "paperCount": 2104,
    "enabled": true
  },
  {
    "id": "clip",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "CLIP",
    "nameEn": "Contrastive Language-Image Pre-training",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过对比学习将图像与文本映射到同一嵌入空间的视觉语言预训练模型。",
    "descriptionEn": "A vision-language pre-training model that maps images and text to the same embedding space through contrastive learning.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "clip",
    "paperCount": 686,
    "enabled": true
  },
  {
    "id": "vlms",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉语言模型",
    "nameEn": "Vision-Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种同时处理图像与文本并学习跨模态对齐表示的深度学习模型。",
    "descriptionEn": "A deep learning model that processes both images and text and learns cross-modal aligned representations.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "vlms",
    "paperCount": 577,
    "enabled": true
  },
  {
    "id": "mllms",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "多模态大语言模型",
    "nameEn": "Multimodal Large Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在大语言模型基础上扩展视觉等多模态输入理解能力的模型。",
    "descriptionEn": "A model that extends large language models with multimodal input understanding capabilities such as vision.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "mllms",
    "paperCount": 530,
    "enabled": true
  },
  {
    "id": "vqa",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "视觉问答",
    "nameEn": "Visual Question Answering",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据图像内容回答自然语言问题的多模态任务。",
    "descriptionEn": "A multimodal task that answers natural language questions based on image content.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "vqa",
    "paperCount": 244,
    "enabled": true
  },
  {
    "id": "llava",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "LLaVA",
    "nameEn": "Large Language and Vision Assistant",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将视觉编码器与大语言模型连接的开源多模态助手模型。",
    "descriptionEn": "An open-source multimodal assistant model that connects a vision encoder with a large language model.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "llava",
    "paperCount": 76,
    "enabled": true
  },
  {
    "id": "captioning",
    "imagePath": "/images/topics/representation-learning-cover.png",
    "nameZh": "图像描述",
    "nameEn": "Image Captioning",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动为图像生成自然语言描述的多模态方法。",
    "descriptionEn": "A multimodal method that automatically generates natural language descriptions for images.",
    "followersCount": 0,
    "category": "多模态",
    "subjectQuery": "captioning",
    "paperCount": 320,
    "enabled": true
  },
  {
    "id": "speech",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "语音",
    "nameEn": "Speech",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类由人类发声器官产生的、承载语言信息的声学信号。",
    "descriptionEn": "Acoustic signals produced by human vocal organs that carry linguistic information.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "speech",
    "paperCount": 9898,
    "enabled": true
  },
  {
    "id": "speaker",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "说话人",
    "nameEn": "Speaker",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音信号的发出者，其声纹特征可用于身份识别与区分。",
    "descriptionEn": "The producer of a speech signal, whose voiceprint features can be used for identity recognition and differentiation.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "speaker",
    "paperCount": 2875,
    "enabled": true
  },
  {
    "id": "audio",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "音频",
    "nameEn": "Audio",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类可被人耳感知的声波信号及其数字化表示。",
    "descriptionEn": "Acoustic wave signals perceivable by the human ear and their digital representations.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "audio",
    "paperCount": 1720,
    "enabled": true
  },
  {
    "id": "asr",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "自动语音识别",
    "nameEn": "Automatic Speech Recognition",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将人类语音信号自动转换为文字文本的技术。",
    "descriptionEn": "A technology that automatically converts human speech signals into written text.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "asr",
    "paperCount": 1663,
    "enabled": true
  },
  {
    "id": "acoustic",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "声学",
    "nameEn": "Acoustics",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一门研究声波的产生、传播与感知及其在语音处理中应用的学科。",
    "descriptionEn": "A discipline that studies the production, propagation, and perception of sound waves and their application in speech processing.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "acoustic",
    "paperCount": 1523,
    "enabled": true
  },
  {
    "id": "voice",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "嗓音",
    "nameEn": "Voice",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "由声带振动产生的个体独特声学特征，可用于身份识别与情感分析。",
    "descriptionEn": "An individual's unique acoustic features produced by vocal cord vibration, usable for identity recognition and emotion analysis.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "voice",
    "paperCount": 1279,
    "enabled": true
  },
  {
    "id": "spoken",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "口语",
    "nameEn": "Spoken Language",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类以口头表达为载体的自然语言形式及其处理方法。",
    "descriptionEn": "A form of natural language expressed orally and its processing methods.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "spoken",
    "paperCount": 1134,
    "enabled": true
  },
  {
    "id": "emotion",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "语音情感",
    "nameEn": "Speech Emotion",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音信号中承载的情感状态信息及其自动识别方法。",
    "descriptionEn": "Emotional state information carried in speech signals and its automatic recognition methods.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "emotion",
    "paperCount": 874,
    "enabled": true
  },
  {
    "id": "frequency",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "频率",
    "nameEn": "Frequency",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "声波每秒振动的次数，是语音信号分析的基本物理量。",
    "descriptionEn": "The number of vibrations per second of a sound wave, a fundamental physical quantity in speech signal analysis.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "frequency",
    "paperCount": 735,
    "enabled": true
  },
  {
    "id": "prosodic",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "韵律",
    "nameEn": "Prosody",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音中由音高、时长与强度变化构成的超音段特征。",
    "descriptionEn": "Suprasegmental features in speech composed of variations in pitch, duration, and intensity.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "prosodic",
    "paperCount": 662,
    "enabled": true
  },
  {
    "id": "tts",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "文本转语音",
    "nameEn": "Text-to-Speech",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将文字文本自动转换为自然流畅语音的合成技术。",
    "descriptionEn": "A synthesis technology that automatically converts written text into natural and fluent speech.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "tts",
    "paperCount": 632,
    "enabled": true
  },
  {
    "id": "phonetic",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "语音学",
    "nameEn": "Phonetics",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一门研究人类语音的产生、传播与感知特性的学科。",
    "descriptionEn": "A discipline that studies the production, transmission, and perceptual properties of human speech sounds.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "phonetic",
    "paperCount": 565,
    "enabled": true
  },
  {
    "id": "hmm",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "隐马尔可夫模型",
    "nameEn": "Hidden Markov Model",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种用隐含状态序列建模观测序列概率分布的统计模型，曾广泛用于语音识别。",
    "descriptionEn": "A statistical model that models the probability distribution of observation sequences using hidden state sequences, formerly widely used in speech recognition.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "hmm",
    "paperCount": 535,
    "enabled": true
  },
  {
    "id": "conversion",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "语音转换",
    "nameEn": "Voice Conversion",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将说话人的语音特征转换为另一说话人风格同时保留语义内容的技术。",
    "descriptionEn": "A technology that converts a speaker's voice features to another speaker's style while preserving semantic content.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "conversion",
    "paperCount": 516,
    "enabled": true
  },
  {
    "id": "utterances",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "话语",
    "nameEn": "Utterances",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音中由停顿分隔的连续发声片段，是语音处理的基本单位。",
    "descriptionEn": "Continuous speech segments separated by pauses, the basic unit of speech processing.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "utterances",
    "paperCount": 498,
    "enabled": true
  },
  {
    "id": "phoneme",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "音素",
    "nameEn": "Phoneme",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种语言中能够区分词义的最小语音单位。",
    "descriptionEn": "The smallest unit of speech in a language that can distinguish word meaning.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "phoneme",
    "paperCount": 495,
    "enabled": true
  },
  {
    "id": "pitch",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "音高",
    "nameEn": "Pitch",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音基频的感知对应量，是韵律与语调的核心参数。",
    "descriptionEn": "The perceptual correlate of speech fundamental frequency, a core parameter of prosody and intonation.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "pitch",
    "paperCount": 483,
    "enabled": true
  },
  {
    "id": "signals",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "信号",
    "nameEn": "Audio Signals",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "承载语音或音频信息的一维时间序列电信号。",
    "descriptionEn": "One-dimensional time-series electrical signals carrying speech or audio information.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "signals",
    "paperCount": 476,
    "enabled": true
  },
  {
    "id": "sound",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "声音",
    "nameEn": "Sound",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "由物体振动产生并通过介质传播的可听机械波。",
    "descriptionEn": "Audible mechanical waves produced by vibrating objects and propagating through a medium.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "sound",
    "paperCount": 427,
    "enabled": true
  },
  {
    "id": "articulatory",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "发音语音学",
    "nameEn": "Articulatory Phonetics",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一门研究人类发音器官如何产生语音的学科。",
    "descriptionEn": "A discipline that studies how human articulatory organs produce speech sounds.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "articulatory",
    "paperCount": 426,
    "enabled": true
  },
  {
    "id": "emotional",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "情感语音",
    "nameEn": "Emotional Speech",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "带有情感色彩的语音信号及其特征分析与合成方法。",
    "descriptionEn": "Speech signals with emotional coloring and their feature analysis and synthesis methods.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "emotional",
    "paperCount": 426,
    "enabled": true
  },
  {
    "id": "pronunciation",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "发音",
    "nameEn": "Pronunciation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种语言中语音的标准发音方式及其评估方法。",
    "descriptionEn": "The standard way of producing speech sounds in a language and its evaluation methods.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "pronunciation",
    "paperCount": 420,
    "enabled": true
  },
  {
    "id": "separation",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "语音分离",
    "nameEn": "Speech Separation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从混合音频中分离出不同说话人或声源语音信号的方法。",
    "descriptionEn": "A method that separates speech signals of different speakers or sound sources from mixed audio.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "separation",
    "paperCount": 411,
    "enabled": true
  },
  {
    "id": "mandarin",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "普通话",
    "nameEn": "Mandarin",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "中国大陆的标准汉语口语及其语音处理方法。",
    "descriptionEn": "The standard spoken Chinese in mainland China and its speech processing methods.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "mandarin",
    "paperCount": 402,
    "enabled": true
  },
  {
    "id": "vowel",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "元音",
    "nameEn": "Vowel",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类发音时气流不受阻碍、声带振动的语音音素。",
    "descriptionEn": "A class of speech phonemes produced with unobstructed airflow and vibrating vocal cords.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "vowel",
    "paperCount": 393,
    "enabled": true
  },
  {
    "id": "channel",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "声道",
    "nameEn": "Vocal Tract",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "从声带到嘴唇的共鸣腔，其形状变化决定语音的音色特征。",
    "descriptionEn": "The resonant cavity from the vocal cords to the lips, whose shape changes determine the timbre of speech.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "channel",
    "paperCount": 392,
    "enabled": true
  },
  {
    "id": "intelligibility",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "可懂度",
    "nameEn": "Speech Intelligibility",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种衡量语音信号被听者正确理解程度的客观指标。",
    "descriptionEn": "An objective metric that measures the degree to which speech signals are correctly understood by listeners.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "intelligibility",
    "paperCount": 385,
    "enabled": true
  },
  {
    "id": "signal",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "音频信号",
    "nameEn": "Audio Signal",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "承载声音信息的随时间变化的电信号或数字序列。",
    "descriptionEn": "Time-varying electrical signals or digital sequences that carry sound information.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "signal",
    "paperCount": 381,
    "enabled": true
  },
  {
    "id": "iwslt",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "国际口语翻译研讨会",
    "nameEn": "International Workshop on Spoken Language Translation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一个专注于口语语音翻译技术研究与评测的学术会议。",
    "descriptionEn": "An academic conference focused on research and evaluation of spoken language translation technology.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "iwslt",
    "paperCount": 378,
    "enabled": true
  },
  {
    "id": "prosody",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "韵律学",
    "nameEn": "Prosody",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一门研究语音中音高、时长与重音等超音段特征的学科。",
    "descriptionEn": "A discipline that studies suprasegmental features in speech such as pitch, duration, and stress.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "prosody",
    "paperCount": 375,
    "enabled": true
  },
  {
    "id": "phone",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "音子",
    "nameEn": "Phone",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音中实际发出的最小语音单位，是音素在具体语境中的实现。",
    "descriptionEn": "The smallest actually produced unit of speech, the realization of a phoneme in a specific context.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "phone",
    "paperCount": 337,
    "enabled": true
  },
  {
    "id": "wer",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "词错误率",
    "nameEn": "Word Error Rate",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种衡量自动语音识别系统性能的标准指标，计算识别结果与参考文本的词级编辑距离。",
    "descriptionEn": "A standard metric for measuring automatic speech recognition system performance, computing word-level edit distance between recognition results and reference text.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "wer",
    "paperCount": 334,
    "enabled": true
  },
  {
    "id": "gmm",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "高斯混合模型",
    "nameEn": "Gaussian Mixture Model",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由多个高斯分布加权组合而成的概率模型，曾用于语音识别声学建模。",
    "descriptionEn": "A probabilistic model composed of a weighted combination of multiple Gaussian distributions, formerly used for acoustic modeling in speech recognition.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "gmm",
    "paperCount": 333,
    "enabled": true
  },
  {
    "id": "listeners",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "听者",
    "nameEn": "Listeners",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音信号的接收者，其感知特性是语音质量评估的重要依据。",
    "descriptionEn": "Receivers of speech signals whose perceptual characteristics are important for speech quality assessment.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "listeners",
    "paperCount": 316,
    "enabled": true
  },
  {
    "id": "duration",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "时长",
    "nameEn": "Duration",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "语音片段或音素持续的时间长度，是韵律分析的重要参数。",
    "descriptionEn": "The length of time a speech segment or phoneme lasts, an important parameter in prosodic analysis.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "duration",
    "paperCount": 310,
    "enabled": true
  },
  {
    "id": "vowels",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "元音",
    "nameEn": "Vowels",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类发音时气流不受阻碍、声带振动的语音音素的集合。",
    "descriptionEn": "A collection of speech phonemes produced with unobstructed airflow and vibrating vocal cords.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "vowels",
    "paperCount": 299,
    "enabled": true
  },
  {
    "id": "auditory",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "听觉",
    "nameEn": "Auditory",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类研究人耳与听觉系统对声音感知与处理机制的学科。",
    "descriptionEn": "A discipline that studies the mechanisms of sound perception and processing by the human ear and auditory system.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "auditory",
    "paperCount": 290,
    "enabled": true
  },
  {
    "id": "text-to-speech",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "文本转语音",
    "nameEn": "Text-to-Speech",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将文字文本自动转换为自然流畅语音的合成技术。",
    "descriptionEn": "A synthesis technology that automatically converts written text into natural and fluent speech.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "text-to-speech",
    "paperCount": 14,
    "enabled": true
  },
  {
    "id": "beamforming",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "波束成形",
    "nameEn": "Beamforming",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过麦克风阵列信号处理增强目标方向语音并抑制噪声的方法。",
    "descriptionEn": "A method that enhances speech from a target direction and suppresses noise through microphone array signal processing.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "beamforming",
    "paperCount": 66,
    "enabled": true
  },
  {
    "id": "reverberation",
    "imagePath": "/images/topics/translation-cover.png",
    "nameZh": "混响",
    "nameEn": "Reverberation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "声波在封闭空间中经多次反射后形成的持续衰减声学现象。",
    "descriptionEn": "A persistent decaying acoustic phenomenon formed by multiple reflections of sound waves in an enclosed space.",
    "followersCount": 0,
    "category": "语音/音频处理",
    "subjectQuery": "reverberation",
    "paperCount": 95,
    "enabled": true
  },
  {
    "id": "diffusion-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "扩散模型",
    "nameEn": "Diffusion Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过逐步去噪从随机噪声中生成高质量数据的生成模型。",
    "descriptionEn": "A generative model that generates high-quality data from random noise through iterative denoising.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "diffusion models",
    "paperCount": 328,
    "enabled": true
  },
  {
    "id": "flow-matching",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "流匹配",
    "nameEn": "Flow Matching",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过学习概率流路径上的向量场来生成数据的生成模型方法。",
    "descriptionEn": "A generative model method that generates data by learning vector fields along probability flow paths.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "flow matching",
    "paperCount": 122,
    "enabled": true
  },
  {
    "id": "text-to-image-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "文本生成图像",
    "nameEn": "Text-to-Image Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据自然语言描述自动生成对应图像的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates corresponding images from natural language descriptions.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "text-to-image generation",
    "paperCount": 74,
    "enabled": true
  },
  {
    "id": "novel-view-synthesis",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "新视角合成",
    "nameEn": "Novel View Synthesis",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种从已知视角图像生成未观测视角图像的计算机视觉方法。",
    "descriptionEn": "A computer vision method that generates images from unobserved viewpoints based on images from known viewpoints.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "novel view synthesis",
    "paperCount": 57,
    "enabled": true
  },
  {
    "id": "video-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "视频生成",
    "nameEn": "Video Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据文本或图像自动生成连续视频序列的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates continuous video sequences from text or images.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "video generation",
    "paperCount": 56,
    "enabled": true
  },
  {
    "id": "diffusion-transformer",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "扩散Transformer",
    "nameEn": "Diffusion Transformer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将Transformer架构用于扩散模型去噪网络的生成模型。",
    "descriptionEn": "A generative model that uses the Transformer architecture as the denoising network in a diffusion model.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "diffusion transformer",
    "paperCount": 55,
    "enabled": true
  },
  {
    "id": "sparse-autoencoders",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "稀疏自编码器",
    "nameEn": "Sparse Autoencoders",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过稀疏约束学习可解释特征表示的无监督神经网络模型。",
    "descriptionEn": "An unsupervised neural network model that learns interpretable feature representations through sparsity constraints.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "sparse autoencoders",
    "paperCount": 55,
    "enabled": true
  },
  {
    "id": "image-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "图像生成",
    "nameEn": "Image Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种自动生成符合特定条件或风格的新图像的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates new images conforming to specific conditions or styles.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "image generation",
    "paperCount": 41,
    "enabled": true
  },
  {
    "id": "diffusion-language-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "扩散语言模型",
    "nameEn": "Diffusion Language Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将扩散过程应用于离散文本生成的语言模型。",
    "descriptionEn": "A language model that applies the diffusion process to discrete text generation.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "diffusion language models",
    "paperCount": 40,
    "enabled": true
  },
  {
    "id": "generative-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "生成模型",
    "nameEn": "Generative Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类学习数据分布并能够生成新样本的机器学习模型。",
    "descriptionEn": "A class of machine learning models that learn data distributions and can generate new samples.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "generative models",
    "paperCount": 40,
    "enabled": true
  },
  {
    "id": "generative-ai",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "生成式AI",
    "nameEn": "Generative AI",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类能够生成文本、图像、音频等新内容的人工智能技术。",
    "descriptionEn": "A class of artificial intelligence technologies capable of generating new content such as text, images, and audio.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "generative ai",
    "paperCount": 33,
    "enabled": true
  },
  {
    "id": "knowledge-editing",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "知识编辑",
    "nameEn": "Knowledge Editing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在不重新训练的情况下修改大模型中特定知识的方法。",
    "descriptionEn": "A method that modifies specific knowledge in a large model without retraining.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "knowledge editing",
    "paperCount": 32,
    "enabled": true
  },
  {
    "id": "image-editing",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "图像编辑",
    "nameEn": "Image Editing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据文本指令或局部修改对图像进行编辑的生成式AI方法。",
    "descriptionEn": "A generative AI method that edits images based on text instructions or local modifications.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "image editing",
    "paperCount": 31,
    "enabled": true
  },
  {
    "id": "data-synthesis",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "数据合成",
    "nameEn": "Data Synthesis",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用生成模型自动合成人工训练数据以扩充数据集的方法。",
    "descriptionEn": "A method that uses generative models to automatically synthesize artificial training data to expand datasets.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "data synthesis",
    "paperCount": 30,
    "enabled": true
  },
  {
    "id": "generative-modeling",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "生成建模",
    "nameEn": "Generative Modeling",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种学习数据概率分布并从中采样生成新样本的机器学习范式。",
    "descriptionEn": "A machine learning paradigm that learns the probability distribution of data and samples new samples from it.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "generative modeling",
    "paperCount": 25,
    "enabled": true
  },
  {
    "id": "discrete-diffusion",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "离散扩散",
    "nameEn": "Discrete Diffusion",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将扩散过程应用于离散数据（如文本）生成的方法。",
    "descriptionEn": "A method that applies the diffusion process to the generation of discrete data such as text.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "discrete diffusion",
    "paperCount": 24,
    "enabled": true
  },
  {
    "id": "latent-diffusion",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "隐空间扩散",
    "nameEn": "Latent Diffusion",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在压缩后的隐空间中执行扩散过程以降低计算成本的生成模型。",
    "descriptionEn": "A generative model that performs the diffusion process in a compressed latent space to reduce computational cost.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "latent diffusion",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "video-diffusion-models",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "视频扩散模型",
    "nameEn": "Video Diffusion Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于扩散模型生成高质量视频序列的生成模型。",
    "descriptionEn": "A generative model based on diffusion models for generating high-quality video sequences.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "video diffusion models",
    "paperCount": 21,
    "enabled": true
  },
  {
    "id": "model-editing",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "模型编辑",
    "nameEn": "Model Editing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在不重新训练的情况下修改神经网络模型特定行为或知识的方法。",
    "descriptionEn": "A method that modifies specific behaviors or knowledge of a neural network model without retraining.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "model editing",
    "paperCount": 18,
    "enabled": true
  },
  {
    "id": "text-to-video-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "文本生成视频",
    "nameEn": "Text-to-Video Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据自然语言描述自动生成对应视频的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates corresponding videos from natural language descriptions.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "text-to-video generation",
    "paperCount": 15,
    "enabled": true
  },
  {
    "id": "3d-generation",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "三维生成",
    "nameEn": "3D Generation",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据文本或图像自动生成三维物体或场景的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates 3D objects or scenes from text or images.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "3d generation",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "normalizing-flows",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "归一化流",
    "nameEn": "Normalizing Flows",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过可逆变换将简单分布映射为复杂数据分布的生成模型。",
    "descriptionEn": "A generative model that maps a simple distribution to a complex data distribution through invertible transformations.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "normalizing flows",
    "paperCount": 11,
    "enabled": true
  },
  {
    "id": "diffusion",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "扩散模型",
    "nameEn": "Diffusion Models",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过逐步去噪从随机噪声中生成高质量数据的生成模型。",
    "descriptionEn": "A generative model that generates high-quality data from random noise through iterative denoising.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "diffusion",
    "paperCount": 2780,
    "enabled": true
  },
  {
    "id": "gan",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "生成对抗网络",
    "nameEn": "Generative Adversarial Network",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过生成器与判别器对抗训练来学习数据分布的生成模型。",
    "descriptionEn": "A generative model that learns data distributions through adversarial training between a generator and a discriminator.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "gan",
    "paperCount": 305,
    "enabled": true
  },
  {
    "id": "vae",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "变分自编码器",
    "nameEn": "Variational Autoencoder",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种基于变分推断学习数据隐变量表示的生成模型。",
    "descriptionEn": "A generative model that learns latent variable representations of data based on variational inference.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "vae",
    "paperCount": 203,
    "enabled": true
  },
  {
    "id": "autoencoder",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "自编码器",
    "nameEn": "Autoencoder",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种通过编码器-解码器架构学习数据压缩表示并重建输入的神经网络模型。",
    "descriptionEn": "A neural network model that learns compressed representations of data and reconstructs inputs through an encoder-decoder architecture.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "autoencoder",
    "paperCount": 219,
    "enabled": true
  },
  {
    "id": "watermarking",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "水印",
    "nameEn": "Watermarking",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种在生成内容中嵌入不可见标识以追踪来源与版权的方法。",
    "descriptionEn": "A method that embeds invisible markers in generated content to trace origin and copyright.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "watermarking",
    "paperCount": 172,
    "enabled": true
  },
  {
    "id": "t2i",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "文本生成图像",
    "nameEn": "Text-to-Image",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据自然语言描述自动生成对应图像的生成式AI方法。",
    "descriptionEn": "A generative AI method that automatically generates corresponding images from natural language descriptions.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "t2i",
    "paperCount": 167,
    "enabled": true
  },
  {
    "id": "inpainting",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "图像修复",
    "nameEn": "Image Inpainting",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据周围上下文填充图像中缺失或损坏区域的生成式AI方法。",
    "descriptionEn": "A generative AI method that fills missing or damaged regions in an image based on surrounding context.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "inpainting",
    "paperCount": 150,
    "enabled": true
  },
  {
    "id": "avatar",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "数字人",
    "nameEn": "Digital Avatar",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种由人工智能生成或驱动的虚拟人物形象。",
    "descriptionEn": "A virtual human character generated or driven by artificial intelligence.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "avatar",
    "paperCount": 142,
    "enabled": true
  },
  {
    "id": "deepfake",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "深度伪造",
    "nameEn": "Deepfake",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种利用深度学习技术生成或篡改人脸与语音的伪造内容。",
    "descriptionEn": "Forged content in which faces and voices are generated or manipulated using deep learning techniques.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "deepfake",
    "paperCount": 136,
    "enabled": true
  },
  {
    "id": "style",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "风格迁移",
    "nameEn": "Style Transfer",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种将一幅图像的艺术风格迁移到另一幅图像内容上的生成式AI方法。",
    "descriptionEn": "A generative AI method that transfers the artistic style of one image onto the content of another image.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "style",
    "paperCount": 701,
    "enabled": true
  },
  {
    "id": "editing",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "内容编辑",
    "nameEn": "Content Editing",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种根据指令对生成内容（图像、文本等）进行局部修改的方法。",
    "descriptionEn": "A method that performs local modifications to generated content such as images and text based on instructions.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "editing",
    "paperCount": 818,
    "enabled": true
  },
  {
    "id": "synthesis",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "合成",
    "nameEn": "Synthesis",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一类利用模型自动生成新的语音、图像或文本内容的技术。",
    "descriptionEn": "A class of technologies that use models to automatically generate new speech, image, or text content.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "synthesis",
    "paperCount": 1281,
    "enabled": true
  },
  {
    "id": "fidelity",
    "imagePath": "/images/topics/language-models-cover.png",
    "nameZh": "保真度",
    "nameEn": "Fidelity",
    "author": {
      "id": "shenzhi",
      "name": "深知",
      "avatarUrl": "/brand/logo-night.png",
      "isVerified": true
    },
    "descriptionZh": "一种衡量生成内容与真实数据或参考输入相似程度的指标。",
    "descriptionEn": "A metric that measures the degree of similarity between generated content and real data or reference inputs.",
    "followersCount": 0,
    "category": "生成式AI",
    "subjectQuery": "fidelity",
    "paperCount": 282,
    "enabled": true
  }
] as KnowledgeTopic[];

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
