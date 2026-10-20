export interface FundDetailMetadata {
  projectName: string;
  projectNameZh: string;
  projectNumber: string;
  fundingAgency: string;
  projectCategory: string;
  principalInvestigator: string;
  hostInstitution: string;
  fundingAmount: string;
  startDate: string;
  endDate: string;
  researchAreas: string;
  description: string;
  dataSource: string;
}

export const FUND_DETAIL_METADATA: FundDetailMetadata = {
  projectName: "CAREER: Surface Texturing of Bulk Metallic Glasses for Fabrication of Complex Micro Optics",
  projectNameZh: "面向复杂微光学器件制造的块体金属玻璃表面织构技术研究",
  projectNumber: "1553815",
  fundingAgency: "美国国家科学基金会（NSF）",
  projectCategory: "CAREER 青年教师科研发展项目",
  principalInvestigator: "Xiaoliang Jin",
  hostInstitution: "Oklahoma State University（俄克拉荷马州立大学）",
  fundingAmount: "500,000 美元",
  startDate: "2016-04-01",
  endDate: "2021-03-31（原预计日期）",
  researchAreas: "先进制造、材料科学、微光学",
  description: "研究通过金属玻璃表面织构与振动辅助加工技术，提高复杂微光学器件的制造精度并降低成本。",
  dataSource: "NSF 官方公开资助记录",
};
