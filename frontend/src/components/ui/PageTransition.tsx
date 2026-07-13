import { ReactNode } from "react";
import { motion } from "framer-motion";
import { staggerContainer } from "../../lib/motion";

interface PageTransitionProps {
  children: ReactNode;
  className?: string;
}

/**
 * Standard page enter: children using the `fadeRise` variant (or any variant
 * with hidden/show states) stagger in at 40ms. Wrap page roots in this instead
 * of ad-hoc motion.div initial/animate props.
 */
export default function PageTransition({ children, className }: PageTransitionProps) {
  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="show" className={className}>
      {children}
    </motion.div>
  );
}
