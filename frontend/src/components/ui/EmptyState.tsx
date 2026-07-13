import { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "../../lib/cn";
import { fadeRise } from "../../lib/motion";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}

/**
 * Standard empty state for any list/table: icon + one-line explanation +
 * optional action. Every data surface should render this instead of a void.
 */
export default function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <motion.div
      variants={fadeRise}
      initial="hidden"
      animate="show"
      className={cn("flex flex-col items-center justify-center gap-3 py-12 px-6 text-center", className)}
    >
      <div className="p-3 rounded-xl bg-bg-elevated text-text-muted">{icon}</div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {description && <p className="text-xs text-text-secondary max-w-sm">{description}</p>}
      </div>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-1 px-3.5 py-1.5 rounded-lg bg-accent hover:bg-accent-bright text-white text-xs font-medium transition-colors duration-150"
        >
          {action.label}
        </button>
      )}
    </motion.div>
  );
}
