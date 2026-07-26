"use client";

import { m, useReducedMotion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

// Entrance motion primitives. Each one degrades to a plain <div> when the user
// prefers reduced motion (belt-and-suspenders with the CSS guard in globals.css).
// Honoring the OS reduced-motion setting is an accessibility requirement, not
// a nicety.

const fadeRise: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.24, ease: "easeOut" } },
};

interface RevealProps {
  children: ReactNode;
  className?: string;
}

/** Fade + rise a single block in on mount. */
export function Reveal({ children, className }: RevealProps) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <m.div className={className} initial="hidden" animate="show" variants={fadeRise}>
      {children}
    </m.div>
  );
}

/** Stagger children in sequence — wrap a list, mark each child with <StaggerItem>. */
export function StaggerList({ children, className }: RevealProps) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <m.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
    >
      {children}
    </m.div>
  );
}

export function StaggerItem({ children, className }: RevealProps) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <m.div className={className} variants={fadeRise}>
      {children}
    </m.div>
  );
}
