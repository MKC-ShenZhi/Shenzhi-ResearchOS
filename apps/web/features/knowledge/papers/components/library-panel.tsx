import { History, Square } from "lucide-react";
import { libraryFolders } from "@/lib/data/library";
import { cn } from "@/lib/utils";

/** 我的文献库面板 —— 文件夹树 + 标签(对应知识库页面 SVG 第二栏) */
export function LibraryPanel({
  historyActive,
  onHistoryClick,
}: {
  historyActive: boolean;
  onHistoryClick: () => void;
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col self-stretch border-r border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-bold text-ink">我的文献库</h2>
      </div>

      <button
        type="button"
        className="mt-4 flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-primary-soft text-sm font-medium text-primary transition-colors hover:bg-primary-soft/70"
      >
        <Square className="size-3 fill-current" />
        新建文件夹
      </button>

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

      <div className="mt-auto">
        <hr className="mb-3 border-line" />
        
        <button
          type="button"
          onClick={onHistoryClick}
          className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm text-ink-2 transition-colors hover:bg-chip"
        >
          <History className={cn("size-3.5", historyActive && "text-primary")} />
          浏览历史
        </button>
      </div>
    </aside>
  );
}
