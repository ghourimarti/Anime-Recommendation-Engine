"use client";

import { domAnimation, LazyMotion } from "framer-motion";
import type { ReactNode } from "react";

/** Loads ONLY framer-motion's DOM animation features (~15 kB) instead of the
 *  full bundle (~40 kB). `strict` forbids the heavy `motion.*` components, so we
 *  use the lightweight `m.*` everywhere (see reveal.tsx) — the build fails loudly
 *  if anyone reintroduces `motion.*`. */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={domAnimation} strict>
      {children}
    </LazyMotion>
  );
}
