import type { Transition, Variants } from "framer-motion";

/**
 * Motion tokens — the ONLY timing values used across the app.
 * One ease, two durations, one spring. Anything else is a bug.
 */
export const EASE = [0.16, 1, 0.3, 1] as const;

export const DUR = {
  fast: 0.15, // hovers, presses, small reveals
  base: 0.25, // page/card enters, drawers, modals
} as const;

export const SPRING: Transition = {
  type: "spring",
  stiffness: 380,
  damping: 32,
};

/** Standard element enter: fade + 8px rise. */
export const fadeRise: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: DUR.base, ease: EASE },
  },
};

/** Container that staggers fadeRise children by 40ms. */
export const staggerContainer: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.04 },
  },
};

/** Scale-in for modals / popovers (enter from where they conceptually live). */
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  show: {
    opacity: 1,
    scale: 1,
    transition: { duration: DUR.fast, ease: EASE },
  },
};

/** Slide-in for drawer-style panels from the right. */
export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 24 },
  show: {
    opacity: 1,
    x: 0,
    transition: { duration: DUR.base, ease: EASE },
  },
};
