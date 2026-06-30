import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "../../lib/cn";
import { fmt } from "../../lib/formatters";

interface PnLBadgeProps {
  value: number;
  showDollar?: boolean;
  size?: "sm" | "md" | "lg";
}

export default function PnLBadge({ value, showDollar = false, size = "md" }: PnLBadgeProps) {
  const isPos = value >= 0;
  const Icon = isPos ? TrendingUp : TrendingDown;

  return (
    <span className={cn(
      "inline-flex items-center gap-1 font-mono font-medium rounded-md",
      isPos ? "badge-gain" : "badge-loss",
      size === "sm" && "text-2xs px-1.5 py-0.5",
      size === "md" && "text-xs px-2 py-0.5",
      size === "lg" && "text-sm px-3 py-1",
    )}>
      <Icon size={size === "sm" ? 10 : size === "lg" ? 14 : 12} />
      {showDollar ? fmt.signUsd(value) : `${isPos ? "+" : ""}${value.toFixed(2)}%`}
    </span>
  );
}
