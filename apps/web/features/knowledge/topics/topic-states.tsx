import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TopicLoadingState() { return <div className="flex min-h-56 items-center justify-center rounded-2xl border border-dashed border-line bg-card/60 text-muted"><LoaderCircle className="mr-2 size-5 animate-spin text-primary" />正在加载主题</div>; }
export function TopicEmptyState({ onReset }: { onReset?: () => void }) { return <div className="flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-card/60 px-6 text-center"><Inbox className="mb-3 size-8 text-muted" /><p className="font-medium text-ink">暂时没有匹配的主题</p><p className="mt-1 text-sm text-muted">试试其他关键词，或切换到全部分类。</p>{onReset ? <Button className="mt-4" variant="outline" size="sm" onClick={onReset}>清除筛选</Button> : null}</div>; }
export function TopicErrorState({ onRetry }: { onRetry: () => void }) { return <div className="flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-danger/30 bg-danger/5 px-6 text-center"><AlertCircle className="mb-3 size-8 text-danger" /><p className="font-medium text-ink">主题暂时加载失败</p><p className="mt-1 text-sm text-muted">请稍后重试。</p><Button className="mt-4" variant="outline" size="sm" onClick={onRetry}>重新加载</Button></div>; }

