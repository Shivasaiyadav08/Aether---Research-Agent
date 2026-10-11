"use client";
import { useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useResearch } from "@/stores/research";
import type { Model } from "@/types";

export function FreeModelPicker() {
  const { models, selectedModel, streaming, modelNotice, update } =
    useResearch();
  const [loading, setLoading] = useState(false);
  async function refresh() {
    const sessionId = useResearch.getState().sessionId;
    setLoading(true);
    try {
      const models = await api<Model[]>("/models?refresh=true");
      if (useResearch.getState().sessionId !== sessionId) return;
      update({
        models,
        selectedModel: models.some(
          (model) => model.id === selectedModel && model.available !== false,
        )
          ? selectedModel
          : models.find((model) => model.available !== false)?.id || "",
        modelNotice: "",
      });
    } catch (error) {
      if (useResearch.getState().sessionId !== sessionId) return;
      update({
        modelNotice:
          error instanceof Error
            ? error.message
            : "Could not load free-tier Gemini models.",
      });
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="free-model-picker">
      <Sparkles size={13} />
      <select
        aria-label="Free-tier Gemini research model"
        title="Models eligible for Google's free tier. Actual quota is checked on use; your Google project's billing tier controls charges."
        value={selectedModel}
        disabled={streaming || loading || !models.length}
        onChange={(event) =>
          update({ selectedModel: event.target.value, modelNotice: "" })
        }
      >
        {!selectedModel && (
          <option value="">No eligible Gemini model ready</option>
        )}
        {selectedModel &&
          !models.some((model) => model.id === selectedModel) && (
            <option value={selectedModel}>
              {selectedModel} · Gemini fallback
            </option>
          )}
        {models.map((model) => (
          <option
            key={model.id}
            value={model.id}
            disabled={model.available === false}
          >
            {model.name} ·{" "}
            {model.available === false
              ? `Unavailable / quota · retry in ${model.retry_after_seconds || 60}s`
              : "Free tier"}
          </option>
        ))}
      </select>
      <button
        type="button"
        aria-label="Refresh free models"
        title="Refresh free models"
        disabled={streaming || loading}
        onClick={() => void refresh()}
      >
        <RefreshCw size={12} className={loading ? "spin" : ""} />
      </button>
      {modelNotice && (
        <span className="model-notice" role="status">
          {modelNotice}
        </span>
      )}
    </div>
  );
}
