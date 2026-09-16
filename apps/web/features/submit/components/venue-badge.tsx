import { BADGE_PALETTE } from "@/features/submit/data";
import type { VenueBadgeName } from "@/types";

/** 等级徽章 —— 配色与投稿详情页 SVG 的调色板一一对应 */
export function VenueBadge({ name }: { name: VenueBadgeName }) {
  const palette = BADGE_PALETTE[name];
  return (
    <span
      className="inline-flex h-7 items-center whitespace-nowrap rounded-full px-3 text-xs font-semibold"
      style={{ backgroundColor: palette.bg, color: palette.fg }}
    >
      {name}
    </span>
  );
}
