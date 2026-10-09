"use client";

import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";

export function TopicSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) { return <div className="relative w-full"><Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" /><Input value={value} onChange={(event) => onChange(event.target.value)} placeholder="搜索主题名称、简介或维护者" aria-label="搜索主题" className="h-12 rounded-full border-border bg-card pl-12 pr-12 text-sm shadow-sm" />{value ? <button type="button" onClick={() => onChange("")} aria-label="清除搜索" className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="size-4" /></button> : null}</div>; }

