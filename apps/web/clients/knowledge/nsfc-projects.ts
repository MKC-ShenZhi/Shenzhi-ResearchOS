import { apiJson } from "../backend/http";

interface ProjectSummary {
  awardNumber: string;
  name: string;
  awardYear: number;
  status: string;
  program: string;
  institutions: string[];
  topics: string[];
}

interface ProjectList {
  items: ProjectSummary[];
  total: number;
  snapshot: boolean;
}

interface ProjectDetail extends ProjectSummary {
  summary: string;
  startDate: string;
  endDate: string;
  sourceUrl: string | null;
  members: { name: string; role: string }[];
  papers: { id: string; title: string; sourceUrl: string | null }[];
  snapshot: boolean;
}

const endpoint = "/knowledge/nsfc-projects";

export function searchNsfcProjects(q: string, limit: number, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
  return apiJson<ProjectList>(`${endpoint}?${params}`, { signal });
}

export function getNsfcProject(awardNumber: string, signal?: AbortSignal) {
  return apiJson<ProjectDetail>(`${endpoint}/${encodeURIComponent(awardNumber)}`, { signal });
}
