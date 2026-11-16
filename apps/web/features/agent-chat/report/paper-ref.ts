/** Shared types for the citation UI. */

/** A single cited paper (global 1-based numbering, ordered by first appearance). */
export interface PaperRef {
  n: number;
  document_id: string;
  title: string;
  abstract: string;
  year: string;
  authors: string[];
  venue: string;
  doi: string;
  /** Full-text PDF link (official source), may be empty. */
  url: string;
  /** paper = 论文引用；web = 综述图表 fetch 的网页来源（机构页面/报告）。 */
  kind?: "paper" | "web";
}
