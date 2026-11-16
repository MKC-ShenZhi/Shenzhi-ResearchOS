import { apiJson } from "../backend/http";

export interface ProjectSummary {
  awardNumber: string;
  name: string;
  awardYear: number;
  status: string;
  program: string;
  institutions: string[];
  topics: string[];
  summary?: string;
  principalInvestigators?: string[];
  paperCount?: number | null;
}

interface ProjectList {
  items: ProjectSummary[];
  total: number;
}

interface ProjectDetail extends ProjectSummary {
  startDate: string;
  endDate: string;
  sourceUrl: string | null;
  members: { name: string; role: string }[];
  papers: { id: string; title: string; sourceUrl: string | null }[];
}

const endpoint = "/knowledge/projects";

export function searchNsfcProjects(q: string, limit: number, offset: number, keyword: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
  if (keyword) params.set("keyword", keyword);
  return apiJson<ProjectList>(`${endpoint}?${params}`, { signal });
}

export function getNsfcProject(awardNumber: string, signal?: AbortSignal) {
  return apiJson<ProjectDetail>(`${endpoint}/${encodeURIComponent(awardNumber)}`, { signal });
}
