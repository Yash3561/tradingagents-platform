import { cn } from "../../lib/cn";

interface SkeletonProps {
  className?: string;
}

/**
 * Shimmer placeholder. Size it with className (h-*, w-*) to reserve the exact
 * space the loaded content will occupy — no layout shift on data arrival.
 */
export default function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-shimmer rounded-md",
        "bg-gradient-to-r from-bg-elevated via-border/70 to-bg-elevated",
        "bg-[length:200%_100%]",
        className,
      )}
    />
  );
}

/** N shimmer lines mimicking a text block; last line is shorter. */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3.5", i === lines - 1 ? "w-3/5" : "w-full")} />
      ))}
    </div>
  );
}
