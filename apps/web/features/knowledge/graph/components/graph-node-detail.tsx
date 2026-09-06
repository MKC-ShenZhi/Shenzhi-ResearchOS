"use client";

import Link from "next/link";
import { ArrowRight, ExternalLink, FileText, Quote, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  KnowledgeClientError,
  KnowledgeGraphNode,
  KnowledgePaperDetail,
} from "@/clients/knowledge";
import { kindLabel, nodeColor } from "../lib/graph-utils";
import { paperDoiUrl, paperHref } from "@/lib/navigation/paper";
import { cn } from "@/lib/utils";

function doiHref(doi: string): string {
  return paperDoiUrl(doi) ?? "";
}

function EntityMeta({ label, value }: { label: string; value: string | null }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
      <p className="mt-0.5 text-xs text-ink-2">{value}</p>
    </div>
  );
}

/** 非 Paper 实体信息 */
function EntityDetail({ node }: { node: KnowledgeGraphNode }) {
  const properties = node.properties;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span
          className="flex size-7 items-center justify-center rounded-lg text-[10px] font-bold text-white"
          style={{ backgroundColor: nodeColor(node.kind) }}
        >
          {kindLabel(node.kind).slice(0, 1)}
        </span>
        <span className="text-[11px] text-faint">{kindLabel(node.kind)}</span>
      </div>
      <h2 className="text-[15px] font-bold leading-snug text-ink">{node.label}</h2>
      <div className="space-y-2 border-t border-line pt-3">
        <EntityMeta label="年份" value={properties.year != null ? String(properties.year) : null} />
        <EntityMeta label="会议" value={typeof properties.venue === "string" ? properties.venue : null} />
        <EntityMeta
          label="描述"
          value={typeof properties.description === "string" ? properties.description : null}
        />
        <EntityMeta
          label="所属机构"
          value={typeof properties.affiliation === "string" ? properties.affiliation : null}
        />
        <EntityMeta
          label="地点"
          value={typeof properties.location === "string" ? properties.location : null}
        />
        <EntityMeta
          label="资助方"
          value={typeof properties.grant === "string" ? properties.grant : null}
        />
        {Array.isArray(properties.authors) && (properties.authors as string[]).length > 0 && (
          <div>
            <p className="text-[10px] uppercase tracking-wide text-faint">作者</p>
            <p className="mt-0.5 text-xs leading-relaxed text-ink-2">
              {(properties.authors as string[]).join(" · ")}
            </p>
          </div>
        )}
        {typeof properties.abstract === "string" && properties.abstract && (
          <div>
            <p className="text-[10px] uppercase tracking-wide text-faint">摘要</p>
            <p className="mt-0.5 line-clamp-6 text-xs leading-relaxed text-ink-2">
              {properties.abstract}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/** Paper 详情（含加载 / 错误态） */
function PaperDetailPanel({
  node,
  paper,
  loading,
  error,
  isCenter,
  onRetry,
  returnTo,
}: {
  node: KnowledgeGraphNode;
  paper: KnowledgePaperDetail | null;
  loading: boolean;
  error: KnowledgeClientError | null;
  isCenter: boolean;
  onRetry: () => void;
  returnTo?: string | null;
}) {
  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 7 }).map((_, index) => (
          <div key={index} className="h-3 animate-pulse rounded bg-chip" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[220px] flex-col items-center justify-center text-center">
        <p className="text-sm font-medium text-ink-2">
          {error.code === "NOT_FOUND" ? "未找到论文详情" : "详情加载失败"}
        </p>
        <p className="mt-2 text-xs text-faint">{error.message}</p>
        <Button size="sm" variant="outline" className="mt-4" onClick={onRetry}>
          <RefreshCw className="size-3.5" />
          重试
        </Button>
      </div>
    );
  }

  const data = paper ?? {
    id: node.id,
    title: node.label,
    abstract: node.properties.abstract ?? null,
    authors: node.properties.authors ?? [],
    year: node.properties.year ?? null,
    venue: node.properties.venue ?? null,
    doi: node.properties.doi ?? null,
    pdfUrl: node.properties.pdfUrl ?? null,
    keywords: Array.isArray(node.properties.keywords)
      ? (node.properties.keywords as string[])
      : [],
    subjects: [],
    citationCount: null,
    referenceCount: null,
    provenance: node.provenance,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-bold leading-snug text-ink">{data.title}</h2>
        {isCenter && (
          <span className="shrink-0 rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-medium text-primary">
            中心论文
          </span>
        )}
      </div>
      <p className="text-xs leading-relaxed text-muted">
        {data.authors.length ? data.authors.join(" · ") : "未知作者"}
      </p>
      <p className="text-xs text-faint">
        {data.venue ?? "暂无会议"} · {data.year ?? "—"}
      </p>

      {/* 指标卡 */}
      <div className="grid grid-cols-2 gap-2.5">
        <Metric label="被引用" value={data.citationCount} />
        <Metric label="参考文献" value={data.referenceCount} />
      </div>

      {/* 操作 */}
      {(data.pdfUrl || data.doi) && (
        <div className="flex flex-wrap gap-2">
          {data.pdfUrl && (
            <a href={data.pdfUrl} target="_blank" rel="noreferrer" className="shrink-0">
              <Button size="sm" className="h-8 rounded-lg px-3 text-xs">
                <FileText className="size-3.5" />
                查看 PDF
              </Button>
            </a>
          )}
          {data.doi && (
            <a href={doiHref(data.doi)} target="_blank" rel="noreferrer" className="shrink-0">
              <Button size="sm" variant="outline" className="h-8 rounded-lg px-3 text-xs">
                DOI
                <ExternalLink className="size-3" />
              </Button>
            </a>
          )}
        </div>
      )}

      {/* 摘要 */}
      {data.abstract && (
        <div className="border-t border-line pt-3">
          <p className="text-[10px] uppercase tracking-wide text-faint">摘要</p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{data.abstract}</p>
        </div>
      )}

      {/* 关键词 */}
      {data.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line pt-3">
          {data.keywords.map((keyword) => (
            <Badge key={keyword} variant="violet">
              {keyword}
            </Badge>
          ))}
        </div>
      )}

      <Link href={paperHref(node.id, returnTo)} className="inline-flex text-sm text-primary hover:underline">阅读论文</Link>

      {/* 关系图谱入口 */}
      <div className="border-t border-line pt-3">
        <Link
          href={paperHref(node.id, returnTo, true)}
          className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
        >
          在图中聚焦此论文
          <ArrowRight className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-lg border border-line/70 bg-panel px-3 py-2.5">
      <p className="text-[15px] font-bold tabular-nums text-ink">
        {value === null ? "—" : value.toLocaleString()}
      </p>
      <p className="mt-0.5 flex items-center gap-1 text-[10px] text-faint">
        <Quote className="size-2.5" />
        {label}
      </p>
    </div>
  );
}

/** 右栏 —— 选中节点详情（Paper 拉详情，实体展示元信息） */
export function GraphNodeDetail({
  node,
  paper,
  loading,
  error,
  isCenter,
  onRetry,
  returnTo,
}: {
  node: KnowledgeGraphNode | null;
  paper: KnowledgePaperDetail | null;
  loading: boolean;
  error: KnowledgeClientError | null;
  isCenter: boolean;
  onRetry: () => void;
  returnTo?: string | null;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between">
        <h1 className="text-sm font-semibold text-ink">节点详情</h1>
        <span className="text-[10px] text-faint">点击图谱节点查看</span>
      </div>
      <div className={cn("mt-4 min-h-0 flex-1 overflow-y-auto")}>
        {!node ? (
          <div className="flex h-full min-h-[220px] items-center justify-center text-center">
            <p className="text-xs text-faint">选择一篇论文查看详情</p>
          </div>
        ) : node.kind === "Paper" ? (
          <PaperDetailPanel
            node={node}
            paper={paper}
            loading={loading}
            error={error}
            isCenter={isCenter}
            onRetry={onRetry}
            returnTo={returnTo}
          />
        ) : (
          <EntityDetail node={node} />
        )}
      </div>
    </div>
  );
}
