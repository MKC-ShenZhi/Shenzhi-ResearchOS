"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { popoverPosition } from "@/lib/use-popover-placement";

/** 带进出动画的弹出面板，定位于相对定位的锚点容器内 */
export function PopoverPanel({
  open,
  placement,
  align = "left",
  className,
  children,
}: {
  open: boolean;
  placement: "up" | "down";
  align?: "left" | "right";
  className?: string;
  children: ReactNode;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: placement === "down" ? -4 : 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: placement === "down" ? -4 : 4 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          style={{ transformOrigin: `${placement === "down" ? "top" : "bottom"} ${align}` }}
          className={cn(
            "absolute z-30 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-card p-1.5 shadow-pop",
            align === "left" ? "left-0" : "right-0",
            popoverPosition(placement),
            className,
          )}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
