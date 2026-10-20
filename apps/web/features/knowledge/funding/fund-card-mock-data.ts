export interface FundCardMockMetadata {
  agencyAbbreviation: string;
  agencyName: string;
  projectType: string;
  shortDescription: string;
  principalInvestigator: string;
  hostInstitution: string;
  period: string;
  fundingAmount: string;
}

// Temporary display-only fixtures for Fund Library cards; keep outside Knowledge contracts.
const CARD_METADATA_TEMPLATES: Record<string, FundCardMockMetadata> = {
  "template-0": {
    agencyAbbreviation: "NSF",
    agencyName: "National Science Foundation",
    projectType: "Research Grant",
    shortDescription: "探索精密表面加工方法，提升复杂光学元件的制造质量与效率。",
    principalInvestigator: "Clara Nguyen",
    hostInstitution: "University of California, Berkeley",
    period: "2018–2022",
    fundingAmount: "$420,000",
  },
  "template-1": {
    agencyAbbreviation: "NIH",
    agencyName: "National Institutes of Health",
    projectType: "R01 Project Grant",
    shortDescription: "开发新型材料表征与加工技术，支持高性能器件的设计和制备。",
    principalInvestigator: "Aaron Patel",
    hostInstitution: "University of Michigan",
    period: "2020–2024",
    fundingAmount: "$680,000",
  },
  "template-2": {
    agencyAbbreviation: "DOE",
    agencyName: "U.S. Department of Energy",
    projectType: "Early Career Research Program",
    shortDescription: "研究数据驱动的材料发现流程，加快候选材料筛选与实验验证。",
    principalInvestigator: "Sofia Martinez",
    hostInstitution: "Northwestern University",
    period: "2019–2023",
    fundingAmount: "$350,000",
  },
  "template-3": {
    agencyAbbreviation: "NSF",
    agencyName: "National Science Foundation",
    projectType: "CAREER",
    shortDescription: "结合精密加工与表面织构技术，改善微尺度器件的性能表现。",
    principalInvestigator: "Maya Chen",
    hostInstitution: "Oklahoma State University",
    period: "2016–2021",
    fundingAmount: "$500,000",
  },
  "template-4": {
    agencyAbbreviation: "NSF",
    agencyName: "National Science Foundation",
    projectType: "CAREER",
    shortDescription: "构建可扩展的光学制造方案，降低复杂微器件的加工成本。",
    principalInvestigator: "Daniel Kim",
    hostInstitution: "Oklahoma State University",
    period: "2021–2025",
    fundingAmount: "$740,000",
  },
  "template-5": {
    agencyAbbreviation: "DOE",
    agencyName: "U.S. Department of Energy",
    projectType: "Basic Energy Sciences Grant",
    shortDescription: "融合实验与计算方法，理解先进合金在极端条件下的结构变化。",
    principalInvestigator: "Aisha Johnson",
    hostInstitution: "University of Illinois Urbana-Champaign",
    period: "2017–2022",
    fundingAmount: "$610,000",
  },
  "template-6": {
    agencyAbbreviation: "NASA",
    agencyName: "National Aeronautics and Space Administration",
    projectType: "Early Career Faculty Award",
    shortDescription: "改进振动辅助加工工艺，提升精密零件的一致性与表面质量。",
    principalInvestigator: "Ethan Brooks",
    hostInstitution: "Purdue University",
    period: "2022–2026",
    fundingAmount: "$290,000",
  },
  "template-7": {
    agencyAbbreviation: "NSF",
    agencyName: "National Science Foundation",
    projectType: "Collaborative Research Grant",
    shortDescription: "探索面向下一代传感器的微型光学结构与集成制造技术。",
    principalInvestigator: "Priya Raman",
    hostInstitution: "University of Washington",
    period: "2020–2024",
    fundingAmount: "$560,000",
  },
};

export function getFundCardMetadata(fundingId: string): FundCardMockMetadata {
  const hash = [...fundingId].reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return CARD_METADATA_TEMPLATES[`template-${hash % 8}`];
}
