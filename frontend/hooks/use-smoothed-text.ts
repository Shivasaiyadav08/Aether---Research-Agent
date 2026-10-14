"use client";

import { useEffect, useRef, useState } from "react";

/** Smooth network batches without changing the canonical draft or saved answer. */
export function useSmoothedText(text: string, enabled: boolean) {
  const [displayed, setDisplayed] = useState("");
  const visible = useRef("");
  const length = useRef(0);

  useEffect(() => {
    if (!enabled) {
      visible.current = text;
      length.current = Array.from(text).length;
      return;
    }
    // A model switch, correction, or cancellation must remove the old draft.
    if (!text.startsWith(visible.current)) {
      visible.current = "";
      length.current = 0;
    }
    const characters = Array.from(text);
    let frame = 0;
    let previous = 0;
    function reveal(now: number) {
      if (now - previous >= 32) {
        previous = now;
        const remaining = characters.length - length.current;
        length.current += Math.min(
          remaining,
          Math.max(4, Math.ceil(remaining / 8)),
        );
        visible.current = characters.slice(0, length.current).join("");
        setDisplayed(visible.current);
      }
      if (length.current < characters.length)
        frame = requestAnimationFrame(reveal);
    }
    frame = requestAnimationFrame(reveal);
    return () => cancelAnimationFrame(frame);
  }, [text, enabled]);

  return enabled ? (text.startsWith(displayed) ? displayed : "") : text;
}
