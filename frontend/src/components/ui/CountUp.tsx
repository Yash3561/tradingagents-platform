import { useEffect, useRef, useState } from "react";
import { animate, useReducedMotion } from "framer-motion";
import { EASE } from "../../lib/motion";

interface CountUpProps {
  value: number;
  /** Formats the interpolated number each frame (e.g. formatCurrency). */
  format?: (n: number) => string;
  className?: string;
  /** Seconds. Defaults to 0.6 — long enough to read, short enough to trust. */
  duration?: number;
}

/**
 * Animated number for KPI values: counts from the previously displayed value
 * to the new one. First render starts from 0; reduced-motion users see the
 * final value immediately.
 */
export default function CountUp({ value, format, className, duration = 0.6 }: CountUpProps) {
  const reduced = useReducedMotion();
  const fmt = format ?? ((n: number) => n.toLocaleString());
  const fromRef = useRef(0);
  const [display, setDisplay] = useState(() => fmt(reduced ? value : 0));
  const fmtRef = useRef(fmt);
  fmtRef.current = fmt;

  useEffect(() => {
    if (reduced) {
      fromRef.current = value;
      setDisplay(fmtRef.current(value));
      return;
    }
    const controls = animate(fromRef.current, value, {
      duration,
      ease: EASE,
      onUpdate: (v) => setDisplay(fmtRef.current(v)),
      onComplete: () => {
        fromRef.current = value;
      },
    });
    return () => {
      fromRef.current = value;
      controls.stop();
    };
  }, [value, reduced, duration]);

  return <span className={className}>{display}</span>;
}
