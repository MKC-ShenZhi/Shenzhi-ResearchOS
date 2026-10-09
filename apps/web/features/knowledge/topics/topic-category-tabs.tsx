"use client";

export function TopicCategoryTabs({ categories, value, onChange }: { categories: string[]; value: string; onChange: (value: string) => void }) { return <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="主题分类">{["全部", ...categories].map((category) => { const selected = value === (category === "全部" ? "" : category); return <button key={category} type="button" role="tab" aria-selected={selected} onClick={() => onChange(category === "全部" ? "" : category)} className={`shrink-0 rounded-full border px-4 py-2 text-sm transition ${selected ? "border-primary bg-primary text-primary-foreground shadow-sm" : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{category}</button>; })}</div>; }

