import Link from "next/link";
import { Network, Square } from "lucide-react";
import { libraryFolders, libraryTags } from "@/features/knowledge/data-library";
import { cn } from "@/lib/utils";

const TAG_COLORS = [
  "bg-primary-soft text-primary",
  "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
  "bg-success-soft text-[#059669] dark:text-success",
  "bg-danger-soft text-danger",
  "bg-[#EDE9FE] text-[#7C3AED] dark:bg-[#2a2150] dark:text-brand-violet",
];

/** 我的文献库面板 —— 文件夹树 + 标签(对应知识库页面 SVG 第二栏) */
export function LibraryPanel() {
  return (
    <aside className="w-60 shrink-0 self-stretch border-r border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-bold text-ink">我的文献库</h2>
        <button
          type="button"
          className="flex cursor-pointer items-center gap-1 text-xs text-faint hover:text-muted"
        >
          <Square className="size-3 fill-current" />
          最近添加
        </button>
      </div>

      <button
        type="button"
        className="mt-4 flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-primary-soft text-sm font-medium text-primary transition-colors hover:bg-primary-soft/70"
      >
        <Square className="size-3 fill-current" />
        新建文件夹
      </button>

      <p className="mt-5 px-1 text-xs text-faint">我的作品</p>
      <p className="mt-2 px-1 text-xs text-faint">文件夹</p>
      <ul className="mt-1.5 space-y-0.5">
        {libraryFolders.map((folder) => (
          <li key={folder.name}>
            <button
              type="button"
              className={cn(
                "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors",
                folder.active
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-ink-2 hover:bg-chip",
              )}
            >
              <span
                className={cn(
                  "size-3.5 rounded-[4px]",
                  folder.active ? "bg-primary" : "bg-ink-2/70",
                )}
              />
              <span className="flex-1 text-left">{folder.name}</span>
              <span
                className={cn(
                  "text-xs",
                  folder.active
                    ? "rounded-full bg-primary px-1.5 py-0.5 leading-none text-white"
                    : "text-faint",
                )}
              >
                {folder.count}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <p className="mt-5 px-1 text-xs text-faint">标签</p>
      <div className="mt-2 flex flex-wrap gap-2 px-1">
        {libraryTags.map((tag, i) => (
          <span
            key={tag}
            className={cn(
              "cursor-pointer rounded-md px-2 py-1 text-xs",
              TAG_COLORS[i % TAG_COLORS.length],
            )}
          >
            # {tag}
          </span>
        ))}
      </div>

      <p className="mt-5 px-1 text-xs text-faint">知识图谱</p>
      <Link
        href="/knowledge/graph"
        className="mt-2 flex items-center gap-2.5 rounded-lg bg-panel p-2.5 transition-colors hover:bg-primary-soft"
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary-soft">
          <Network className="size-4 text-primary" />
        </span>
        <span>
          <span className="block text-[13px] font-medium text-ink-2">
            私域知识图谱
          </span>
          <span className="text-[11px] text-faint">
            我的发表 × 收藏论文 · 分层视图 →
          </span>
        </span>
      </Link>

    </aside>
  );
}
