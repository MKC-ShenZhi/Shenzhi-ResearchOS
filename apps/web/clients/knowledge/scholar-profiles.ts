import { z } from "zod";
import { KnowledgeClientError } from "./client";

const count = z.number().int().nonnegative().nullable().optional();
const scholarEmploymentSchema = z.object({
  organization: z.string().nullable(),
  role_title: z.string().nullable(),
  department: z.string().nullable(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
});

const scholarExternalIdsSchema = z.object({
  orcid: z.string().regex(/^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$/).nullable(),
});

/** ShenZhi product contract, never an OpenAlex response. */
export const scholarProfileSchema = z.object({
  scholar_id: z.string().trim().min(1),
  name_zh: z.string().nullable().optional(),
  aliases: z.array(z.string()).optional(),
  topics: z.array(z.string()).optional(),
  name_en: z.string().nullable().optional(),
  avatar_path: z.string().nullable().optional(),
  affiliations: z.array(z.object({
    institution: z.string().nullable().optional(),
    position: z.string().nullable().optional(),
  })).nullable().optional(),
  bio_zh: z.string().nullable().optional(),
  bio_en: z.string().nullable().optional(),
  employment: z.array(scholarEmploymentSchema).optional(),
  external_ids: scholarExternalIdsSchema.optional(),
  metrics: z.object({
    paper_count: count,
    source_work_count: count,
    citation_count: count,
    h_index: count,
    i10_index: count,
  }).nullable().optional(),
  annual_citations: z.array(z.object({
    year: z.number().int().min(1).max(9999), count,
  })).nullable().optional(),
  updated_at: z.string().nullable().optional(),
  citation_meta: z.object({
    source: z.string().nullable().optional(),
    coverage: z.string().nullable().optional(),
    as_of: z.string().nullable().optional(),
  }).nullable().optional(),
});
export const scholarProfilePageSchema = z.object({
  items: z.array(scholarProfileSchema),
  limit: z.number().int().min(1).max(100),
  offset: z.number().int().nonnegative(),
  total: count,
  has_more: z.boolean(),
});
export const scholarPapersPageSchema = z.object({
  items: z.array(z.object({
    id: z.string().min(1), title: z.string().min(1),
    authors: z.array(z.string()), year: z.number().int().nullable(),
    venue: z.string().nullable(), abstract: z.string().nullable(),
    doi: z.string().nullable(), pdfUrl: z.string().nullable(),
    platform_detail: z.boolean(),
  })),
  limit: z.number().int().min(1).max(100),
  offset: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
});
export type ScholarProfile = z.infer<typeof scholarProfileSchema>;
export type ScholarProfilePage = z.infer<typeof scholarProfilePageSchema>;
export type ScholarPapersPage = z.infer<typeof scholarPapersPageSchema>;
export type ScholarPublication = ScholarPapersPage["items"][number];

export function parseScholarContract<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new KnowledgeClientError(
    "CONTRACT_VIOLATION", "学者服务返回格式无效", { retryable: false },
  );
  return result.data;
}
