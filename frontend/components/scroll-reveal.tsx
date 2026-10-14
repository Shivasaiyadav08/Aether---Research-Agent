"use client";

import { useEffect, useRef } from "react";

/** Progressive enhancement: content stays readable without JS or motion support. */
export function ScrollReveal({ children }: { children: React.ReactNode }) {
  const element = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = element.current;
    if (
      !node ||
      !window.IntersectionObserver ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          node.classList.add("is-revealed");
          observer.disconnect();
        }
      },
      { threshold: 0.08 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="scroll-reveal" ref={element}>
      {children}
    </div>
  );
}
