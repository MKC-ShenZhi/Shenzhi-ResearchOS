import type { PaperGraph } from "@/types";
import { paperDetail } from "./data-paper-detail";

/** 公域知识图谱 —— RDT-1B 引用关系宇宙(节点标签 = 一作姓 + 年份) */
export const publicGraph: PaperGraph = {
  origin: {
    id: "liu-2024",
    labelLines: ["Liu", "2024"],
    weight: 1,
    year: 2024,
    title: paperDetail.title,
    authors: "Songming Liu, Lingxuan Wu, Bangguo Li, et al.",
    venue: "arXiv",
    citations: "引用 312",
    abstract: paperDetail.abstract,
    paperId: "rdt-1b",
  },
  nodes: [
    {
      id: "chi-2023",
      labelLines: ["Chi", "2023"],
      weight: 0.95, year: 2023,
      title: "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion",
      authors: "Cheng Chi, Siyuan Feng, Yilun Du, et al.",
      venue: "CoRL 2023", citations: "引用 1.8k",
      abstract:
        "We introduce Diffusion Policy, a new way of generating robot behavior by representing a robot's visuomotor policy as a conditional denoising diffusion process. Across 12 tasks from 4 benchmarks, Diffusion Policy outperforms existing state-of-the-art robot learning methods with an average improvement of 46.9%.",
    },
    {
      id: "kim-2024",
      labelLines: ["Kim", "2024"],
      weight: 0.8, year: 2024,
      title: "OpenVLA: An Open-Source Vision-Language-Action Model",
      authors: "Moo Jin Kim, Karl Pertsch, Siddharth Karamcheti, et al.",
      venue: "CoRL 2024", citations: "引用 890",
      abstract:
        "OpenVLA is a 7B-parameter open-source vision-language-action model trained on 970k robot demonstrations from the Open X-Embodiment dataset, achieving strong zero-shot generalization across embodiments and supporting efficient fine-tuning for new tasks.",
    },
    {
      id: "ze-2024",
      labelLines: ["Ze", "2024"],
      weight: 0.72, year: 2024,
      title: "3D Diffusion Policy: Generalizable Visuomotor Policy Learning via Simple 3D Representations",
      authors: "Yanjie Ze, Gu Zhang, Kangning Zhang, et al.",
      venue: "RSS 2024", citations: "引用 642",
      abstract:
        "DP3 incorporates 3D visual representations into diffusion policies, achieving strong performance with as few as 10 demonstrations and exhibiting robust generalization to unseen scenes, instances, and embodiments.",
    },
    {
      id: "black-2024",
      labelLines: ["Black", "2024"],
      weight: 0.7, year: 2024,
      title: "π0: A Vision-Language-Action Flow Model for General Robot Control",
      authors: "Kevin Black, Noah Brown, Danny Driess, et al.",
      venue: "arXiv 2024", citations: "引用 460",
      abstract:
        "We introduce π0, a flow-matching vision-language-action model that transfers internet-scale pretraining to dexterous robot control, enabling zero-shot folding, table bussing, and box packing across multiple robot platforms.",
    },
    {
      id: "ghosh-2024",
      labelLines: ["Ghosh", "2024"],
      weight: 0.68, year: 2024,
      title: "Octo: An Open-Source Generalist Robot Policy",
      authors: "Dibya Ghosh, Homer Walke, Karl Pertsch, et al.",
      venue: "RSS 2024", citations: "引用 520",
      abstract:
        "Octo is an open-source transformer-based generalist robot policy trained on 800k trajectories from Open X-Embodiment, supporting flexible task conditioning and efficient adaptation to new sensors and action spaces.",
    },
    {
      id: "khazatsky-2024",
      labelLines: ["Khazatsky", "2024"],
      weight: 0.65, year: 2024,
      title: "DROID: A Large-Scale In-the-Wild Robot Manipulation Dataset",
      authors: "Alexander Khazatsky, Karl Pertsch, Suraj Nair, et al.",
      venue: "ICRA 2024", citations: "引用 380",
      abstract:
        "DROID is a diverse robot manipulation dataset with 76k demonstration trajectories collected across 564 scenes and 86 tasks, designed to train policies that generalize to novel real-world environments.",
    },
    {
      id: "brohan-2023",
      labelLines: ["Brohan", "2023"],
      weight: 0.6, year: 2023,
      title: "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
      authors: "Anthony Brohan, Noah Brown, Justice Carbajal, et al.",
      venue: "CoRL 2023", citations: "引用 1.5k",
      abstract:
        "RT-2 co-fine-tunes vision-language models on web data and robot trajectories, producing vision-language-action policies that exhibit emergent semantic generalization to unseen objects and instructions.",
    },
    {
      id: "wen-2026",
      labelLines: ["Wen", "2026"],
      weight: 0.55, year: 2026,
      title: "DexMamba: 面向灵巧手控制的视觉状态空间扩散模型",
      authors: "Yuxuan Wen, Zhaohui Li, Manping Sun, et al.",
      venue: "arXiv 2026", citations: "引用 89",
      abstract:
        "DexMamba combines selective state-space backbones with diffusion action heads for dexterous hand control, achieving real-time 60Hz inference while preserving long-horizon temporal consistency.",
    },
    {
      id: "ho-2020",
      labelLines: ["Ho", "2020"],
      weight: 0.5, year: 2020,
      title: "Denoising Diffusion Probabilistic Models",
      authors: "Jonathan Ho, Ajay Jain, Pieter Abbeel",
      venue: "NeurIPS 2020", citations: "引用 12k",
      abstract:
        "We present high-quality image synthesis results using diffusion probabilistic models, a class of latent variable models inspired by non-equilibrium thermodynamics, achieving competitive log-likelihoods and FID scores.",
    },
    {
      id: "vaswani-2017",
      labelLines: ["Vaswani", "2017"],
      weight: 0.45, year: 2017,
      title: "Attention Is All You Need",
      authors: "Ashish Vaswani, Noam Shazeer, Niki Parmar, et al.",
      venue: "NeurIPS 2017", citations: "引用 128k",
      abstract:
        "We propose the Transformer, a network architecture based solely on attention mechanisms, dispensing with recurrence and convolutions entirely, achieving state-of-the-art translation quality with substantially less training time.",
    },
    {
      id: "fu-2024",
      labelLines: ["Fu", "2024"],
      weight: 0.42, year: 2024,
      title: "Mobile ALOHA: Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation",
      authors: "Zipeng Fu, Tony Z. Zhao, Chelsea Finn",
      venue: "RSS 2024", citations: "引用 410",
      abstract:
        "Mobile ALOHA extends bimanual teleoperation to mobile manipulation with a low-cost whole-body interface, enabling imitation learning of complex long-horizon household tasks with high success rates.",
    },
    {
      id: "song-2021",
      labelLines: ["Song", "2021"],
      weight: 0.38, year: 2021,
      title: "Score-Based Generative Modeling through Stochastic Differential Equations",
      authors: "Yang Song, Jascha Sohl-Dickstein, Diederik P. Kingma, et al.",
      venue: "ICLR 2021", citations: "引用 6.4k",
      abstract:
        "We present a stochastic differential equation framework that unifies and generalizes score-based generative modeling and diffusion probabilistic models, enabling exact likelihood computation and controllable generation.",
    },
    {
      id: "zhao-2023",
      labelLines: ["Zhao", "2023"],
      weight: 0.35, year: 2023,
      title: "Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware",
      authors: "Tony Z. Zhao, Vikash Kumar, Sergey Levine, Chelsea Finn",
      venue: "RSS 2023", citations: "引用 690",
      abstract:
        "ALOHA is a low-cost bimanual teleoperation system; combined with Action Chunking with Transformers (ACT), it learns fine-grained tasks like threading zip ties from only 50 demonstrations.",
    },
    {
      id: "reed-2022",
      labelLines: ["Reed", "2022"],
      weight: 0.3, year: 2022,
      title: "A Generalist Agent",
      authors: "Scott Reed, Konrad Żołna, Emilio Parisotto, et al.",
      venue: "TMLR 2022", citations: "引用 2.1k",
      abstract:
        "Gato is a single generalist transformer trained on a wide variety of tasks — from Atari and robotics to image captioning and chat — demonstrating that a single model can sequence actions across modalities.",
    },
  ],
  edges: [
    { source: "liu-2024", target: "chi-2023", strength: 0.95 },
    { source: "liu-2024", target: "kim-2024", strength: 0.8 },
    { source: "liu-2024", target: "ze-2024", strength: 0.72 },
    { source: "liu-2024", target: "black-2024", strength: 0.7 },
    { source: "liu-2024", target: "ghosh-2024", strength: 0.68 },
    { source: "liu-2024", target: "khazatsky-2024", strength: 0.65 },
    { source: "liu-2024", target: "brohan-2023", strength: 0.6 },
    { source: "liu-2024", target: "wen-2026", strength: 0.55 },
    { source: "liu-2024", target: "ho-2020", strength: 0.5 },
    { source: "liu-2024", target: "vaswani-2017", strength: 0.45 },
    { source: "liu-2024", target: "fu-2024", strength: 0.42 },
    { source: "liu-2024", target: "song-2021", strength: 0.38 },
    { source: "liu-2024", target: "zhao-2023", strength: 0.35 },
    { source: "liu-2024", target: "reed-2022", strength: 0.3 },
    { source: "chi-2023", target: "ze-2024", strength: 0.8 },
    { source: "ho-2020", target: "song-2021", strength: 0.7 },
    { source: "zhao-2023", target: "fu-2024", strength: 0.85 },
    { source: "vaswani-2017", target: "brohan-2023", strength: 0.5 },
    { source: "kim-2024", target: "ghosh-2024", strength: 0.6 },
    { source: "black-2024", target: "chi-2023", strength: 0.55 },
  ],
  relatedIds: [
    "chi-2023", "kim-2024", "ze-2024", "black-2024", "ghosh-2024",
    "khazatsky-2024", "brohan-2023", "wen-2026", "ho-2020",
    "vaswani-2017", "fu-2024", "song-2021", "zhao-2023", "reed-2022",
  ],
};

