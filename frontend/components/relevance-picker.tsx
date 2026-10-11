"use client";

import { useResearch } from "@/stores/research";

export function RelevancePicker() {
  const { relevanceThreshold, streaming, update } = useResearch();
  const percentage = Math.round(relevanceThreshold * 100);

  return (
    <label
      className="relevance-picker"
      title="Minimum relevance score for each document chunk. Higher values filter more strictly. Evidence sufficiency and grounding are checked separately."
    >
      <span>Relevance</span>
      <input
        type="range"
        aria-label="Minimum document relevance percentage"
        aria-valuetext={`${percentage}%`}
        min={0}
        max={100}
        step={1}
        value={percentage}
        disabled={streaming}
        onChange={(event) =>
          update({ relevanceThreshold: event.target.valueAsNumber / 100 })
        }
      />
      <span className="relevance-value">{percentage}%</span>
    </label>
  );
}
