import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium [&_svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-primary-soft text-primary",
        violet: "bg-primary-soft text-primary",
        amber: "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
        green: "bg-success-soft text-[#059669] dark:text-success",
        gray: "bg-chip text-muted",
        plain: "text-muted",
        danger: "bg-danger-soft text-danger",
        dark: "bg-ink text-white",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant, className }))}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
