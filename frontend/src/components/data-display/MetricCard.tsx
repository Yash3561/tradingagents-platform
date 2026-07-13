import { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "../../lib/cn";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import CountUp from "../ui/CountUp";
import { DUR, EASE } from "../../lib/motion";

interface MetricCardProps {
  label: string;
  /** Pass a number (with `format`) to get an animated count-up. */
  value: string | number;
  /** Formats numeric values each animation frame, e.g. formatCurrency. */
  format?: (n: number) => string;
  delta?: number;        // percentage or absolute
  deltaLabel?: string;
  icon?: ReactNode;
  accent?: "gain" | "loss" | "warn" | "accent";
  className?: string;
}

export default function MetricCard({ label, value, format, delta, deltaLabel, icon, accent, className }: MetricCardProps) {
  const isPos = delta !== undefined && delta > 0;
  const isNeg = delta !== undefined && delta < 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.base, ease: EASE }}
      className={cn("card card-hover p-5 flex flex-col gap-3", className)}
    >
      <div className="flex items-start justify-between">
        <span className="metric-label">{label}</span>
        {icon && (
          <div className={cn(
            "p-2 rounded-lg",
            accent === "gain" && "bg-gain-bg text-gain",
            accent === "loss" && "bg-loss-bg text-loss",
            accent === "warn" && "bg-warn-bg text-warn",
            accent === "accent" && "bg-accent/10 text-accent-bright",
            !accent && "bg-bg-elevated text-text-secondary",
          )}>
            {icon}
          </div>
        )}
      </div>

      <div className="space-y-1">
        <p className="metric-value">
          {typeof value === "number" ? <CountUp value={value} format={format} /> : value}
        </p>
        {delta !== undefined && (
          <div className="flex items-center gap-1">
            {isPos ? (
              <TrendingUp size={12} className="text-gain" />
            ) : isNeg ? (
              <TrendingDown size={12} className="text-loss" />
            ) : (
              <Minus size={12} className="text-text-muted" />
            )}
            <span className={cn(
              "text-xs font-mono font-medium",
              isPos && "text-gain",
              isNeg && "text-loss",
              !isPos && !isNeg && "text-text-muted",
            )}>
              {isPos ? "+" : ""}{delta?.toFixed(2)}{deltaLabel ?? "%"}
            </span>
            <span className="text-xs text-text-muted">today</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