/** 私域知识图谱 —— 我的发表 × 收藏论文 分层(节点标签 = 关键词 + 年份) */
export const privateGraph: PaperGraph = {
  origin: {
    id: "m1",
    labelLines: ["扩散策略", "2025"],
    weight: 0.9, year: 2025, layer: "mine",
    title: "Hierarchical Diffusion Policies for Contact-Rich Manipulation",
    authors: "陈知行, 王璐, 李慕白",
    venue: "ICRA 2026(under review)", citations: "预印本",
    abstract:
      "We propose a hierarchical diffusion policy that decouples contact-rich manipulation into a contact-planning diffusion head and a motion-execution transformer, improving success rates by 23% on insertion and deformable-object tasks while keeping 30Hz closed-loop control.",
  },
  nodes: [
    {
      id: "m2",
      labelLines: ["机器人基础模型", "2024"],
      weight: 0.72, year: 2024, layer: "mine",
      title: "Cross-Embodiment Pretraining for Robot Foundation Models",
      authors: "陈知行, 李慕白, 赵启明",
      venue: "arXiv 2024", citations: "引用 86",
      abstract:
        "A masked action-modeling pretraining objective that shares a single policy backbone across 6 robot embodiments, reducing per-embodiment fine-tuning data requirements by 4×.",
    },
    {
      id: "m3",
      labelLines: ["视觉伺服", "2022"],
      weight: 0.48, year: 2022, layer: "mine",
      title: "Visual Servoing via Learned Keypoint Affordances",
      authors: "陈知行, 吴桐",
      venue: "IROS 2022", citations: "引用 41",
      abstract:
        "We learn dense keypoint affordance fields from self-supervised interaction and use them as the visual feedback signal for closed-loop servoing of deformable and articulated objects.",
    },
    {
      id: "f7",
      labelLines: ["机器人学习", "2024"],
      weight: 0.85, year: 2024, layer: "folder",
      title: paperDetail.title,
      authors: "Songming Liu, Lingxuan Wu, Bangguo Li, et al.",
      venue: "arXiv 2024", citations: "引用 312",
      abstract: paperDetail.abstract,
      paperId: "rdt-1b",
    },
    {
      id: "f1",
      labelLines: ["扩散模型", "2025"],
      weight: 0.8, year: 2025, layer: "folder",
      title: "Diffusion Models for Iterative Video Frame Interpolation",
      authors: "Zhang Wei, Chen Li, Wang Ming",
      venue: "CVPR 2025", citations: "引用 96",
      abstract:
        "We formulate video frame interpolation as an iterative denoising process over motion-compensated latent frames, improving temporal consistency on fast-motion benchmarks.",
    },
    {
      id: "f3",
      labelLines: ["长上下文", "2025"],
      weight: 0.7, year: 2025, layer: "folder",
      title: "Long-Context Reasoning in Foundation Models",
      authors: "Wang Hao, Liu Yang, Zhou Tong",
      venue: "ICLR 2025", citations: "引用 54",
      abstract:
        "A hierarchical memory architecture enabling foundation models to reason over million-token contexts with linear compute growth, evaluated on LongBench v2 and RULER.",
    },
    {
      id: "f2",
      labelLines: ["智能体", "2024"],
      weight: 0.65, year: 2024, layer: "folder",
      title: "LLM Agents for Autonomous Scientific Discovery",
      authors: "Li Ming, Chen Hao, Liu Yu",
      venue: "NeurIPS 2024", citations: "引用 73",
      abstract:
        "We benchmark LLM agents on end-to-end scientific discovery loops — literature grounding, hypothesis generation, experiment planning, and result analysis — across 40 chemistry and biology tasks.",
    },
    {
      id: "f8",
      labelLines: ["世界模型", "2025"],
      weight: 0.6, year: 2025, layer: "folder",
      title: "World Models for Embodied Planning: A Survey",
      authors: "Sun Qi, Deng Rui, Fan Yu",
      venue: "TMLR 2025", citations: "引用 12",
      abstract:
        "A systematic survey of learned world models for embodied agents, comparing action-conditioned video prediction, latent dynamics, and their use in planning and policy learning.",
    },
    {
      id: "f4",
      labelLines: ["视频生成", "2025"],
      weight: 0.55, year: 2025, layer: "folder",
      title: "SANA-Video 2.0: Efficient Video Diffusion with Hybrid Linear Attention",
      authors: "Junsong Chen, Jincheng Yu, Yitong Li",
      venue: "arXiv 2026", citations: "引用 31",
      abstract:
        "Hybrid linear attention with periodic softmax anchoring cuts video diffusion training cost by 3.2× while preserving motion quality, generating 81-frame videos on a single H100 in 13.2s.",
    },
    {
      id: "f5",
      labelLines: ["Transformer", "2023"],
      weight: 0.5, year: 2023, layer: "folder",
      title: "Efficient Transformers for Long-Sequence Modeling: A Survey",
      authors: "Guo Liang, Shen Yao",
      venue: "ACM CSUR 2023", citations: "引用 210",
      abstract:
        "We taxonomize efficient transformer variants — sparse attention, low-rank kernels, recurrence, and memory compression — and benchmark them on sequences from 4k to 1M tokens.",
    },
    {
      id: "f6",
      labelLines: ["强化学习", "2024"],
      weight: 0.45, year: 2024, layer: "folder",
      title: "Offline RL Fine-tuning for Real-Robot Policy Adaptation",
      authors: "Han Xu, Qian Zhao",
      venue: "ICML 2024", citations: "引用 38",
      abstract:
        "A conservative offline RL recipe that adapts pretrained manipulation policies to hardware shifts using only 2k logged transitions, with no additional teleoperation.",
    },
    {
      id: "f9",
      labelLines: ["状态空间", "2024"],
      weight: 0.4, year: 2024, layer: "folder",
      title: "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
      authors: "Albert Gu, Tri Dao",
      venue: "COLM 2024", citations: "引用 1.2k",
      abstract:
        "Selective state-space models achieve linear-time sequence modeling with input-dependent dynamics, matching transformer quality at 5× higher inference throughput.",
    },
  ],
  edges: [
    { source: "m1", target: "m2", strength: 0.7 },
    { source: "m2", target: "m3", strength: 0.45 },
    { source: "f1", target: "f4", strength: 0.65 },
    { source: "f2", target: "f3", strength: 0.5 },
    { source: "f5", target: "f9", strength: 0.6 },
    { source: "f8", target: "f7", strength: 0.55 },
    { source: "m1", target: "f7", strength: 0.9, crossLayer: true },
    { source: "m1", target: "f1", strength: 0.6, crossLayer: true },
    { source: "m2", target: "f7", strength: 0.7, crossLayer: true },
    { source: "m2", target: "f8", strength: 0.5, crossLayer: true },
    { source: "m3", target: "f6", strength: 0.4, crossLayer: true },
  ],
  relatedIds: ["m2", "m3", "f7", "f1", "f3", "f2", "f8", "f4", "f5", "f6", "f9"],
};
